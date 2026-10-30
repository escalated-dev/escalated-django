from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from escalated.access import shared_features, shared_permissions
from escalated.permissions import is_admin, is_agent, user_permissions  # noqa: F401


class EnsureAgentMiddleware:
    """
    Middleware that ensures the requesting user is a support agent.
    Apply to agent-facing views.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return HttpResponseRedirect(reverse("login"))

        if not is_agent(request.user) and not is_admin(request.user):
            return HttpResponseForbidden(_("You do not have permission to access the agent dashboard."))

        return None


class EnsureAdminMiddleware:
    """
    Middleware that ensures the requesting user is a support admin.
    Apply to admin-facing views.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return HttpResponseRedirect(reverse("login"))

        if not is_admin(request.user):
            return HttpResponseForbidden(_("You do not have permission to access the admin area."))

        return None


# The statuses the shared frontend's Escalated/Error page has wording for, and
# the generic message each one gets. An exception's or a view's own message
# never reaches the page.
ERROR_PAGE = "Escalated/Error"
ERROR_MESSAGES = {
    403: gettext_lazy("You are not authorized to perform this action."),
    404: gettext_lazy("The requested resource was not found."),
    419: gettext_lazy("Your session has expired. Refresh the page and try again."),
    429: gettext_lazy("Too many requests. Wait a moment and try again."),
    500: gettext_lazy("Something went wrong on our end."),
    503: gettext_lazy("The service is temporarily unavailable. Try again shortly."),
}


def inertia_error_page(request, response):
    """The Escalated/Error page for an Inertia visit to an Escalated route that
    ended in one of ERROR_MESSAGES' statuses, or None to keep ``response``.

    Without it the Inertia client gets an HTML (or plain-text, or JSON) error
    back and can only show it in a modal over the screen the user was on. The
    props are the ones Rails and Laravel send: ``status`` and a generic
    ``message``. Left alone: full page loads and JSON clients (no
    ``X-Inertia``), routes outside the ``escalated`` app, responses that are
    already Inertia pages, and a 500 while ``DEBUG`` is on, so the technical
    500 page stays where a developer wants it.
    """
    from django.conf import settings

    status = response.status_code
    if status not in ERROR_MESSAGES or not request.headers.get("X-Inertia"):
        return None
    if response.headers.get("X-Inertia"):
        return None
    match = getattr(request, "resolver_match", None)
    if match is None or match.app_name != "escalated":
        return None
    if status == 500 and settings.DEBUG:
        return None

    from escalated.rendering import render_page

    page = render_page(request, ERROR_PAGE, {"status": status, "message": str(ERROR_MESSAGES[status])})
    page.status_code = status
    return page


class EscalatedInertiaShareMiddleware:
    """
    Middleware that shares Escalated props with every Inertia request, and
    answers an Inertia visit to an Escalated route that ends in 403, 404, 419,
    429, 500 or 503 with the shared Escalated/Error page.
    Add to MIDDLEWARE in your Django settings.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from escalated.conf import get_setting

        response = self.get_response(request)

        if not get_setting("UI_ENABLED"):
            return response

        return inertia_error_page(request, response) or response

    def process_view(self, request, view_func, view_args, view_kwargs):
        from escalated.conf import get_setting

        if not get_setting("UI_ENABLED"):
            return None

        try:
            from inertia import share

            from escalated.models import EscalatedSetting

            data = {
                "prefix": get_setting("ROUTE_PREFIX") or "support",
                "is_agent": False,
                "is_admin": False,
                "permissions": [],
            }

            if request.user.is_authenticated:
                data["is_agent"] = is_agent(request.user)
                data["is_admin"] = is_admin(request.user)
                # ['*'] for staff while roles & permissions is off (the gates
                # decide); the user's role slugs while it is on.
                data["permissions"] = shared_permissions(request.user, data["is_agent"] or data["is_admin"])

            try:
                data["guest_tickets_enabled"] = EscalatedSetting.guest_tickets_enabled()
                data["show_powered_by"] = EscalatedSetting.get_bool("show_powered_by", True)
            except Exception:
                pass

            data["features"] = {"newsletters": bool(get_setting("enable_newsletters")), **shared_features()}
            data["two_factor_required"] = _two_factor_enrolment_required(request.user, data)

            # Plugin menus, slots and widgets, in the shape the shared
            # frontend's usePluginExtensions() reads (plugin contract).
            try:
                from escalated.plugin_ui_service import plugin_ui

                data["plugins"] = plugin_ui.shared_extensions(
                    is_admin=data["is_admin"],
                    permissions=data["permissions"],
                    user=request.user if request.user.is_authenticated else None,
                )
            except Exception:
                data["plugins"] = {}

            # inertia-django takes shared props as keyword arguments.
            share(request, escalated=data)
        except ImportError:
            pass

        return None


class EscalatedCsrfMiddleware:
    """
    Lets the shared frontend's POSTs pass Django's CSRF check.

    The shared pages send the token as ``X-XSRF-TOKEN`` (Inertia visits, from
    an ``XSRF-TOKEN`` cookie) or ``X-CSRF-TOKEN`` (``fetch`` calls, from a
    ``<meta name="csrf-token">`` tag). Django reads only
    ``settings.CSRF_HEADER_NAME`` (``X-CSRFToken`` by default), so this
    middleware:

    * copies the first non-empty of those headers into
      ``CSRF_HEADER_NAME`` when the request does not already carry it, so
      ``CsrfViewMiddleware`` checks it exactly as it checks its own header
      (a missing or wrong token is still refused); and
    * sets a JavaScript-readable ``XSRF-TOKEN`` cookie holding the CSRF token
      whenever the token is new or changed, unless ``CSRF_COOKIE_NAME`` is
      already ``XSRF-TOKEN``.

    Add it to ``MIDDLEWARE`` directly after
    ``django.middleware.csrf.CsrfViewMiddleware``.
    """

    HEADERS = ("HTTP_X_CSRF_TOKEN", "HTTP_X_XSRF_TOKEN")
    COOKIE_NAME = "XSRF-TOKEN"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        header = settings.CSRF_HEADER_NAME
        if not request.META.get(header):
            for name in self.HEADERS:
                value = request.META.get(name)
                if value:
                    request.META[header] = value
                    break

        response = self.get_response(request)
        self._set_xsrf_cookie(request, response)
        return response

    def _set_xsrf_cookie(self, request, response):
        from django.conf import settings
        from django.middleware.csrf import get_token

        if settings.CSRF_COOKIE_NAME == self.COOKIE_NAME or not request.META.get("CSRF_COOKIE"):
            return
        if self.COOKIE_NAME in request.COOKIES and not request.META.get("CSRF_COOKIE_NEEDS_UPDATE"):
            return
        response.set_cookie(
            self.COOKIE_NAME,
            get_token(request),
            max_age=settings.CSRF_COOKIE_AGE,
            domain=settings.CSRF_COOKIE_DOMAIN,
            path=settings.CSRF_COOKIE_PATH,
            secure=settings.CSRF_COOKIE_SECURE,
            httponly=False,
            samesite=settings.CSRF_COOKIE_SAMESITE,
        )


def _two_factor_enrolment_required(user, data) -> bool:
    """Whether the signed-in staff user must enrol in two-factor before going on."""
    if not user.is_authenticated or not (data.get("is_agent") or data.get("is_admin")):
        return False
    from escalated.services.two_factor_service import TwoFactorService

    return TwoFactorService.required() and TwoFactorService.confirmed_for(user) is None
