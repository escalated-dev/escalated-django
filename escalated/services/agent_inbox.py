"""The agent panel's ``inbox`` and ``queue`` props (shared frontend
docs/agent-panel.md), as escalated-laravel's AgentInbox sends them, and the
ticket list filters they count through.

Every number is a count over the same filters the agent ticket list applies,
through the Ticket manager's visibility scope, so it is what the agent would
see by opening that list. Rail counts (``counts``, ``views``) are of
unresolved, unsnoozed tickets; ``stats`` are for the current queue.
"""

import hashlib
import json
import re
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from escalated.conf import get_setting

SESSION_KEY = "escalated_agent_inbox_queue"

# Saved views beyond this many are not listed, so the counts stay bounded.
MAX_SAVED_VIEWS = 50

# How close a due SLA target has to be for the ticket to be "at risk".
SLA_AT_RISK_MINUTES = 60

MAX_UPDATED_WITHIN_HOURS = 8760

# Query keys that pick a page or an order, never which tickets are in a queue.
PRESENTATION_KEYS = {"page", "per_page", "view"}

BOOLEAN_VALUES = {"0", "1", "true", "false", "on", "off", "yes", "no"}
TRUE_VALUES = {"1", "true", "on", "yes"}

WORKSPACE_KEYS = ("mine", "unassigned", "all")


def flag(filters, key):
    """``1``, ``true``, ``on`` or ``yes``, as escalated-laravel's boolean filters read."""
    value = filters.get(key)
    if value is True:
        return True
    return str(value).lower() in TRUE_VALUES if value is not None else False


def filter_errors(filters):
    """Field errors for the filters added for the agent panel, or ``{}``."""
    errors = {}
    for key in ("open", "sla_at_risk", "resolved_today"):
        value = filters.get(key)
        if value in (None, ""):
            continue
        if str(value).lower() not in BOOLEAN_VALUES:
            errors[key] = [f"The {key.replace('_', ' ')} field must be true or false."]
    hours = filters.get("updated_within_hours")
    if hours not in (None, ""):
        if not re.fullmatch(r"\d+", str(hours)) or not 1 <= int(hours) <= MAX_UPDATED_WITHIN_HOURS:
            errors["updated_within_hours"] = ["The updated within hours field must be between 1 and 8760."]
    return errors


def apply_filters(tickets, filters, user=None):
    """The agent ticket list's filters, applied to a ticket queryset."""
    if filters.get("status"):
        tickets = tickets.filter(status=filters["status"])
    if flag(filters, "open"):
        tickets = tickets.open()
    if filters.get("priority"):
        tickets = tickets.filter(priority=filters["priority"])
    if filters.get("ticket_type"):
        tickets = tickets.filter(ticket_type=filters["ticket_type"])
    if filters.get("assigned_to") not in (None, ""):
        tickets = tickets.filter(assigned_to_id=filters["assigned_to"])
    if flag(filters, "unassigned"):
        tickets = tickets.filter(assigned_to__isnull=True)
    department = filters.get("department_id") or filters.get("department")
    if department:
        tickets = tickets.filter(department_id=department)
    if filters.get("tag"):
        tickets = tickets.filter(tags__slug=filters["tag"])
    if filters.get("search"):
        tickets = tickets.search(filters["search"])
    if flag(filters, "sla_breached"):
        tickets = tickets.breached_sla()
    if flag(filters, "sla_at_risk"):
        tickets = sla_at_risk(tickets)
    if flag(filters, "resolved_today"):
        start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        tickets = tickets.filter(resolved_at__gte=start)
    hours = filters.get("updated_within_hours")
    if hours not in (None, "") and re.fullmatch(r"\d+", str(hours)):
        tickets = tickets.filter(updated_at__gte=timezone.now() - timedelta(hours=int(hours)))
    if filters.get("following") and user is not None:
        tickets = tickets.filter(ticket_followers__user=user)

    # Snoozed tickets are left out unless asked for, as escalated-laravel's list does.
    if flag(filters, "snoozed"):
        return tickets.snoozed()
    if flag(filters, "include_snoozed"):
        return tickets
    return tickets.not_snoozed()


def sla_at_risk(tickets):
    """Unresolved tickets whose SLA is already breached, or whose first
    response (still unsent) or resolution falls due within the hour."""
    soon = timezone.now() + timedelta(minutes=SLA_AT_RISK_MINUTES)
    return tickets.open().filter(
        Q(sla_first_response_breached=True)
        | Q(sla_resolution_breached=True)
        | Q(first_response_at__isnull=True, first_response_due_at__lte=soon)
        | Q(resolution_due_at__lte=soon)
    )


def _comparable(filters):
    """Filters as strings, without empty values or order, for comparing a URL with a view."""
    clean = {}
    for key, value in (filters or {}).items():
        if value is None or value == "" or value is False or key in PRESENTATION_KEYS:
            continue
        if isinstance(value, (list, tuple)):
            clean[key] = ",".join(sorted(str(v) for v in value))
        else:
            clean[key] = "1" if value is True else str(value)
    return dict(sorted(clean.items()))


