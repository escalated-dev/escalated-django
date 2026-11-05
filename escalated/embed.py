"""
Embedding Escalated's admin in the host's own admin panel
(ADR 2026-11-05-embeddable-admin). Optional and off by default: while
``ESCALATED["EMBED"]["ENABLED"]`` is false nothing here changes a route, a
prop, a template or a header.

Turned on, the admin URLs move from ``{ROUTE_PREFIX}/admin/`` to the host's
``PREFIX`` (the host includes ``escalated.embed_urls`` at the site root), run
the host's view decorators (``MIDDLEWARE``) before Escalated's own guards,
and keep their URL names, so the ``route()`` table the shared frontend reads
follows them. Embedded pages carry ``escalated.embed``; every Inertia page
carries the admin menu as ``escalated.navigation``. See docs/embedding-admin.md.

Settings, in ``ESCALATED["EMBED"]`` (keys upper or lower case), else the
environment, else the default:

=====================  ===================================  =================
Key                    Environment variable                 Default
=====================  ===================================  =================
``ENABLED``            ``ESCALATED_EMBED``                  ``False``
``MODE``               ``ESCALATED_EMBED_MODE``             ``"layout"``
``PREFIX``             ``ESCALATED_EMBED_PREFIX``           ``"admin/support"``
``MIDDLEWARE``                                              ``None``
``REPLACE_ADMIN_GATE``                                      ``False``
``LAYOUT``                                                  ``None``
``ROOT_VIEW``                                               ``None``
``FRAME_ANCESTORS``    ``ESCALATED_EMBED_FRAME_ANCESTORS``  ``[]``
=====================  ===================================  =================
"""

from __future__ import annotations

import functools
import os
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

MODES = ("layout", "iframe")

DEFAULTS = {
    "ENABLED": False,
    "MODE": "layout",
    "PREFIX": "admin/support",
    "MIDDLEWARE": None,
    "REPLACE_ADMIN_GATE": False,
    "LAYOUT": None,
    "ROOT_VIEW": None,
    "FRAME_ANCESTORS": [],
}

ENVIRONMENT = {
    "ENABLED": "ESCALATED_EMBED",
    "MODE": "ESCALATED_EMBED_MODE",
    "PREFIX": "ESCALATED_EMBED_PREFIX",
    "FRAME_ANCESTORS": "ESCALATED_EMBED_FRAME_ANCESTORS",
}

TRUE_VALUES = {"1", "true", "yes", "on"}

# Admin URLs that stay at {ROUTE_PREFIX}/admin/ while the admin is embedded:
# the personal two-factor enrolment screens, which every staff user opens for
# their own account. (The newsletter admin lives apart and stays too.)
STAYING_ADMIN_URLS = frozenset(
    {"admin_settings_two_factor", "admin_two_factor_setup", "admin_two_factor_confirm", "admin_two_factor_disable"}
)

EMBEDDED_ATTRIBUTE = "escalated_embedded"


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def embed_admin(
    prefix: str = "admin/support",
    middleware=None,
    layout: str | None = None,
    root_view: str | None = None,
    mode: str = "layout",
    replace_admin_gate: bool = False,
    frame_ancestors=(),
) -> dict:
    """
    The ``ESCALATED["EMBED"]`` setting with embedding switched on::

        from escalated.embed import embed_admin

        ESCALATED = {
            # ...
            "EMBED": embed_admin(
                prefix="admin/support",
                middleware=["django.contrib.admin.views.decorators.staff_member_required"],
                layout="Layouts/AdminLayout",
            ),
        }

    ``middleware`` lists view decorators (or their dotted paths) run on the
    admin views before Escalated's own guards, first listed outermost.
    """
    if mode not in MODES:
        raise ValueError(f"embed_admin() mode must be 'layout' or 'iframe', got {mode!r}.")
    if replace_admin_gate and not middleware:
        raise ValueError("embed_admin(replace_admin_gate=True) needs middleware that restricts the admin to admins.")
    return {
        "ENABLED": True,
        "MODE": mode,
        "PREFIX": prefix,
        "MIDDLEWARE": list(middleware) if middleware is not None else None,
        "REPLACE_ADMIN_GATE": bool(replace_admin_gate),
        "LAYOUT": layout,
        "ROOT_VIEW": root_view,
        "FRAME_ANCESTORS": list(frame_ancestors or []),
    }


def _configured() -> dict:
    value = (getattr(settings, "ESCALATED", {}) or {}).get("EMBED")
    return value if isinstance(value, dict) else {}


def _get(key: str):
    configured = _configured()
    for name in (key, key.lower()):
        if name in configured:
            return configured[name]
    variable = ENVIRONMENT.get(key)
    if variable:
        value = os.environ.get(variable)
        if value is not None and value.strip() != "":
            return value
    default = DEFAULTS[key]
    return list(default) if isinstance(default, list) else default


