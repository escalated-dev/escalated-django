"""
Roles & permissions, two-factor and SSO as install-level switches
(ADR 2026-10-29-configurable-access-features).

The switches are read from ``ESCALATED["ACCESS"]`` in Django settings, else
the ``ESCALATED_*`` environment variable, else off. Never from the settings
table: each one changes who may sign in or what they may do.
"""

from __future__ import annotations

import functools
import os
from fnmatch import fnmatchcase

from django.conf import settings
from django.http import HttpResponseForbidden, HttpResponseNotFound, JsonResponse

FEATURES = {
    "roles_permissions": "ESCALATED_ROLES_PERMISSIONS",
    "two_factor": "ESCALATED_TWO_FACTOR",
    "sso": "ESCALATED_SSO",
}

TRUE_VALUES = {"1", "true", "yes", "on"}


def feature_enabled(feature: str) -> bool:
    configured = (getattr(settings, "ESCALATED", {}) or {}).get("ACCESS", {}) or {}
    value = configured.get(feature)
    if value is None:
        value = configured.get(feature.upper())
    if value is None:
        value = os.environ.get(FEATURES[feature])
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in TRUE_VALUES


def shared_features() -> dict:
    """The ``escalated.features`` entries the shared frontend reads."""
    return {name: feature_enabled(name) for name in FEATURES}


# --------------------------------------------------------------------------
# Route permission map: escalated-laravel's src/Support/RoutePermissions.php,
# keyed by this package's URL names. The first matching pattern wins
# (fnmatch). A staff URL matching nothing is refused, and a test walks the URL
# conf so a new one cannot ship unmapped. Every slug is one seed_permissions
# seeds. An empty list means "staff, no particular permission".
# --------------------------------------------------------------------------

CLOSING_STATUSES = {"resolved", "closed", "reopened"}

BULK_ACTIONS = {
    "status": ["ticket.edit"],
    "priority": ["ticket.edit"],
    "assign": ["ticket.assign"],
    "tags": ["ticket.edit"],
    "tag": ["ticket.edit"],
    "department": ["ticket.edit"],
    "close": ["ticket.edit", "ticket.close"],
    "delete": ["ticket.delete"],
}

VIEW = ["ticket.view"]
EDIT = ["ticket.edit"]


def _resource(name: str, group: str, reads=("index",)) -> list:
    return [(f"admin_{name}_{read}", [f"{group}.view"]) for read in reads] + [(f"admin_{name}_*", [f"{group}.manage"])]


