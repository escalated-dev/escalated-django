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

    def set_bridge(self, bridge) -> None:
        self._bridge = bridge

    def set_current_plugin(self, plugin: str) -> None:
        self.current_plugin = plugin

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

        filter_spec = params.get("filter") or {}
        qs = Ticket.objects.filter(**filter_spec)
        return [self._model_to_dict(t) for t in qs]

    def _tickets_create(self, params: dict) -> dict:
        from escalated.models import Ticket

        data = params.get("data")
        if not data:
            raise ValueError("ctx.tickets.create requires data")
        ticket = Ticket.objects.create(**data)
        return self._model_to_dict(ticket)

    def _tickets_update(self, params: dict) -> dict:
        from escalated.models import Ticket

        ticket_id = params.get("id")
        data = params.get("data")
        if ticket_id is None:
            raise ValueError("ctx.tickets.update requires id")
        if not data:
            raise ValueError("ctx.tickets.update requires data")

        ticket = Ticket.objects.get(pk=ticket_id)
        for field, value in data.items():
            setattr(ticket, field, value)
        ticket.save()
        ticket.refresh_from_db()
        return self._model_to_dict(ticket)

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
        qs = Reply.objects.filter(**filter_spec)
        return [self._model_to_dict(r) for r in qs]

    def _replies_create(self, params: dict) -> dict:
        from escalated.models import Reply

        data = params.get("data")
        if not data:
            raise ValueError("ctx.replies.create requires data")
        reply = Reply.objects.create(**data)
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
        data = params.get("data")
        if not data:
            raise ValueError("ctx.contacts.create requires data")
        user = User.objects.create(**data)
        return self._model_to_dict(user)

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def _tags_all(self, params: dict) -> list:
        from escalated.models import Tag

        return [self._model_to_dict(t) for t in Tag.objects.all()]

    def _tags_create(self, params: dict) -> dict:
        from escalated.models import Tag

        data = params.get("data")
        if not data:
            raise ValueError("ctx.tags.create requires data")
        tag = Tag.objects.create(**data)
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
            self._bridge.dispatch_action(hook, data)
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
        Return the current request user if available.

        Because the bridge operates outside the request/response cycle we
        cannot reliably access request.user here.  We return None and let
        the plugin handle the absence gracefully.
        """
        return None

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