class AgentInbox:
    def __init__(self, agent):
        self.agent = agent
        self.me = agent.pk
        self._views = None

    def normalise_filters(self, filters):
        """Translate ``assigned=me`` and ``assigned_to=me`` into the agent's id.

        The list's older ``assigned=unassigned`` and ``assigned=<id>`` keep working.
        """
        filters = dict(filters)
        assigned = filters.pop("assigned", None)
        if assigned == "me" or filters.get("assigned_to") == "me":
            filters["assigned_to"] = self.me
        elif assigned == "unassigned":
            filters["unassigned"] = 1
        elif assigned not in (None, ""):
            filters.setdefault("assigned_to", assigned)
        return filters

    def queue_for(self, filters):
        """The queue a list request shows: ``{key, title, filters}``."""
        views = self.views()

        if filters.get("view") not in (None, ""):
            view = next((v for v in views if str(v["id"]) == str(filters["view"])), None)
            if view:
                return self._view_queue(view)

        selection = _comparable(filters)
        if selection:
            view = next((v for v in views if v["filters"] and _comparable(v["filters"]) == selection), None)
            if view:
                return self._view_queue(view)

        if filters.get("assigned_to") not in (None, "") and str(filters["assigned_to"]) == str(self.me):
            return self._workspace_queue("mine")
        if flag(filters, "unassigned"):
            return self._workspace_queue("unassigned")
        return self._workspace_queue("all")

    def list_filters(self, filters, queue):
        """The filters the list applies: the request's, over a view picked by id."""
        if filters.get("view") not in (None, "") and queue["key"].startswith("view:"):
            rest = {k: v for k, v in filters.items() if k != "view"}
            return {**queue["filters"], **rest}
        return filters

    def remember(self, session, queue):
        """Remember the queue for the ticket page, which is opened from the list."""
        if session is not None:
            session[SESSION_KEY] = queue["key"]

    def recalled(self, session):
        """The queue last shown in the list, or All tickets."""
        key = session.get(SESSION_KEY) if session is not None else None
        if not isinstance(key, str):
            return self._workspace_queue("all")
        if key.startswith("view:"):
            # The view may have been deleted or unshared since.
            view = next((v for v in self.views() if str(v["id"]) == key[5:]), None)
            return self._view_queue(view) if view else self._workspace_queue("all")
        return self._workspace_queue(key)

    @staticmethod
    def queue_prop(queue):
        return {"key": queue["key"], "title": queue["title"]}

    def inbox_props(self, queue):
        """``{"inbox": ...}``, or nothing in cloud mode: there the tickets live in
        the hosted service, and counting the local table would show zeroes."""
        if get_setting("MODE") == "cloud":
            return {}
        return {"inbox": self.summary(queue)}

    def summary(self, queue):
        seconds = int(get_setting("AGENT_INBOX_CACHE_SECONDS") or 0)
        if seconds <= 0:
            return self._build(queue)
        digest = hashlib.sha1(
            json.dumps([queue["key"], _comparable(queue["filters"])], default=str).encode()
        ).hexdigest()
        key = f"escalated:agent_inbox:{self.me}:{translation.get_language()}:{digest}"
        value = cache.get(key)
        if value is None:
            value = self._build(queue)
            cache.set(key, value, seconds)
        return value

    def views(self):
        """Built-in views, then the agent's own and shared saved views."""
        if self._views is None:
            self._views = self._built_in_views() + self._saved_views()
        return self._views

    def _built_in_views(self):
        names = {
            "urgent": _("Urgent"),
            "sla_at_risk": _("SLA at risk"),
            "waiting_on_me": _("Waiting on me"),
            "waiting_on_customer": _("Waiting on customer"),
            "recently_updated": _("Recently updated"),
        }
        built_in = [
            ("urgent", {"priority": "urgent", "open": 1}),
            ("sla_at_risk", {"sla_at_risk": 1}),
            ("waiting_on_me", {"assigned_to": self.me, "status": "waiting_on_agent"}),
            ("waiting_on_customer", {"assigned_to": self.me, "status": "waiting_on_customer"}),
            ("recently_updated", {"open": 1, "updated_within_hours": 24, "sort_by": "updated_at"}),
        ]
        return [{"id": view_id, "name": str(names[view_id]), "filters": filters} for view_id, filters in built_in]

    def _saved_views(self):
        from escalated.models import SavedView

        rows = SavedView.objects.filter(Q(user_id=self.me) | Q(is_shared=True)).order_by("position", "id")[
            :MAX_SAVED_VIEWS
        ]
        return [
            {
                "id": view.pk,
                "name": view.name,
                "filters": self.normalise_filters(view.filters if isinstance(view.filters, dict) else {}),
            }
            for view in rows
        ]

    def _build(self, queue):
        base = dict(queue["filters"])
        return {
            "counts": {
                "mine": self._count_open({"assigned_to": self.me}),
                "unassigned": self._count_open({"unassigned": 1}),
                "all": self._count_open({}),
            },
            "views": [
                {"id": v["id"], "name": v["name"], "count": self._count_open(v["filters"]), "filters": v["filters"]}
                for v in self.views()
            ],
            # Each stat is the list the tile opens: the queue plus the tile's filters.
            "stats": {
                "open": self._count({**base, "status": "open"}),
                "urgent": self._count({**base, "priority": "urgent", "open": 1}),
                "sla_at_risk": self._count({**base, "sla_at_risk": 1}),
                "resolved_today": self._count({**base, "status": "resolved", "resolved_today": 1}),
            },
        }

    def _view_queue(self, view):
        return {"key": f"view:{view['id']}", "title": view["name"], "filters": view["filters"]}

    def _workspace_queue(self, key):
        if key not in WORKSPACE_KEYS:
            key = "all"
        titles = {"mine": _("My inbox"), "unassigned": _("Unassigned"), "all": _("All tickets")}
        filters = {"mine": {"assigned_to": self.me}, "unassigned": {"unassigned": 1}}.get(key, {})
        return {"key": key, "title": str(titles[key]), "filters": filters}

    def _count_open(self, filters):
        """Unresolved tickets, unless the filters ask for a status themselves."""
        if not filters.get("status"):
            filters = {**filters, "open": 1}
        return self._count(filters)

    def _count(self, filters):
        from escalated.models import Ticket

        return apply_filters(Ticket.objects.all(), filters, self.agent).distinct().count()