ROUTE_PERMISSIONS: list[tuple[str, list[str]]] = [
    # ---- Personal ----------------------------------------------------------
    ("admin_settings_two_factor", []),
    ("admin_two_factor_*", []),
    # ---- Tickets (admin and agent panels, staff API) -----------------------
    ("agent_dashboard", VIEW),
    ("api:dashboard", VIEW),
    ("api:auth_validate", []),
    ("api:auth_me", []),
    ("api:auth_profile", []),
    ("api:agents", VIEW),
    ("api:departments", VIEW),
    ("api:tags", VIEW),
    ("api:canned_responses", VIEW),
    ("api:realtime_config", VIEW),
    ("api:macros", ["macro.view"]),
    ("agent_mentions*", VIEW),
    ("agent_ticket_list", VIEW),
    ("agent_ticket_show", VIEW),
    ("agent_ticket_follow", VIEW),
    ("agent_ticket_presence", VIEW),
    ("admin_tickets_index", VIEW),
    ("admin_tickets_show", VIEW),
    ("admin_tickets_follow", VIEW),
    ("admin_tickets_presence", VIEW),
    ("admin_ticket_merge_search", VIEW),
    ("admin_ticket_links_index", VIEW),
    ("admin_side_conversations_index", VIEW),
    ("api:ticket_list", VIEW),
    ("api:ticket_show", VIEW),
    ("api:ticket_follow", VIEW),
    ("api:ticket_create", ["ticket.create"]),
    ("admin_ticket_split", ["ticket.create"]),
    ("agent_ticket_update", EDIT),
    ("*_ticket_status", EDIT),
    ("*_tickets_status", EDIT),
    ("*_ticket_priority", EDIT),
    ("*_tickets_priority", EDIT),
    ("*_ticket_tags", EDIT),
    ("*_tickets_tags", EDIT),
    ("*_ticket_department", EDIT),
    ("*_tickets_department", EDIT),
    ("*_ticket_pin", EDIT),
    ("*_tickets_pin", EDIT),
    ("*_ticket_custom_action", EDIT),
    ("*_ticket_subjects_*", EDIT),
    ("*_tickets_subjects_*", EDIT),
    ("admin_ticket_snooze", EDIT),
    ("admin_ticket_unsnooze", EDIT),
    ("admin_ticket_links_store", EDIT),
    ("admin_ticket_links_destroy", EDIT),
    ("api:ticket_status", EDIT),
    ("api:ticket_priority", EDIT),
    ("api:ticket_tags", EDIT),
    ("api:ticket_custom_action", EDIT),
    ("api:ticket_subjects_*", EDIT),
    ("*_ticket_assign", ["ticket.assign"]),
    ("*_tickets_assign", ["ticket.assign"]),
    ("api:ticket_assign", ["ticket.assign"]),
    ("admin_ticket_merge", ["ticket.merge"]),
    ("api:ticket_destroy", ["ticket.delete"]),
    ("*_ticket_macro", ["macro.view", "ticket.edit"]),
    ("*_tickets_macro", ["macro.view", "ticket.edit"]),
    ("api:ticket_macro", ["macro.view", "ticket.edit"]),
    # Bulk: per action, see required_for().
    ("agent_ticket_bulk", VIEW),
    ("admin_tickets_bulk", VIEW),
    ("*_ticket_reply", ["reply.create"]),
    ("*_tickets_reply", ["reply.create"]),
    ("api:ticket_reply", ["reply.create"]),
    ("*_ticket_note", ["reply.create_internal"]),
    ("*_tickets_note", ["reply.create_internal"]),
    ("admin_side_conversations_*", ["reply.create"]),
    ("admin_saved_views_*", VIEW),
    # ---- Live chat ---------------------------------------------------------
    ("agent_chat_active", VIEW),
    ("agent_chat_queue", VIEW),
    ("agent_chat_*", ["reply.create"]),
    # ---- Reports -----------------------------------------------------------
    ("admin_reports_export", ["report.export"]),
    ("admin_reports", ["report.view"]),
    ("admin_reports_*", ["report.view"]),
    # ---- Knowledge base ----------------------------------------------------
    ("admin_articles_index", ["kb.view"]),
    ("admin_articles_create", ["kb.create"]),
    ("admin_articles_edit", ["kb.edit"]),
    ("admin_articles_delete", ["kb.delete"]),
    ("admin_kb_categories_index", ["kb.view"]),
    ("admin_kb_categories_store", ["kb.edit"]),
    ("admin_kb_categories_update", ["kb.edit"]),
    ("admin_kb_categories_delete", ["kb.delete"]),
    # ---- Departments -------------------------------------------------------
    ("admin_departments_index", ["department.view"]),
    ("admin_departments_create", ["department.create"]),
    ("admin_departments_edit", ["department.edit"]),
    ("admin_departments_delete", ["department.delete"]),
    # ---- Macros: anyone who may create one may save it; edits manage -------
    ("admin_macros_index", ["macro.view"]),
    ("admin_macros_create", ["macro.create"]),
    ("admin_macros_*", ["macro.manage"]),
    # ---- Custom objects: schemas manage, records data ----------------------
    ("admin_custom_object_records", ["custom_object.view"]),
    ("admin_custom_object_records_*", ["custom_object.data"]),
    *_resource("custom_objects", "custom_object"),
    # ---- Users -------------------------------------------------------------
    ("admin_users_index", ["user.view"]),
    ("admin_users_role", ["user.manage"]),
    ("admin_audit_logs_index", ["audit.view"]),
    # ---- Admin resources: index => *.view, everything else => *.manage ------
    *_resource("sla_policies", "sla"),
    *_resource("business_hours", "sla"),
    *_resource("escalation_rules", "escalation"),
    *_resource("automations", "automation"),
    ("admin_workflows", ["automation.view"]),
    ("admin_workflow_logs", ["automation.view"]),
    ("admin_workflow_*", ["automation.manage"]),
    *_resource("tags", "tag"),
    *_resource("custom_fields", "custom_field"),
    *_resource("statuses", "settings"),
    *_resource("roles", "role"),
    *_resource("skills", "user"),
    *_resource("capacity", "user"),
    *_resource("webhooks", "webhook", reads=("index", "deliveries")),
    *_resource("api_tokens", "api_token"),
    *_resource("plugins", "plugin"),
    *_resource("canned_responses", "macro"),
    # ---- Settings ----------------------------------------------------------
    ("admin_import_*", ["settings.manage"]),
    ("admin_settings", ["settings.view"]),
    ("admin_settings_*_update", ["settings.manage"]),
    ("admin_settings_update", ["settings.manage"]),
    ("admin_settings_database_test", ["settings.manage"]),
    ("admin_settings_*", ["settings.view"]),
    # ---- Newsletters (ADR 2026-05-19-newsletter-system) --------------------
    ("admin_newsletters_*", ["newsletters.manage"]),
]


def mapped_permissions(url_name: str) -> list[str] | None:
    for pattern, slugs in ROUTE_PERMISSIONS:
        if fnmatchcase(url_name, pattern):
            return list(slugs)
    return None


def _closing(status) -> list[str]:
    return ["ticket.close"] if str(status or "") in CLOSING_STATUSES else []


# Groups with a separate ``.manage`` permission: a write to a URL whose map
# entry is the group's ``.view`` (a screen that shows a form and saves it under
# one name) needs ``.manage``.
MANAGED_GROUPS = {
    "sla",
    "automation",
    "escalation",
    "macro",
    "tag",
    "custom_field",
    "role",
    "user",
    "settings",
    "webhook",
    "api_token",
    "plugin",
    "custom_object",
}


