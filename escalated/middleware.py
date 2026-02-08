from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse

from escalated.permissions import is_agent, is_admin


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
            return HttpResponseForbidden(
                "You do not have permission to access the agent dashboard."
            )

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
            return HttpResponseForbidden(
                "You do not have permission to access the admin area."
            )

        return None
