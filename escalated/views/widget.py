"""
Public-facing embeddable widget API endpoints.

All endpoints are unauthenticated and intended for use from a JavaScript
widget embedded on a customer's website.  Rate limiting is applied via
Django's cache framework to prevent abuse.
"""

import json
import time

from django.core.cache import cache
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from escalated.conf import get_setting
from escalated.models import Article, EscalatedSetting, Ticket

# ---------------------------------------------------------------------------
# Rate limiting helper
# ---------------------------------------------------------------------------


def _rate_limited(request, scope="widget", limit=None, window=60):
    """
    Simple per-IP rate limiter backed by the Django cache.

    Returns ``True`` when the request should be rejected.
    """
    if limit is None:
        limit = EscalatedSetting.get_int("widget_rate_limit", default=30)

    ip = request.META.get("REMOTE_ADDR", "unknown")
    key = f"escalated.ratelimit.{scope}.{ip}"
    data = cache.get(key)

    now = time.time()
    if data is None:
        cache.set(key, {"count": 1, "start": now}, window)
        return False

    if now - data["start"] > window:
        cache.set(key, {"count": 1, "start": now}, window)
        return False

    data["count"] += 1
    cache.set(key, data, window)
    return data["count"] > limit


def _reject():
    return JsonResponse({"error": "Rate limit exceeded"}, status=429)


def _widget_enabled():
    return EscalatedSetting.get_bool("widget_enabled", default=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@require_GET
def widget_config(request):
    """Return public widget configuration."""
    if not _widget_enabled():
        return JsonResponse({"error": "Widget is disabled"}, status=403)

    if _rate_limited(request, scope="widget_config"):
        return _reject()

    return JsonResponse(
        {
            "widget_enabled": True,
            "widget_title": EscalatedSetting.get("widget_title", "Support"),
            "widget_greeting": EscalatedSetting.get("widget_greeting", "How can we help?"),
            "widget_accent_color": EscalatedSetting.get("widget_accent_color", "#4f46e5"),
            "kb_search_enabled": EscalatedSetting.get_bool("widget_kb_search_enabled", default=True),
            "ticket_creation_enabled": EscalatedSetting.get_bool("widget_ticket_creation_enabled", default=True),
        }
    )


@require_GET
def widget_article_search(request):
    """Search published knowledge-base articles."""
    if not _widget_enabled():
        return JsonResponse({"error": "Widget is disabled"}, status=403)

    if _rate_limited(request, scope="widget_search"):
        return _reject()

    q = request.GET.get("q", "").strip()
    if not q or len(q) < 2:
        return JsonResponse({"articles": []})

    articles = (
        Article.objects.published().filter(Q(title__icontains=q) | Q(body__icontains=q)).order_by("-view_count")[:10]
    )

    return JsonResponse(
        {
            "articles": [
                {
                    "id": a.pk,
                    "title": a.title,
                    "slug": a.slug,
                    "excerpt": (a.body[:200] + "...") if len(a.body) > 200 else a.body,
                }
                for a in articles
            ]
        }
    )


@require_GET
def widget_article_detail(request, article_id):
    """Return a single published article."""
    if not _widget_enabled():
        return JsonResponse({"error": "Widget is disabled"}, status=403)

    if _rate_limited(request, scope="widget_article"):
        return _reject()

    try:
        article = Article.objects.published().get(pk=article_id)
    except Article.DoesNotExist:
        return JsonResponse({"error": "Article not found"}, status=404)

    # Increment view count
    Article.objects.filter(pk=article_id).update(view_count=article.view_count + 1)

    return JsonResponse(
        {
            "article": {
                "id": article.pk,
                "title": article.title,
                "slug": article.slug,
                "body": article.body,
                "category": article.category.name if article.category else None,
            }
        }
    )


@csrf_exempt
@require_POST
def widget_create_ticket(request):
    """Create a ticket from the widget (guest mode)."""
    if not _widget_enabled():
        return JsonResponse({"error": "Widget is disabled"}, status=403)

    if not EscalatedSetting.get_bool("widget_ticket_creation_enabled", default=True):
        return JsonResponse({"error": "Ticket creation is disabled"}, status=403)

    if _rate_limited(request, scope="widget_create", limit=10, window=60):
        return _reject()

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = body.get("name", "").strip()
    email = body.get("email", "").strip()
    subject = body.get("subject", "").strip()
    description = body.get("description", "").strip()

    errors = {}
    if not name:
        errors["name"] = "Name is required"
    if not email:
        errors["email"] = "Email is required"
    if not subject:
        errors["subject"] = "Subject is required"
    if not description:
        errors["description"] = "Description is required"

    if errors:
        return JsonResponse({"errors": errors}, status=400)

    import secrets

    guest_token = secrets.token_hex(32)
    priority = body.get("priority", get_setting("DEFAULT_PRIORITY"))

    ticket = Ticket.objects.create(
        requester_content_type=None,
        requester_object_id=None,
        guest_name=name,
        guest_email=email,
        guest_token=guest_token,
        subject=subject,
        description=description,
        priority=priority,
        channel="widget",
    )

    return JsonResponse(
        {
            "success": True,
            "ticket": {
                "reference": ticket.reference,
                "guest_token": guest_token,
            },
        }
    )


@require_GET
def widget_lookup_ticket(request):
    """Look up a guest ticket by reference and email."""
    if not _widget_enabled():
        return JsonResponse({"error": "Widget is disabled"}, status=403)

    if _rate_limited(request, scope="widget_lookup", limit=10, window=60):
        return _reject()

    reference = request.GET.get("reference", "").strip()
    email = request.GET.get("email", "").strip()

    if not reference or not email:
        return JsonResponse({"error": "reference and email are required"}, status=400)

    try:
        ticket = Ticket.objects.get(reference=reference, guest_email=email)
    except Ticket.DoesNotExist:
        return JsonResponse({"error": "Ticket not found"}, status=404)

    return JsonResponse(
        {
            "ticket": {
                "reference": ticket.reference,
                "subject": ticket.subject,
                "status": ticket.status,
                "guest_token": ticket.guest_token,
                "created_at": ticket.created_at.isoformat(),
            }
        }
    )