def required_for(url_name: str, data: dict, method: str = "GET") -> list[str] | None:
    """
    The slugs a request needs, or None when its URL is not mapped (refused).
    Body-decided actions are checked per action: a status change to
    resolved/closed/reopened also needs ticket.close, a bulk action needs its
    own permission, and an internal API reply needs reply.create_internal.
    """
    required = mapped_permissions(url_name)
    if required is None:
        return None
    if method.upper() not in ("GET", "HEAD", "OPTIONS"):
        required = [
            f"{slug[: -len('.view')]}.manage"
            if slug.endswith(".view") and slug[: -len(".view")] in MANAGED_GROUPS
            else slug
            for slug in required
        ]
    if url_name in ("agent_ticket_bulk", "admin_tickets_bulk"):
        action = str(data.get("action") or "")
        required += BULK_ACTIONS.get(action, [])
        if action == "status":
            required += _closing(data.get("value"))
    elif url_name == "api:ticket_reply" and str(data.get("is_internal_note", "")).lower() in TRUE_VALUES:
        required = ["reply.create_internal"]
    elif "ticket.edit" in required and "status" in data:
        required += _closing(data.get("status"))
    return list(dict.fromkeys(required))


def user_permissions(user) -> list[str]:
    from escalated.permissions import user_permissions as from_roles

    return sorted(from_roles(user))


def allows(user, slug: str) -> bool:
    """Always while roles & permissions is off (the gates decide); else only via a role."""
    if not feature_enabled("roles_permissions"):
        return True
    return slug in user_permissions(user)


def shared_permissions(user, staff: bool) -> list[str]:
    """``escalated.permissions``: the user's slugs while on, ``['*']`` for staff while off."""
    if not user or not getattr(user, "is_authenticated", False):
        return []
    if not feature_enabled("roles_permissions"):
        return ["*"] if staff else []
    return user_permissions(user)


# --------------------------------------------------------------------------
# The staff guard: wraps every admin, agent and staff API view.
# --------------------------------------------------------------------------


def _request_data(request) -> dict:
    data = {}
    try:
        data.update(request.GET.dict())
        data.update(request.POST.dict())
    except Exception:
        pass
    content_type = request.META.get("CONTENT_TYPE", "")
    if "json" in content_type:
        try:
            import json

            body = json.loads(request.body or b"{}")
            if isinstance(body, dict):
                data.update(body)
        except Exception:
            pass
    return data


def _gate_passes(group: str, request) -> bool:
    from escalated.permissions import is_admin, is_agent

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if group == "admin":
        return is_admin(user)
    if group == "agent":
        return is_agent(user) or is_admin(user)
    if group == "api":
        return getattr(request, "api_token", None) is not None
    return False


def _wants_json(request) -> bool:
    return request.headers.get("X-Inertia") is None and (
        "json" in request.headers.get("Accept", "") or "json" in request.META.get("CONTENT_TYPE", "")
    )


def _forbidden(request, message: str):
    if _wants_json(request) or getattr(request, "api_token", None) is not None:
        return JsonResponse({"message": message}, status=403)
    return HttpResponseForbidden(message)


def enforce_route_permissions(request, url_name: str):
    """A 403 response when the user's roles lack the URL's permission, else None."""
    if not feature_enabled("roles_permissions"):
        return None
    required = required_for(url_name, _request_data(request), request.method)
    if required is None:
        return _forbidden(request, "This route has no permission mapping.")
    granted = set(user_permissions(request.user))
    for slug in required:
        if slug not in granted:
            return _forbidden(request, f"You do not have the required permission: {slug}")
    return None


def staff_view(group: str, url_name: str, view):
    """
    The host gate (inside the view, as before), then with roles & permissions
    on the URL's permission from the user's roles. Both must pass. A request
    the gate refuses goes straight to the view, which refuses it its own way.
    """

    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        if _gate_passes(group, request):
            refused = enforce_route_permissions(request, url_name)
            if refused is not None:
                return refused
        return view(request, *args, **kwargs)

    wrapped.escalated_access_group = group
    wrapped.escalated_url_name = url_name
    return wrapped


def guard_patterns(patterns, group: str, prefix: str = "") -> list:
    """Wraps each URL pattern's view in staff_view (the map key is prefix + name)."""
    for pattern in patterns:
        if getattr(pattern, "callback", None) is None or getattr(pattern.callback, "escalated_access_group", None):
            continue
        pattern.callback = staff_view(group, prefix + (pattern.name or ""), pattern.callback)
    return patterns


def feature_required(feature: str):
    """A view decorator answering 404 while the access switch is off."""

    def decorator(view):
        @functools.wraps(view)
        def wrapped(request, *args, **kwargs):
            if not feature_enabled(feature):
                return HttpResponseNotFound()
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