def _flag(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in TRUE_VALUES


def _name(value) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def enabled() -> bool:
    return _flag(_get("ENABLED"))


def mode() -> str:
    value = str(_get("MODE") or "").strip().lower()
    return value if value in MODES else "layout"


def prefix() -> str:
    """The URL prefix the admin is mounted under while embedded, without slashes."""
    value = str(_get("PREFIX") or "").strip().strip("/")
    return value or DEFAULTS["PREFIX"]


def replaces_admin_gate() -> bool:
    return _flag(_get("REPLACE_ADMIN_GATE"))


def layout() -> str | None:
    return _name(_get("LAYOUT"))


def root_view() -> str | None:
    return _name(_get("ROOT_VIEW"))


def middleware():
    value = _get("MIDDLEWARE")
    if value is None:
        return None
    if isinstance(value, str | bytes) or callable(value):
        value = [value]
    return list(value)


def frame_ancestors() -> list[str]:
    """
    Origins allowed to frame the admin in iframe mode: exact
    ``scheme://host[:port]`` http(s) origins only. ``*``, wildcards, paths and
    credentials are dropped.
    """
    configured = _get("FRAME_ANCESTORS")
    if isinstance(configured, str):
        configured = configured.split(",")
    origins = []
    for entry in configured or []:
        origin = _origin(entry.strip() if isinstance(entry, str) else "")
        if origin is not None and origin not in origins:
            origins.append(origin)
    return origins


def _origin(value: str) -> str | None:
    if not value or "*" in value:
        return None
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/"):
        return None
    origin = f"{parts.scheme.lower()}://{parts.hostname.lower()}"
    return f"{origin}:{port}" if port is not None else origin


def config() -> dict:
    """The effective settings, after the environment and the defaults."""
    return {
        "ENABLED": enabled(),
        "MODE": mode(),
        "PREFIX": prefix(),
        "MIDDLEWARE": middleware(),
        "REPLACE_ADMIN_GATE": replaces_admin_gate(),
        "LAYOUT": layout(),
        "ROOT_VIEW": root_view(),
        "FRAME_ANCESTORS": frame_ancestors(),
    }


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


def host_decorators() -> list:
    """The host's view decorators for the embedded admin, imported, outermost first."""
    from django.utils.module_loading import import_string

    decorators = []
    for entry in middleware() or []:
        decorator = import_string(entry) if isinstance(entry, str) else entry
        if not callable(decorator):
            raise ImproperlyConfigured(f'ESCALATED["EMBED"]["MIDDLEWARE"] entry {entry!r} is not a view decorator.')
        decorators.append(decorator)
    return decorators


def embedded_view(view, decorators=()):
    """
    An admin view as the embedded admin serves it: marked as embedded, then the
    host's decorators, then the view with every guard it already had (the
    admin gate, two-factor and route permissions). The iframe framing headers
    are set on what comes back, and again by EscalatedEmbedMiddleware once the
    whole response is built.
    """
    guarded = view
    for decorator in reversed(list(decorators)):
        guarded = decorator(guarded)

    @functools.wraps(view)
    def embedded(request, *args, **kwargs):
        setattr(request, EMBEDDED_ATTRIBUTE, True)
        return apply_frame_headers(request, guarded(request, *args, **kwargs))

    setattr(embedded, EMBEDDED_ATTRIBUTE, True)
    return embedded


def mount_admin(patterns) -> list:
    """
    The admin URL patterns re-created relative to the host prefix
    (``admin/tags/`` becomes ``tags/``), with the same names and view, each
    view wrapped in :func:`embedded_view`. The given patterns are not changed.
    """
    from django.urls import URLPattern, path

    if replaces_admin_gate() and not middleware():
        raise ImproperlyConfigured(
            'ESCALATED["EMBED"]["REPLACE_ADMIN_GATE"] needs ESCALATED["EMBED"]["MIDDLEWARE"]: with the admin gate '
            "replaced, your view decorators are the only check on who reaches the admin."
        )
    decorators = host_decorators()
    mounted = []
    for pattern in patterns:
        if not isinstance(pattern, URLPattern):
            continue
        route = str(pattern.pattern)
        if route.startswith("admin/"):
            route = route[len("admin/") :]
        mounted.append(path(route, embedded_view(pattern.callback, decorators), pattern.default_args, pattern.name))
    return mounted


def base_url() -> str:
    """Where the embedded admin lives, as an absolute path (``/admin/support``)."""
    from django.urls import get_script_prefix

    return get_script_prefix().rstrip("/") + "/" + prefix()


# --------------------------------------------------------------------------
# Requests and responses
# --------------------------------------------------------------------------


def is_embedded_request(request, view_func=None) -> bool:
    """Whether ``request`` is served by an embedded admin view."""
    if not enabled() or request is None:
        return False
    return bool(getattr(request, EMBEDDED_ATTRIBUTE, False) or getattr(view_func, EMBEDDED_ATTRIBUTE, False))


def _frontend_names() -> dict:
    from escalated.route_list import ROUTES

    names = {}
    for name, route in ROUTES.items():
        if "GET" in route.methods:
            names.setdefault(route.url_name, name)
    return names


def current_route(request) -> str | None:
    """The current page's ``route()`` name as the shared frontend knows it."""
    match = getattr(request, "resolver_match", None)
    if match is None or not match.url_name:
        return None
    return _frontend_names().get(match.url_name) or match.view_name


def shared(request, view_func=None) -> dict:
    """The ``escalated.embed`` prop; shared on every page while embedding is on."""
    embedded = is_embedded_request(request, view_func)
    return {
        "enabled": embedded,
        "mode": mode(),
        "layout": layout(),
        "route": current_route(request) if embedded else None,
        "base_url": base_url(),
        "allowed_origins": frame_ancestors() if mode() == "iframe" else [],
    }


def root_view_for(request) -> str | None:
    """The Inertia root template for this response: ROOT_VIEW on embedded pages only."""
    if not is_embedded_request(request):
        return None
    return root_view()


def frame_ancestors_directive() -> str:
    return " ".join(["frame-ancestors 'self'", *frame_ancestors()])


def apply_frame_headers(request, response):
    """
    iframe mode, embedded responses only: allow the listed origins to frame
    the page (``Content-Security-Policy: frame-ancestors 'self' <origins>``)
    and drop ``X-Frame-Options``, which ``frame-ancestors`` replaces. A CSP
    the host already sent is kept and this one is added as a second policy.
    Nothing else is touched.
    """
    if response is None or mode() != "iframe" or not is_embedded_request(request):
        return response
    if response.has_header("X-Frame-Options"):
        del response["X-Frame-Options"]
    # Django's XFrameOptionsMiddleware leaves exempt responses alone.
    response.xframe_options_exempt = True
    directive = frame_ancestors_directive()
    existing = response.get("Content-Security-Policy")
    if not existing:
        response["Content-Security-Policy"] = directive
    elif directive not in [policy.strip() for policy in existing.split(",")]:
        response["Content-Security-Policy"] = f"{existing}, {directive}"
    return response


# --------------------------------------------------------------------------
# The admin menu
# --------------------------------------------------------------------------

# key (also the icon key), label, the frontend's route name, this package's
# URL name, position. Labels and positions match the standalone sidebar.
NAVIGATION = [
    ("reports", "Reports", "escalated.admin.reports", "admin_reports", 10),
    ("tickets", "Tickets", "escalated.admin.tickets.index", "admin_tickets_index", 20),
    ("departments", "Departments", "escalated.admin.departments.index", "admin_departments_index", 30),
    ("sla-policies", "SLA Policies", "escalated.admin.sla-policies.index", "admin_sla_policies_index", 40),
    ("knowledge-base", "Knowledge Base", "escalated.admin.kb-articles.index", "admin_articles_index", 45),
    (
        "escalation-rules",
        "Escalation Rules",
        "escalated.admin.escalation-rules.index",
        "admin_escalation_rules_index",
        50,
    ),
    ("workflows", "Workflows", "escalated.admin.workflows.index", "admin_workflows", 53),
    ("automations", "Automations", "escalated.admin.automations.index", "admin_automations_index", 53.5),
    ("webhooks", "Webhooks", "escalated.admin.webhooks.index", "admin_webhooks_index", 54),
    ("tags", "Tags", "escalated.admin.tags.index", "admin_tags_index", 60),
    ("custom-fields", "Custom Fields", "escalated.admin.custom-fields.index", "admin_custom_fields_index", 62),
    ("statuses", "Statuses", "escalated.admin.statuses.index", "admin_statuses_index", 64),
    (
        "canned-responses",
        "Canned Responses",
        "escalated.admin.canned-responses.index",
        "admin_canned_responses_index",
        70,
    ),
    ("macros", "Macros", "escalated.admin.macros.index", "admin_macros_index", 80),
    ("newsletters", "Newsletters", "escalated.admin.newsletters.index", "admin_newsletters_index", 81),
    ("skills", "Skills", "escalated.admin.skills.index", "admin_skills_index", 82),
    ("users", "Users", "escalated.admin.users.index", "admin_users_index", 83),
    ("roles", "Roles", "escalated.admin.roles.index", "admin_roles_index", 84),
    ("capacity", "Capacity", "escalated.admin.capacity.index", "admin_capacity_index", 85),
    ("business-hours", "Business Hours", "escalated.admin.business-hours.index", "admin_business_hours_index", 86),
    ("audit-log", "Audit Log", "escalated.admin.audit-log", "admin_audit_logs_index", 88),
    ("api-tokens", "API Tokens", "escalated.admin.api-tokens.index", "admin_api_tokens_index", 90),
    ("custom-objects", "Custom Objects", "escalated.admin.custom-objects.index", "admin_custom_objects_index", 92),
    ("plugins", "Plugins", "escalated.admin.plugins.index", "admin_plugins_index", 95),
    ("import", "Import", "escalated.admin.import.index", "admin_import_index", 97),
    ("settings", "Settings", "escalated.admin.settings", "admin_settings", 100),
]


def _feature_on(key: str) -> bool:
    """Screens whose URL is registered but answers 404 while their feature is off."""
    from escalated.access import feature_enabled
    from escalated.conf import get_setting

    if key == "roles":
        return feature_enabled("roles_permissions")
    if key == "newsletters":
        return bool(get_setting("enable_newsletters"))
    if key == "plugins":
        return bool(get_setting("PLUGINS_ENABLED"))
    if key == "knowledge-base":
        from escalated.kb_guards import kb_enabled

        return kb_enabled()
    return True


def _item(key, label, route, url, icon, position, path) -> dict:
    target = urlsplit(url).path or url
    return {
        "key": key,
        "label": label,
        "route": route,
        "url": url,
        "icon": icon,
        "position": position,
        "active": bool(path) and (path == target or path.startswith(target.rstrip("/") + "/")),
        "badge": None,
        "plugin": None,
        "children": [],
    }


def admin_navigation(user=None, request=None) -> list[dict]:
    """
    Escalated's admin menu for ``user`` (default: ``request.user``), for a host
    to list in its own sidebar: ``key, label, route, url, icon, position,
    active, badge, plugin, children``, sorted by position.

    Filtered so it never links to a screen that would answer 403 or 404: empty
    for a user who fails Escalated's admin gate (any signed-in user while the
    host replaced the gate), screens whose URL is not registered or whose
    feature is off are left out, and while roles & permissions is on each item
    needs the permissions its URL requires. Plugin admin menu items are merged
    in. Works whether or not embedding is on; the URLs follow the admin.
    """
    from django.urls import NoReverseMatch, reverse

    from escalated.access import feature_enabled, required_for, shared_permissions, user_permissions
    from escalated.permissions import is_admin

    if user is None and request is not None:
        user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    if not is_admin(user) and not (enabled() and replaces_admin_gate()):
        return []

    path = getattr(request, "path", "") if request is not None else ""
    granted = set(user_permissions(user)) if feature_enabled("roles_permissions") else None

    items = []
    for key, label, route, url_name, position in NAVIGATION:
        try:
            url = reverse(f"escalated:{url_name}")
        except NoReverseMatch:
            continue
        if not _feature_on(key):
            continue
        if granted is not None:
            required = required_for(url_name, {}, "GET")
            if required is None or not set(required) <= granted:
                continue
        items.append(_item(key, label, route, url, key, position, path))

    for index, plugin in enumerate(_plugin_items(user, shared_permissions(user, True))):
        url = plugin.get("route")
        if not isinstance(url, str) or not url:
            continue
        icon = plugin.get("icon")
        item = _item(
            f"plugin:{plugin.get('plugin') or 'native'}:{index}",
            str(plugin.get("label") or ""),
            None,
            url,
            icon if isinstance(icon, str) else None,
            plugin.get("position", 100),
            path,
        )
        item["badge"] = plugin.get("badge")
        item["plugin"] = plugin.get("plugin")
        item["children"] = [
            {
                "label": str(child.get("label") or ""),
                "url": str(child.get("url") or child.get("route") or ""),
                "icon": child.get("icon"),
            }
            for child in plugin.get("submenu") or []
            if isinstance(child, dict)
        ]
        items.append(item)

    # Stable: items with the same position keep their order.
    return sorted(items, key=lambda item: item["position"])


def _plugin_items(user, permissions) -> list[dict]:
    """Plugin menu items for the admin section, filtered as the plugin contract does."""
    from escalated.conf import get_setting

    if not get_setting("PLUGINS_ENABLED"):
        return []
    try:
        from escalated.plugin_ui_service import plugin_ui

        menu = plugin_ui.shared_extensions(is_admin=True, permissions=permissions, user=user).get("menuItems") or []
    except Exception:
        return []
    return [item for item in menu if (item.get("section") or "admin") == "admin"]
