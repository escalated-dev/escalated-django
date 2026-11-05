"""
A host back office for the embeddable-admin tests (ADR
2026-11-05-embeddable-admin): the view decorators a host lists in
``ESCALATED["EMBED"]["MIDDLEWARE"]``, a host middleware that sends its own
framing headers, and the settings that switch embedding on.
"""

import importlib
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.test import override_settings
from django.urls import clear_url_caches

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

SHARE = "escalated.middleware.EscalatedInertiaShareMiddleware"
EMBED_MIDDLEWARE = "escalated.middleware.EscalatedEmbedMiddleware"


def host_admin(view):
    """The host's own admin guard: signed in, not refused, and it marks the response."""

    @wraps(view)
    def guarded(request, *args, **kwargs):
        if request.headers.get("X-Host-Deny"):
            return HttpResponseForbidden("Refused by the host.")
        if not request.user.is_authenticated:
            return HttpResponse("Host login required.", status=401)
        response = view(request, *args, **kwargs)
        response["X-Host-Admin"] = "1"
        return response

    return guarded


def host_backoffice_only(view):
    """A host gate that decides on its own who is an admin: first name "Host"."""

    @wraps(view)
    def guarded(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated or user.first_name != "Host":
            return HttpResponseForbidden("Back office staff only.")
        return view(request, *args, **kwargs)

    return guarded


class HostFramingHeadersMiddleware:
    """A host middleware that refuses framing and sends its own CSP on every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-Frame-Options"] = "DENY"
        response["Content-Security-Policy"] = "default-src 'self'"
        return response


def reload_urls():
    import escalated.embed_urls
    import escalated.urls
    import tests.urls
    import tests.urls_embed

    importlib.reload(escalated.urls)
    importlib.reload(escalated.embed_urls)
    importlib.reload(tests.urls)
    importlib.reload(tests.urls_embed)
    clear_url_caches()

    from escalated import route_list

    route_list._cache.clear()


@contextmanager
def embedded(middleware=None, urlconf="tests.urls_embed", extra=None, **embed):
    """Settings with the admin embedded, and the URLconf rebuilt from them."""
    config = {"ENABLED": True, **embed}
    escalated_settings = {**settings.ESCALATED, "EMBED": config, **(extra or {})}
    overrides = {"ESCALATED": escalated_settings, "ROOT_URLCONF": urlconf}
    if middleware is not None:
        overrides["MIDDLEWARE"] = middleware
    try:
        with override_settings(**overrides):
            reload_urls()
            yield
    finally:
        reload_urls()
