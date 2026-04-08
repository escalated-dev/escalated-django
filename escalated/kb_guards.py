"""
Knowledge base toggle guards.

Provides settings and a decorator to conditionally enable/disable KB views
based on EscalatedSetting values.
"""

from functools import wraps

from django.http import HttpResponseNotFound
from django.utils.translation import gettext as _

from escalated.models import EscalatedSetting


def kb_enabled():
    """Check if the knowledge base is enabled."""
    return EscalatedSetting.get_bool("knowledge_base_enabled", default=True)


def kb_public():
    """Check if the knowledge base is publicly accessible (no login required)."""
    return EscalatedSetting.get_bool("knowledge_base_public", default=False)


def kb_feedback_enabled():
    """Check if the helpful/not-helpful feedback is enabled on articles."""
    return EscalatedSetting.get_bool("knowledge_base_feedback_enabled", default=True)


def require_kb_enabled(view_func):
    """Decorator that returns 404 if the knowledge base is disabled."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not kb_enabled():
            return HttpResponseNotFound(_("Knowledge base is not available."))
        return view_func(request, *args, **kwargs)

    return _wrapped
