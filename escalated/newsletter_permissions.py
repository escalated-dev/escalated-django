"""Permission checks for newsletter admin HTTP endpoints."""

from __future__ import annotations

from django.http import HttpResponseForbidden

from escalated.models import Role
from escalated.permissions import is_admin


def user_has_newsletter_permission(user, slug: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    if is_admin(user):
        return True
    return Role.objects.filter(users=user, permissions__slug=slug).exists()


def require_newsletter_permission(request, slug: str):
    """Return HttpResponseForbidden when the user lacks the slug; else None."""
    if user_has_newsletter_permission(request.user, slug):
        return None
    return HttpResponseForbidden("Insufficient permissions.")
