from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext as _

from escalated.permissions import is_admin, is_agent


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
            }

            if request.user.is_authenticated:
                data["is_agent"] = is_agent(request.user)
                data["is_admin"] = is_admin(request.user)

            try:
                data["guest_tickets_enabled"] = EscalatedSetting.guest_tickets_enabled()
                data["show_powered_by"] = EscalatedSetting.get_bool("show_powered_by", True)
            except Exception:
                pass

            share(request, "escalated", data)
        except ImportError:
            pass

        return None
