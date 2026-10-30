"""Permission checks for newsletter admin HTTP endpoints."""

from __future__ import annotations

from django.http import HttpResponseForbidden

from escalated.access import allows


def user_has_newsletter_permission(user, slug: str) -> bool:
    """
    While roles & permissions is off the admin gate (already passed) decides,
    like every other admin screen; while it is on the user's roles must grant
    the slug (ADR 2026-10-29-configurable-access-features).
    """
    if not user or not user.is_authenticated:
        return False
    return allows(user, slug)


def require_newsletter_permission(request, slug: str):
    """Return HttpResponseForbidden when the user lacks the slug; else None."""
    if user_has_newsletter_permission(request.user, slug):
        return None
    return HttpResponseForbidden("Insufficient permissions.")
