from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext as _

from escalated.permissions import is_admin, is_agent, user_permissions


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


class EscalatedInertiaShareMiddleware:
    """
    Middleware that shares Escalated props with every Inertia request.
    Add to MIDDLEWARE in your Django settings.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from escalated.conf import get_setting

        if not get_setting("UI_ENABLED"):
            return self.get_response(request)

        return self.get_response(request)

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
                data["permissions"] = user_permissions(request.user)

            try:
                data["guest_tickets_enabled"] = EscalatedSetting.guest_tickets_enabled()
                data["show_powered_by"] = EscalatedSetting.get_bool("show_powered_by", True)
            except Exception:
                pass

            data["features"] = {"newsletters": bool(get_setting("enable_newsletters"))}

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
