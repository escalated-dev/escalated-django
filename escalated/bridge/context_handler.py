"""
Handles ctx.* callbacks coming from the plugin runtime.

The plugin runtime sends JSON-RPC requests back to the host when plugin
code calls ctx.tickets.find(), ctx.config.all(), ctx.store.query(), etc.
This module translates those calls into native Django/ORM operations and
returns the serialisable result.

ctx.* callbacks are synchronous from the plugin's perspective: the plugin
awaits the promise and the host blocks the JSON-RPC read loop until the ORM
operation completes, then sends back the JSON-RPC response.
"""

import logging

logger = logging.getLogger("escalated.bridge")


# ctx.tickets.query filter keys (plugin contract) and the field each reads.
# Any other key is an error, never a field name or a lookup.
TICKET_FILTERS = {
    "id": "pk",
    "reference": "reference",
    "status": "status",
    "priority": "priority",
    "channel": "channel",
    "ticket_type": "ticket_type",
    "department_id": "department_id",
    "requester_id": "requester_object_id",
    "contact_id": "contact_id",
    "assigned_to": "assigned_to_id",
}

# ctx.replies.query filter keys and their fields.
REPLY_FILTERS = {
    "ticket_id": "ticket_id",
    "is_internal": "is_internal_note",
    "type": "type",
}

# The most rows a ticket or reply query hands back.
QUERY_LIMIT = 500

# The fields each ctx write takes (plugin contract). title and body are the
# SDK's names for subject and description. Any other key is an error, never
# an attribute: a plugin never names an author, a requester, an assignee or a
# reply's flags.
TICKET_UPDATE_FIELDS = (
    "subject",
    "title",
    "body",
    "description",
    "priority",
    "status",
    "department_id",
    "ticket_type",
    "metadata",
)
TICKET_CREATE_FIELDS = (*TICKET_UPDATE_FIELDS, "channel", "contact_id", "requester_email", "requester_name")
REPLY_CREATE_FIELDS = ("ticket_id", "body", "is_internal")
CONTACT_CREATE_FIELDS = ("name", "email")
TAG_CREATE_FIELDS = ("name", "slug", "color")


def _contract_fields(data, allowed, method):
    """The plugin's data, refused when it holds a key outside the contract."""
    if not isinstance(data, dict):
        raise ValueError(f"{method} requires a data object")
    unknown = [str(key) for key in data if key not in allowed]
    if unknown:
        raise ValueError(f"{method} does not accept: {', '.join(unknown)}")
    return data


def _optional_text(data, key, method):
    """A stripped, non-empty string field, or None when absent or blank."""
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{method}: {key} must be a string")
    return str(value).strip() or None


def _choice(data, key, choices, method):
    value = _optional_text(data, key, method)
    if value is not None and value not in choices.values:
        raise ValueError(f'{method}: unknown {key} "{value}"')
    return value


def _ticket_attributes(data, method):
    """Ticket fields from the contract fields a plugin sent."""
    from escalated.models import Department, Ticket

    attributes = {}
    subject = _optional_text(data, "subject", method) or _optional_text(data, "title", method)
    if subject is not None:
        attributes["subject"] = subject
    if "description" in data or "body" in data:
        description = data["description"] if "description" in data else data["body"]
        if description is not None and not isinstance(description, str):
            raise ValueError(f"{method}: description must be a string")
        attributes["description"] = description or ""
    for key, choices in (
        ("priority", Ticket.Priority),
        ("status", Ticket.Status),
        ("ticket_type", Ticket.TicketType),
    ):
        value = _choice(data, key, choices, method)
        if value is not None:
            attributes[key] = value
    if "department_id" in data:
        department_id = data["department_id"]
        if department_id is None:
            attributes["department"] = None
        else:
            department = Department.objects.filter(pk=department_id).first() if str(department_id).isdigit() else None
            if department is None:
                raise ValueError(f"{method}: no such department")
            attributes["department"] = department
    if "metadata" in data:
        if data["metadata"] is not None and not isinstance(data["metadata"], dict):
            raise ValueError(f"{method}: metadata must be an object")
        attributes["metadata"] = data["metadata"]
    return attributes


