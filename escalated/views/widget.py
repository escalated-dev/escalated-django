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
from django.http import Http404, HttpResponse, JsonResponse
from django.utils.http import parse_etags
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_safe

from escalated import guest_throttle
from escalated.conf import get_setting
from escalated.models import Article, Contact, Department, EscalatedSetting, Ticket
from escalated.widget_embed import WidgetMetadata, embed_script

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


def active_department(value):
    """Resolve a widget-supplied ``department_id`` to an active Department.

    Returns ``(department, error)``: ``(None, None)`` when no department was
    chosen, ``(None, message)`` when the id is not an active department.
    """
    if value in (None, ""):
        return None, None
    invalid = (None, "The selected department is invalid.")
    if isinstance(value, bool):
        return invalid
    try:
        department_id = int(value)
    except (TypeError, ValueError):
        return invalid
    department = Department.objects.filter(pk=department_id, is_active=True).first()
    return (department, None) if department else invalid


def contract_validation_error(errors):
    """A validation answer in the shape the shared widget reads: 422 ``{message, errors: {field: [msg]}}``."""
    errors = {field: msg if isinstance(msg, list) else [msg] for field, msg in errors.items()}
    first = next(iter(errors.values()))[0]
    return JsonResponse({"message": first, "errors": errors}, status=422)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@require_GET
