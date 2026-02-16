"""
Admin views for managing API tokens.

Provides a full CRUD interface for API tokens using Inertia.js rendering,
following the same pattern as other admin views in the package.
"""

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone

from escalated.api_serializers import ApiTokenSerializer
from escalated.conf import get_setting
from escalated.models import ApiToken
from escalated.permissions import is_admin, is_agent

try:
    from inertia import render
except ImportError:
    # Fallback for environments without inertia-django
    render = None

User = get_user_model()


def _require_admin(request):
    """Return an error response if user is not admin, else None."""
    if not request.user.is_authenticated:
        return redirect("login")
    if not is_admin(request.user):
        return HttpResponseForbidden("Admin access required.")
    return None


def _get_agent_users():
    """Return list of users who are agents or admins."""
    users = User.objects.filter(is_active=True)
    return [
        {"id": u.pk, "name": u.get_full_name() or u.username, "email": u.email}
        for u in users
        if is_agent(u) or is_admin(u)
    ]


@login_required
def api_tokens_index(request):
    """
    List all API tokens with their associated users.
    """
    check = _require_admin(request)
    if check:
        return check

    tokens = ApiToken.objects.order_by("-created_at")
    token_data = ApiTokenSerializer.serialize_list(tokens)

    if render:
        return render(request, "Escalated/Admin/ApiTokens/Index", props={
            "tokens": token_data,
            "users": _get_agent_users(),
            "api_enabled": get_setting("API_ENABLED"),
        })

    # JSON fallback for non-Inertia setups
    return JsonResponse({
        "tokens": token_data,
        "users": _get_agent_users(),
        "api_enabled": get_setting("API_ENABLED"),
    })


@login_required
def api_tokens_create(request):
    """
    Create a new API token.

    Accepts POST with:
        name (required), user_id (required), abilities (list), expires_in_days (optional int)
    """
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    # Parse body — support both form-encoded and JSON
    if request.content_type and "json" in request.content_type:
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            data = {}
    else:
        data = request.POST

    name = (data.get("name") or "").strip() if isinstance(data, dict) else (data.get("name", "")).strip()
    user_id = data.get("user_id")

    if not name:
        return JsonResponse(
            {"message": "Validation failed.", "errors": {"name": "Name is required."}},
            status=422,
        )
    if not user_id:
        return JsonResponse(
            {"message": "Validation failed.", "errors": {"user_id": "User ID is required."}},
            status=422,
        )

    try:
        user = User.objects.get(pk=int(user_id))
    except (User.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"message": "User not found."}, status=404)

    # Parse abilities
    abilities = data.get("abilities", ["*"])
    if isinstance(abilities, str):
        try:
            abilities = json.loads(abilities)
        except (json.JSONDecodeError, ValueError):
            abilities = ["*"]

    # Parse expiry
    expires_in_days = data.get("expires_in_days")
    expires_at = None
    if expires_in_days:
        try:
            days = int(expires_in_days)
            if 1 <= days <= 365:
                expires_at = timezone.now() + timezone.timedelta(days=days)
        except (ValueError, TypeError):
            pass

    result = ApiToken.create_token(
        user=user,
        name=name,
        abilities=abilities,
        expires_at=expires_at,
    )

    return JsonResponse(
        {
            "message": "API token created.",
            "plain_text_token": result["plain_text_token"],
            "token": ApiTokenSerializer.serialize(result["token"]),
        },
        status=201,
    )


@login_required
def api_tokens_update(request, token_id):
    """
    Update an existing API token (name and/or abilities).

    Accepts POST/PUT/PATCH with:
        name (optional), abilities (optional list)
    """
    check = _require_admin(request)
    if check:
        return check

    if request.method not in ("POST", "PUT", "PATCH"):
        return HttpResponseForbidden("Method not allowed")

    try:
        token = ApiToken.objects.get(pk=token_id)
    except ApiToken.DoesNotExist:
        return HttpResponseNotFound("Token not found")

    # Parse body
    if request.content_type and "json" in request.content_type:
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            data = {}
    else:
        data = request.POST

    name = data.get("name")
    if name is not None:
        token.name = name.strip() if isinstance(name, str) else name

    abilities = data.get("abilities")
    if abilities is not None:
        if isinstance(abilities, str):
            try:
                abilities = json.loads(abilities)
            except (json.JSONDecodeError, ValueError):
                abilities = None
        if abilities is not None:
            token.abilities = abilities

    token.save()

    return JsonResponse({"message": "Token updated.", "token": ApiTokenSerializer.serialize(token)})


@login_required
def api_tokens_destroy(request, token_id):
    """
    Revoke (delete) an API token.
    """
    check = _require_admin(request)
    if check:
        return check

    if request.method not in ("POST", "DELETE"):
        return HttpResponseForbidden("Method not allowed")

    try:
        token = ApiToken.objects.get(pk=token_id)
        token.delete()
    except ApiToken.DoesNotExist:
        pass

    return JsonResponse({"message": "Token revoked."})