def _contract_lookups(filter_spec, fields, method):
    """Equality lookups on whitelisted keys, single values only."""
    if filter_spec is None:
        return {}
    if not isinstance(filter_spec, dict):
        raise ValueError(f"{method} requires an object filter")
    lookups = {}
    for key, value in filter_spec.items():
        field = fields.get(key)
        if field is None:
            raise ValueError(f'{method} cannot filter by "{key}"')
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError(f'{method} filter "{key}" must be a single value')
        if field == "requester_object_id" and value is not None:
            value = str(value)
        lookups[f"{field}__isnull" if value is None else field] = True if value is None else value
    return lookups


class ContextHandler:
    """
    Dispatch ctx.* method calls from the runtime to the appropriate handler.

    The bridge sets current_plugin before each RPC dispatch so that
    store/config calls that omit the ``plugin`` param default to the
    currently executing plugin.
    """

    def __init__(self):
        self.current_plugin: str = ""
        self._bridge = None  # set by PluginBridge after construction
        self._acting_user = None

    def set_bridge(self, bridge) -> None:
        self._bridge = bridge

    def set_current_plugin(self, plugin: str) -> None:
        self.current_plugin = plugin

    def set_acting_user(self, user) -> None:
        """The user a host call is served for (a widget badge's viewer), or None."""
        self._acting_user = user if getattr(user, "is_authenticated", False) else None

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def handle(self, method: str, params: dict) -> object:
        """
        Route a ctx.* method to the appropriate handler and return the result.

        Parameters
        ----------
        method:
            e.g. "ctx.tickets.find", "ctx.store.set", "ctx.log"
        params:
            Arbitrary dict of parameters from the runtime.
        """
        handlers = {
            # Config
            "ctx.config.all": self._config_all,
            "ctx.config.get": self._config_get,
            "ctx.config.set": self._config_set,
            # Store
            "ctx.store.get": self._store_get,
            "ctx.store.set": self._store_set,
            "ctx.store.query": self._store_query,
            "ctx.store.insert": self._store_insert,
            "ctx.store.update": self._store_update,
            "ctx.store.delete": self._store_delete,
            # Tickets
            "ctx.tickets.find": self._tickets_find,
            "ctx.tickets.query": self._tickets_query,
            "ctx.tickets.create": self._tickets_create,
            "ctx.tickets.update": self._tickets_update,
            # Replies
            "ctx.replies.find": self._replies_find,
            "ctx.replies.query": self._replies_query,
            "ctx.replies.create": self._replies_create,
            # Contacts
            "ctx.contacts.find": self._contacts_find,
            "ctx.contacts.findByEmail": self._contacts_find_by_email,
            "ctx.contacts.create": self._contacts_create,
            # Tags
            "ctx.tags.all": self._tags_all,
            "ctx.tags.create": self._tags_create,
            # Departments
            "ctx.departments.all": self._departments_all,
            "ctx.departments.find": self._departments_find,
            # Agents
            "ctx.agents.all": self._agents_all,
            "ctx.agents.find": self._agents_find,
            # Broadcast
            "ctx.broadcast.toChannel": self._broadcast_to_channel,
            "ctx.broadcast.toUser": self._broadcast_to_user,
            "ctx.broadcast.toTicket": self._broadcast_to_ticket,
            # Misc
            "ctx.emit": self._emit,
            "ctx.log": self._ctx_log,
            "ctx.currentUser": self._current_user,
        }

        handler = handlers.get(method)
        if handler is None:
            raise RuntimeError(f"Unknown ctx method: {method}")

        return handler(params)

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _config_all(self, params: dict) -> dict:
        plugin = params.get("plugin", self.current_plugin)
        return self._get_plugin_config(plugin)

    def _config_get(self, params: dict) -> object:
        plugin = params.get("plugin", self.current_plugin)
        key = params.get("key")
        if not key:
            raise ValueError("ctx.config.get requires key")
        return self._get_plugin_config(plugin).get(key)

    def _config_set(self, params: dict) -> None:
        plugin = params.get("plugin", self.current_plugin)
        data = params.get("data")
        if data is None:
            raise ValueError("ctx.config.set requires data")
        self._set_plugin_config(plugin, data)
        return None

    def _get_plugin_config(self, plugin: str) -> dict:
        from escalated.bridge.plugin_store_record import PluginStoreRecord

        record = PluginStoreRecord.objects.filter(
            plugin=plugin,
            collection="__config__",
            key="__config__",
        ).first()
        if record is None:
            return {}
        return record.data if isinstance(record.data, dict) else {}

    def _set_plugin_config(self, plugin: str, data: dict) -> None:
        from escalated.bridge.plugin_store_record import PluginStoreRecord

        existing = self._get_plugin_config(plugin)
        merged = {**existing, **data}
        PluginStoreRecord.objects.update_or_create(
            plugin=plugin,
            collection="__config__",
            key="__config__",
            defaults={"data": merged},
        )

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def _store_get(self, params: dict) -> object:
        from escalated.bridge.plugin_store_record import PluginStoreRecord

        plugin = params.get("plugin", self.current_plugin)
        collection = params.get("collection")
        key = params.get("key")
        if not collection:
            raise ValueError("ctx.store.get requires collection")
        if not key:
            raise ValueError("ctx.store.get requires key")

        record = PluginStoreRecord.objects.filter(plugin=plugin, collection=collection, key=key).first()
        return record.data if record else None

    def _store_set(self, params: dict) -> None:
        from escalated.bridge.plugin_store_record import PluginStoreRecord

        plugin = params.get("plugin", self.current_plugin)
        collection = params.get("collection")
        key = params.get("key")
        value = params.get("value")
        if not collection:
            raise ValueError("ctx.store.set requires collection")
        if not key:
            raise ValueError("ctx.store.set requires key")

        PluginStoreRecord.objects.update_or_create(
            plugin=plugin,
            collection=collection,
            key=key,
            defaults={"data": value},
        )
        return None

    def _store_query(self, params: dict) -> list:
        from escalated.bridge.plugin_store_record import PluginStoreRecord

        plugin = params.get("plugin", self.current_plugin)
        collection = params.get("collection")
        if not collection:
            raise ValueError("ctx.store.query requires collection")

        filter_spec = params.get("filter") or {}
        options = params.get("options") or {}

        qs = PluginStoreRecord.objects.filter(plugin=plugin, collection=collection)

        # Apply simple equality filters against the JSON data field.
        # Advanced operators ($gt, $in, etc.) require raw SQL and are
        # database-specific; we support them for PostgreSQL and SQLite via
        # the _apply_json_filter helper.
        for field, condition in filter_spec.items():
            if isinstance(condition, dict):
                for op, val in condition.items():
                    qs = self._apply_json_operator(qs, field, op, val)
            else:
                # Simple equality — filter in Python after fetching the
                # collection (avoids DB-specific JSON path syntax).
                qs = qs.filter(data__contains={field: condition})

        # Ordering and pagination are applied in Python for portability.
        records = list(qs)

        order_by = options.get("orderBy")
        if order_by:
            order_dir = options.get("order", "asc").lower()
            reverse = order_dir == "desc"
            records.sort(
                key=lambda r: (r.data or {}).get(order_by) if isinstance(r.data, dict) else None,
                reverse=reverse,
            )

        limit = options.get("limit")
        if limit is not None:
            records = records[: int(limit)]

        return [{"_id": r.id, **(r.data if isinstance(r.data, dict) else {})} for r in records]

    def _apply_json_operator(self, qs, field: str, op: str, value):
        """
        Apply a MongoDB-style query operator to a PluginStoreRecord queryset.

        Only $gt/$gte/$lt/$lte/$ne/$in/$nin are supported.  These are
        evaluated in Python (after fetching the queryset) to remain
        database-agnostic.  For large collections a database-level
        implementation would be more efficient.
        """

        def _extract(record):
            if not isinstance(record.data, dict):
                return None
            return record.data.get(field)

        op_funcs = {
            "$gt": lambda v, val: v is not None and v > val,
            "$gte": lambda v, val: v is not None and v >= val,
            "$lt": lambda v, val: v is not None and v < val,
            "$lte": lambda v, val: v is not None and v <= val,
            "$ne": lambda v, val: v != val,
            "$in": lambda v, val: v in (val if isinstance(val, list) else [val]),
            "$nin": lambda v, val: v not in (val if isinstance(val, list) else [val]),
        }

        if op not in op_funcs:
            raise ValueError(f"Unsupported store query operator: {op}")

        func = op_funcs[op]
        # Materialise queryset and filter in Python
        all_ids = [r.pk for r in qs if func(_extract(r), value)]
        return qs.model.objects.filter(pk__in=all_ids)

    def _store_insert(self, params: dict) -> dict:
        from escalated.bridge.plugin_store_record import PluginStoreRecord

        plugin = params.get("plugin", self.current_plugin)
        collection = params.get("collection")
        data = params.get("data")
        if not collection:
            raise ValueError("ctx.store.insert requires collection")
        if data is None:
            raise ValueError("ctx.store.insert requires data")

        record = PluginStoreRecord.objects.create(
            plugin=plugin,
            collection=collection,
            key=data.get("key") if isinstance(data, dict) else None,
            data=data,
        )
        return {"_id": record.id, **(record.data if isinstance(record.data, dict) else {})}

    def _store_update(self, params: dict) -> dict:
        from escalated.bridge.plugin_store_record import PluginStoreRecord

        plugin = params.get("plugin", self.current_plugin)
        collection = params.get("collection")
        key = params.get("key")
        data = params.get("data")
        if not collection:
            raise ValueError("ctx.store.update requires collection")
        if not key:
            raise ValueError("ctx.store.update requires key")
        if data is None:
            raise ValueError("ctx.store.update requires data")

        record = PluginStoreRecord.objects.get(plugin=plugin, collection=collection, key=key)
        existing = record.data if isinstance(record.data, dict) else {}
        record.data = {**existing, **data}
        record.save(update_fields=["data"])
        return {"_id": record.id, **(record.data if isinstance(record.data, dict) else {})}

    def _store_delete(self, params: dict) -> None:
        from escalated.bridge.plugin_store_record import PluginStoreRecord

        plugin = params.get("plugin", self.current_plugin)
        collection = params.get("collection")
        key = params.get("key")
        if not collection:
            raise ValueError("ctx.store.delete requires collection")
        if not key:
            raise ValueError("ctx.store.delete requires key")

        PluginStoreRecord.objects.filter(plugin=plugin, collection=collection, key=key).delete()
        return None

    # ------------------------------------------------------------------
    # Tickets
    # ------------------------------------------------------------------

    def _tickets_find(self, params: dict) -> dict | None:
        from escalated.models import Ticket

        ticket_id = params.get("id")
        if ticket_id is None:
            raise ValueError("ctx.tickets.find requires id")
        ticket = Ticket.objects.filter(pk=ticket_id).first()
        return self._model_to_dict(ticket)

    def _tickets_query(self, params: dict) -> list:
        from escalated.models import Ticket

        lookups = _contract_lookups(params.get("filter"), TICKET_FILTERS, "ctx.tickets.query")
        qs = Ticket.objects.filter(**lookups).order_by("pk")[:QUERY_LIMIT]
        return [self._model_to_dict(t) for t in qs]

    def _tickets_create(self, params: dict) -> dict:
        from escalated.models import Contact

        method = "ctx.tickets.create"
        data = _contract_fields(params.get("data"), TICKET_CREATE_FIELDS, method)
        attributes = _ticket_attributes(data, method)
        if not attributes.get("subject"):
            raise ValueError(f"{method} requires subject")
        attributes.setdefault("description", "")
        attributes["channel"] = _optional_text(data, "channel", method) or "api"

        # The requester is a contact, never a user id the plugin names.
        contact = None
        if data.get("contact_id") is not None:
            contact_id = data["contact_id"]
            contact = Contact.objects.filter(pk=contact_id).first() if str(contact_id).isdigit() else None
            if contact is None:
                raise ValueError(f"{method}: no such contact")
        else:
            email = _optional_text(data, "requester_email", method)
            if email is not None:
                if "@" not in email:
                    raise ValueError(f"{method}: requester_email is not an email address")
                contact = Contact.find_or_create_by_email(email, _optional_text(data, "requester_name", method))
        if contact is not None:
            attributes["contact"] = contact
            attributes["guest_email"] = contact.email
            attributes["guest_name"] = contact.name or contact.email

        # Through the ticket service, like a guest or widget ticket: SLA, the
        # created activity, ticket.created, workflows and webhooks.
        from escalated.services.ticket_service import TicketService

        ticket = TicketService().create_for_system(attributes, self._acting_user)
        ticket.refresh_from_db()
        return self._model_to_dict(ticket)

    def _tickets_update(self, params: dict) -> dict:
        from escalated.models import Ticket

        ticket_id = params.get("id")
        if ticket_id is None:
            raise ValueError("ctx.tickets.update requires id")
        data = _contract_fields(params.get("data"), TICKET_UPDATE_FIELDS, "ctx.tickets.update")
        attributes = _ticket_attributes(data, "ctx.tickets.update")

        ticket = Ticket.objects.get(pk=ticket_id)
        self._update_ticket(ticket, attributes)
        ticket.refresh_from_db()
        return self._model_to_dict(ticket)

    def _update_ticket(self, ticket, attributes):
        """
        Each change goes the way the API makes it, through the ticket
        service, so it is logged and announced (ticket.updated,
        ticket.priority_changed, ticket.department_changed,
        ticket.status_changed).
        """
        from escalated.models import Ticket
        from escalated.services.ticket_service import TicketService
        from escalated.signals import ticket_updated

        service = TicketService()
        actor = self._acting_user

        # Fields the service's update does not take: written here, announced
        # as ticket.updated with the rest.
        extra = {}
        if "ticket_type" in attributes and attributes["ticket_type"] != ticket.ticket_type:
            extra["ticket_type"] = {"old": ticket.ticket_type, "new": attributes["ticket_type"]}
            ticket.ticket_type = attributes["ticket_type"]
        if "department" in attributes and attributes["department"] is None and ticket.department_id is not None:
            extra["department_id"] = {"old": ticket.department_id, "new": None}
            ticket.department = None
        if extra:
            ticket.save()

        details = {key: attributes[key] for key in ("subject", "description", "metadata") if key in attributes}
        changed = {key for key, value in details.items() if getattr(ticket, key) != value}
        if changed:
            service.update(ticket, actor, details)
        if extra:
            ticket_updated.send(sender=Ticket, ticket=ticket, user=actor, changes=extra)

        if attributes.get("priority"):
            service.change_priority(ticket, actor, attributes["priority"])
        department = attributes.get("department")
        if department is not None and department.pk != ticket.department_id:
            service.change_department(ticket, actor, department)
        if attributes.get("status"):
            service.change_status(ticket, actor, attributes["status"])

    # ------------------------------------------------------------------
    # Replies
    # ------------------------------------------------------------------

    def _replies_find(self, params: dict) -> dict | None:
        from escalated.models import Reply

        reply_id = params.get("id")
        if reply_id is None:
            raise ValueError("ctx.replies.find requires id")
        reply = Reply.objects.filter(pk=reply_id).first()
        return self._model_to_dict(reply)

    def _replies_query(self, params: dict) -> list:
        from escalated.models import Reply

        filter_spec = params.get("filter") or {}
        if isinstance(filter_spec, dict) and isinstance(filter_spec.get("is_internal"), (str, int)):
            filter_spec = {**filter_spec, "is_internal": filter_spec["is_internal"] in (1, "1", "true", True)}
        lookups = _contract_lookups(filter_spec, REPLY_FILTERS, "ctx.replies.query")
        qs = Reply.objects.filter(**lookups).order_by("pk")[:QUERY_LIMIT]
        return [self._model_to_dict(r) for r in qs]

    def _replies_create(self, params: dict) -> dict:
        from escalated.models import Reply, Ticket

        method = "ctx.replies.create"
        data = _contract_fields(params.get("data"), REPLY_CREATE_FIELDS, method)
        ticket_id = data.get("ticket_id")
        ticket = Ticket.objects.filter(pk=ticket_id).first() if str(ticket_id).isdigit() else None
        if ticket is None:
            raise ValueError(f"{method} requires an existing ticket_id")
        body = _optional_text(data, "body", method)
        if body is None:
            raise ValueError(f"{method} requires body")
        internal = data.get("is_internal") in (True, 1, "1", "true")

        # The author is the acting user (the signed-in user of the request the
        # plugin is serving), or nobody: a plugin never names it. Through the
        # ticket service, like a reply over the API: the status follow-up,
        # activity log, reply.created / note.created, workflows and webhooks.
        from escalated.services.ticket_service import TicketService

        reply = TicketService().reply(ticket, self._acting_user, {"body": body, "is_internal_note": internal})
        reply = Reply.objects.get(pk=reply.pk)
        return self._model_to_dict(reply)

    # ------------------------------------------------------------------
    # Contacts (users)
    # ------------------------------------------------------------------

    def _get_user_model(self):
        from django.contrib.auth import get_user_model

        from escalated.conf import get_setting

        model_path = get_setting("USER_MODEL")
        if model_path:
            from django.apps import apps

            app_label, model_name = model_path.rsplit(".", 1) if "." in model_path else model_path.split(".")
            try:
                return apps.get_model(app_label, model_name)
            except Exception:
                pass
        return get_user_model()

    def _contacts_find(self, params: dict) -> dict | None:
        User = self._get_user_model()
        user_id = params.get("id")
        if user_id is None:
            raise ValueError("ctx.contacts.find requires id")
        user = User.objects.filter(pk=user_id).first()
        return self._model_to_dict(user)

    def _contacts_find_by_email(self, params: dict) -> dict | None:
        User = self._get_user_model()
        email = params.get("email")
        if not email:
            raise ValueError("ctx.contacts.findByEmail requires email")
        user = User.objects.filter(email=email).first()
        return self._model_to_dict(user)

    def _contacts_create(self, params: dict) -> dict:
        User = self._get_user_model()
        method = "ctx.contacts.create"
        data = _contract_fields(params.get("data"), CONTACT_CREATE_FIELDS, method)
        email = _optional_text(data, "email", method)
        if email is None or "@" not in email:
            raise ValueError(f"{method} requires an email address")
        name = _optional_text(data, "name", method)

        # Only the contract's name and email: never a password, a staff or
        # superuser flag, or any other field of the host's user model.
        fields = {field.name for field in User._meta.get_fields()}
        values = {"email": email}
        if User.USERNAME_FIELD != "email" and User.USERNAME_FIELD in fields:
            values[User.USERNAME_FIELD] = email
        if name is not None:
            if "name" in fields:
                values["name"] = name
            elif "first_name" in fields:
                values["first_name"] = name
        user = User.objects.create(**values)
        return self._model_to_dict(user)

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def _tags_all(self, params: dict) -> list:
        from escalated.models import Tag

        return [self._model_to_dict(t) for t in Tag.objects.all()]

    def _tags_create(self, params: dict) -> dict:
        from django.utils.text import slugify

        from escalated.models import Tag

        method = "ctx.tags.create"
        data = _contract_fields(params.get("data"), TAG_CREATE_FIELDS, method)
        name = _optional_text(data, "name", method)
        if name is None:
            raise ValueError(f"{method} requires name")
        values = {"name": name, "slug": _optional_text(data, "slug", method) or slugify(name)}
        color = _optional_text(data, "color", method)
        if color is not None:
            values["color"] = color
        tag = Tag.objects.create(**values)
        return self._model_to_dict(tag)

    # ------------------------------------------------------------------
    # Departments
    # ------------------------------------------------------------------

    def _departments_all(self, params: dict) -> list:
        from escalated.models import Department

        return [self._model_to_dict(d) for d in Department.objects.all()]

    def _departments_find(self, params: dict) -> dict | None:
        from escalated.models import Department

        dept_id = params.get("id")
        if dept_id is None:
            raise ValueError("ctx.departments.find requires id")
        dept = Department.objects.filter(pk=dept_id).first()
        return self._model_to_dict(dept)

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    def _agents_all(self, params: dict) -> list:
        User = self._get_user_model()
        return [self._model_to_dict(u) for u in User.objects.all()]

    def _agents_find(self, params: dict) -> dict | None:
        User = self._get_user_model()
        agent_id = params.get("id")
        if agent_id is None:
            raise ValueError("ctx.agents.find requires id")
        user = User.objects.filter(pk=agent_id).first()
        return self._model_to_dict(user)

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    def _broadcast_to_channel(self, params: dict) -> None:
        channel = params.get("channel")
        event = params.get("event")
        data = params.get("data") or {}
        if not channel:
            raise ValueError("ctx.broadcast.toChannel requires channel")
        if not event:
            raise ValueError("ctx.broadcast.toChannel requires event")
        self._send_broadcast(channel, event, data)
        return None

    def _broadcast_to_user(self, params: dict) -> None:
        user_id = params.get("userId")
        event = params.get("event")
        data = params.get("data") or {}
        if user_id is None:
            raise ValueError("ctx.broadcast.toUser requires userId")
        if not event:
            raise ValueError("ctx.broadcast.toUser requires event")
        self._send_broadcast(f"private-user.{user_id}", event, data)
        return None

    def _broadcast_to_ticket(self, params: dict) -> None:
        ticket_id = params.get("ticketId")
        event = params.get("event")
        data = params.get("data") or {}
        if ticket_id is None:
            raise ValueError("ctx.broadcast.toTicket requires ticketId")
        if not event:
            raise ValueError("ctx.broadcast.toTicket requires event")
        self._send_broadcast(f"private-ticket.{ticket_id}", event, data)
        return None

    def _send_broadcast(self, channel: str, event: str, data: dict) -> None:
        """
        Attempt to broadcast via Django Channels layer if available.
        Gracefully no-ops when Channels is not installed.
        """
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            channel_layer = get_channel_layer()
            if channel_layer is None:
                logger.debug(
                    "ctx.broadcast: no channel layer configured — skipping broadcast to '%s'",
                    channel,
                )
                return

            async_to_sync(channel_layer.group_send)(
                channel,
                {"type": "plugin.event", "event": event, "data": data},
            )
        except ImportError:
            logger.debug(
                "ctx.broadcast: django-channels not installed — skipping broadcast to '%s'",
                channel,
            )
        except Exception as exc:
            logger.warning("ctx.broadcast: failed to broadcast to '%s': %s", channel, exc)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _emit(self, params: dict) -> None:
        hook = params.get("hook")
        data = params.get("data") or {}
        if not hook:
            raise ValueError("ctx.emit requires hook")
        if self._bridge is not None:
            from escalated.plugin_actions import is_reserved_hook

            # A plugin may not impersonate a host event or lifecycle action.
            if is_reserved_hook(hook):
                logger.warning("Dropped ctx.emit of reserved hook %s from %s", hook, self.current_plugin)
                return None
            from escalated.plugin_actions import guard

            guard(hook, lambda: self._bridge.dispatch_action(hook, data))
        return None

    def _ctx_log(self, params: dict) -> None:
        level = params.get("level", "info")
        message = params.get("message", "")
        context = dict(params.get("data") or {})
        context["plugin"] = params.get("plugin", self.current_plugin)

        log_fn = {
            "debug": logger.debug,
            "warn": logger.warning,
            "warning": logger.warning,
            "error": logger.error,
        }.get(level, logger.info)

        log_fn("[plugin:%s] %s %s", context.get("plugin", "?"), message, context)
        return None

    def _current_user(self, params: dict) -> dict | None:
        """
        The user the current host call is served for (the viewer of a widget
        badge), or None -- outside such a call, and always for cron.
        """
        user = self._acting_user
        if user is None:
            return None
        return {
            "id": user.pk,
            "name": (user.get_full_name() if hasattr(user, "get_full_name") else "") or str(user),
            "email": getattr(user, "email", None),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _model_to_dict(instance) -> dict | None:
        """Convert a Django model instance to a plain serialisable dict."""
        if instance is None:
            return None

        try:
            d = {}
            for field in instance._meta.get_fields():
                if field.is_relation:
                    continue
                try:
                    value = getattr(instance, field.name)
                    # Convert non-JSON-serialisable types
                    if hasattr(value, "isoformat"):
                        value = value.isoformat()
                    d[field.name] = value
                except Exception:
                    pass
            return d
        except Exception:
            return {"id": getattr(instance, "pk", None)}