def widget_config(request):
    """Return public widget configuration."""
    if not _widget_enabled():
        return JsonResponse({"enabled": False, "error": "Widget is disabled"}, status=403)

    if _rate_limited(request, scope="widget_config"):
        return _reject()

    greeting = EscalatedSetting.get("widget_greeting", "How can we help?")
    color = EscalatedSetting.get("widget_accent_color", "#4f46e5")
    kb_enabled = EscalatedSetting.get_bool("widget_kb_search_enabled", default=True)
    tickets_enabled = EscalatedSetting.get_bool("widget_ticket_creation_enabled", default=True)

    return JsonResponse(
        {
            "widget_enabled": True,
            "widget_title": EscalatedSetting.get("widget_title", "Support"),
            "widget_greeting": greeting,
            "widget_accent_color": color,
            "kb_search_enabled": kb_enabled,
            "ticket_creation_enabled": tickets_enabled,
            # The keys the shared widget (@escalated-dev/escalated) reads.
            "enabled": True,
            "color": color,
            "greeting": greeting,
            "position": EscalatedSetting.get("widget_position", "bottom-right") or "bottom-right",
            "departments": [{"id": d.pk, "name": d.name} for d in Department.objects.filter(is_active=True)],
            "kb_enabled": kb_enabled,
            "guest_tickets_enabled": tickets_enabled,
            # Ticket create and chat start store the host page's `metadata`.
            "accepts_metadata": True,
            # There is no mailbox-verified status lookup, so the widget hides its
            # Status tab: a claimed email address never unlocks a ticket.
            "status_lookup_enabled": False,
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


def _article_payload(request, lookup):
    """Return ``(fields, None)`` for the published article matching ``lookup``, or ``(None, error_response)``."""
    if not _widget_enabled():
        return None, JsonResponse({"error": "Widget is disabled"}, status=403)

    if _rate_limited(request, scope="widget_article"):
        return None, _reject()

    try:
        article = Article.objects.published().select_related("category").get(**lookup)
    except Article.DoesNotExist:
        return None, JsonResponse({"error": "Article not found", "message": "Article not found"}, status=404)

    # Increment view count
    Article.objects.filter(pk=article.pk).update(view_count=article.view_count + 1)

    return {
        "id": article.pk,
        "title": article.title,
        "slug": article.slug,
        "body": article.body,
        "category": article.category.name if article.category else None,
    }, None


@require_GET
def widget_article_detail(request, article_id):
    """Return a single published article by id, wrapped in ``article``."""
    fields, error = _article_payload(request, {"pk": article_id})
    return error or JsonResponse({"article": fields})


@require_GET
def widget_article_by_slug(request, slug):
    """Return a single published article by slug, its fields at the top level (shared widget)."""
    fields, error = _article_payload(request, {"slug": slug})
    return error or JsonResponse(fields)


def _create_ticket(request, contract):
    """Create a guest ticket from a widget request.

    Returns ``(ticket, None)`` or ``(None, error_response)``. ``contract`` selects the
    shared widget's validation shape (422 ``{message, errors: {field: [msg]}}``) over
    the original one (400 ``{errors: {field: msg}}``).
    """
    if not _widget_enabled():
        return None, JsonResponse({"error": "Widget is disabled", "message": "Widget is disabled"}, status=403)

    if not EscalatedSetting.get_bool("widget_ticket_creation_enabled", default=True):
        message = "Ticket creation is disabled"
        return None, JsonResponse({"error": message, "message": message}, status=403)

    retry_after = guest_throttle.check(request, guest_throttle.TICKET)
    if retry_after is not None:
        return None, guest_throttle.too_many_requests(retry_after, json=True)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        body = None
    if not isinstance(body, dict):
        return None, JsonResponse({"error": "Invalid JSON", "message": "Invalid JSON"}, status=400)

    name = str(body.get("name") or "").strip()
    email = str(body.get("email") or "").strip()
    subject = str(body.get("subject") or "").strip()
    description = str(body.get("description") or "").strip()

    errors = {}
    if not name:
        errors["name"] = "Name is required"
    if not email:
        errors["email"] = "Email is required"
    if not subject:
        errors["subject"] = "Subject is required"
    if not description:
        errors["description"] = "Description is required"
    department, department_error = active_department(body.get("department_id"))
    if department_error:
        errors["department_id"] = department_error
    metadata_error = WidgetMetadata.error(body.get("metadata"))
    if metadata_error:
        errors["metadata"] = metadata_error

    if errors:
        if contract:
            return None, contract_validation_error(errors)
        return None, JsonResponse({"errors": errors}, status=400)

    import secrets

    guest_token = secrets.token_hex(32)
    priority = body.get("priority", get_setting("DEFAULT_PRIORITY"))

    # Dedupe repeat guests by email (Pattern B).
    contact = Contact.find_or_create_by_email(email, name)

    attrs = _apply_guest_policy(
        {
            "guest_name": name,
            "guest_email": email,
            "guest_token": guest_token,
            "subject": subject,
            "description": description,
            "priority": priority,
            "channel": "widget",
            "contact": contact,
            "department": department,
            "metadata": WidgetMetadata.clean(body.get("metadata"), request),
        }
    )

    return Ticket.objects.create(**attrs), None


@csrf_exempt
@require_POST
def widget_create_ticket(request):
    """Create a ticket from the widget (guest mode). Original route and answer shape."""
    ticket, error = _create_ticket(request, contract=False)
    if error is not None:
        return error

    return JsonResponse(
        {
            "success": True,
            "ticket": {
                "reference": ticket.reference,
                "guest_token": ticket.guest_token,
            },
        }
    )


@csrf_exempt
@require_POST
def widget_tickets(request):
    """Create a ticket from the shared widget: 201 with ``reference`` at the top level."""
    ticket, error = _create_ticket(request, contract=True)
    if error is not None:
        return error

    return JsonResponse(
        {
            "message": "Ticket created.",
            "reference": ticket.reference,
            # Opens the guest ticket page (guest/<token>/), as the original route's guest_token does.
            "guest_access_token": ticket.guest_token,
        },
        status=201,
    )


@require_safe
def widget_embed_script(request):
    """Serve the standalone widget bundle so any site can load it with a <script> tag."""
    script = embed_script()
    if script is None:
        raise Http404("Widget bundle not found")

    content, etag = script
    headers = {
        "Cache-Control": "public, max-age=3600",
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
        "Cross-Origin-Resource-Policy": "cross-origin",
        "Access-Control-Allow-Origin": "*",
    }
    if_none_match = parse_etags(request.META.get("HTTP_IF_NONE_MATCH", ""))
    if etag in if_none_match or "*" in if_none_match:
        response = HttpResponse(status=304, headers=headers)
        del response["Content-Type"]
        return response

    return HttpResponse(content, content_type="application/javascript; charset=utf-8", headers=headers)


def _apply_guest_policy(attrs):
    """Layer the admin-configured guest policy onto a ticket-create attrs dict.

    Persisted by the admin settings page under three EscalatedSetting keys
    (guest_policy_mode / guest_policy_user_id / guest_policy_signup_url_template).
    Modes:

      * ``unassigned`` (default): ``requester_*`` left null, ``guest_*`` preserved.
      * ``guest_user``: route to the configured host-app user via the generic
        (ContentType, object_id) FK. Still records ``guest_name`` / ``guest_email``
        so agents see who submitted. Falls through to ``unassigned`` behavior if
        ``guest_policy_user_id`` is zero or missing.
      * ``prompt_signup``: same ticket-create path as ``unassigned`` today;
        signup-invite emission is a listener-level follow-up.

    Returns the modified attrs dict.
    """
    from django.contrib.auth import get_user_model
    from django.contrib.contenttypes.models import ContentType

    mode = EscalatedSetting.get("guest_policy_mode", "unassigned") or "unassigned"

    if mode == "guest_user":
        raw_id = EscalatedSetting.get("guest_policy_user_id", "") or ""
        try:
            user_id = int(raw_id)
        except (TypeError, ValueError):
            user_id = 0
        if user_id > 0:
            user_model = get_user_model()
            attrs["requester_content_type"] = ContentType.objects.get_for_model(user_model)
            attrs["requester_object_id"] = user_id
            return attrs

    # unassigned + prompt_signup + misconfigured guest_user all land here.
    attrs["requester_content_type"] = None
    attrs["requester_object_id"] = None
    return attrs
