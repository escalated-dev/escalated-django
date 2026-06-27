"""
General JSON API authentication endpoints for the Flutter app and
integrations.

Credential handling is delegated to host-app callbacks configured via the
ESCALATED settings (``API_AUTHENTICATOR`` / ``API_REGISTRAR`` /
``API_TOKEN_REFRESHER`` / ``API_PROFILE_UPDATER`` / ``API_LOGOUT``). Escalated
owns no passwords or sessions, so it ships no password-hashing dependency. An
unconfigured callback responds 501; a callback returning a falsy value is
treated as an authentication failure (401).
"""

import json

from django.http import JsonResponse
from django.utils.module_loading import import_string
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from escalated.conf import get_setting


def public_api(view):
    """Mark a view as exempt from API-token authentication (login/register/etc)."""
    view._escalated_api_public = True
    return view


def _resolve(name):
    value = get_setting(name)
    if value is None:
        return None
    if callable(value):
        return value
    if isinstance(value, str):
        return import_string(value)
    return None


def _json_body(request):
    if not request.body:
        return {}
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _bearer(request):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return ""


def _delegate(setting, *args):
    callback = _resolve(setting)
    if callback is None:
        return JsonResponse({"error": "Authentication is not configured"}, status=501)
    result = callback(*args)
    if not result:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    return JsonResponse({"data": result})


@public_api
@require_POST
def api_auth_login(request):
    return _delegate("API_AUTHENTICATOR", _json_body(request))


@public_api
@require_POST
def api_auth_register(request):
    return _delegate("API_REGISTRAR", _json_body(request))


@public_api
@require_POST
def api_auth_refresh(request):
    return _delegate("API_TOKEN_REFRESHER", _bearer(request))


@public_api
@require_POST
def api_auth_logout(request):
    callback = _resolve("API_LOGOUT")
    if callback is not None:
        callback(_bearer(request))
    return JsonResponse({"data": {"success": True}})


@require_http_methods(["POST", "PATCH"])
def api_auth_profile(request):
    return _delegate("API_PROFILE_UPDATER", request.user, _json_body(request))


@require_GET
def api_auth_me(request):
    user = request.user
    return JsonResponse(
        {
            "data": {
                "id": user.pk,
                "name": getattr(user, "get_full_name", lambda: str(user))(),
                "email": getattr(user, "email", ""),
            }
        }
    )
