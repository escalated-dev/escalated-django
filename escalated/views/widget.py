"""
Public-facing embeddable widget API endpoints.

All endpoints are unauthenticated and intended for use from a JavaScript
widget embedded on a customer's website.  Rate limiting is applied via
Django's cache framework to prevent abuse.
"""

import hmac
import json
import time

from django.core.cache import cache
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.utils.http import parse_etags
from django.views.decorators.http import require_GET, require_POST, require_safe

from escalated import guest_access, guest_throttle, kb_guards
from escalated.conf import get_setting
from escalated.models import Article, Contact, Department, EscalatedSetting, Ticket
from escalated.signals import ticket_created
from escalated.views import guest_verification
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
    """Off until an admin turns it on, as in the other hosts (migration 0031 kept existing installs on)."""
    return EscalatedSetting.get_bool("widget_enabled", default=False)


def chat_enabled():
    """Live chat in the widget: off until an admin turns it on."""
    return EscalatedSetting.get_bool("chat_enabled", default=False)


def _guest_tickets_enabled():
    """Ticket creation from the widget: the shared guest-tickets switch and the widget's own."""
    return EscalatedSetting.guest_tickets_enabled() and EscalatedSetting.get_bool(
        "widget_ticket_creation_enabled", default=True
    )


def _signed_in(request):
    user = getattr(request, "user", None)
    return bool(user is not None and user.is_authenticated)


def _kb_available(request):
    """The knowledge base is on, and public or the visitor is signed in (always a guest cross-origin)."""
    return kb_guards.kb_enabled() and (kb_guards.kb_public() or _signed_in(request))


def _kb_error(request):
    """The answer when the widget may not show articles, else None."""
    if not kb_guards.kb_enabled():
        return JsonResponse(
            {"error": "Knowledge base is disabled", "message": "Knowledge base is disabled"}, status=404
        )
    if not (kb_guards.kb_public() or _signed_in(request)):
        message = "Knowledge base is not public"
        return JsonResponse({"error": message, "message": message}, status=403)
    return None


def _widget_departments():
    """Active departments the widget offers: the admin's ``widget_departments`` list, or all of them."""
    departments = Department.objects.filter(is_active=True)
    raw = EscalatedSetting.get("widget_departments", "") or ""
    ids = [int(part) for part in raw.replace(",", " ").split() if part.isdigit()]
    return departments.filter(pk__in=ids) if ids else departments


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
    color = EscalatedSetting.get("widget_color") or EscalatedSetting.get("widget_accent_color", "#4f46e5")
    kb_enabled = EscalatedSetting.get_bool("widget_kb_search_enabled", default=True) and _kb_available(request)
    tickets_enabled = _guest_tickets_enabled()

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
            "departments": [{"id": d.pk, "name": d.name} for d in _widget_departments()],
            "kb_enabled": kb_enabled,
            "guest_tickets_enabled": tickets_enabled,
            "chat_enabled": chat_enabled(),
            # Ticket create and chat start store the host page's `metadata`.
            "accepts_metadata": True,
            # Ticket creation, chat and status lookup need an emailed code
            # (POST verification); lookup returns expiring grants, never a
            # ticket for a claimed address alone. See docs/guest-access.md.
            "guest_verification_required": True,
            "status_lookup_enabled": True,
        }
    )


@require_GET
def widget_article_search(request):
    """Search published knowledge-base articles."""
    if not _widget_enabled():
        return JsonResponse({"error": "Widget is disabled"}, status=403)

    if _rate_limited(request, scope="widget_search"):
        return _reject()

    kb_error = _kb_error(request)
    if kb_error is not None:
        return kb_error

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

    kb_error = _kb_error(request)
    if kb_error is not None:
        return None, kb_error

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

    if not _guest_tickets_enabled():
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

    errors.update(guest_verification.proof_errors(body))

    if errors:
        if contract:
            return None, contract_validation_error(errors)
        return None, JsonResponse({"errors": errors}, status=400)

    priority = body.get("priority", get_setting("DEFAULT_PRIORITY"))
    metadata = WidgetMetadata.clean(body.get("metadata"), request)

    def create():
        # Dedupe repeat guests by email (Pattern B).
        contact = Contact.find_or_create_by_email(email, name)

        attrs = _apply_guest_policy(
            {
                "guest_name": name,
                "guest_email": email,
                "subject": subject,
                "description": description,
                "priority": priority,
                "channel": "widget",
                "contact": contact,
                "department": department,
                "metadata": metadata,
            }
        )
        ticket = Ticket.objects.create(**attrs)
        guest_access.mark_verified(ticket, email)
        return ticket, guest_access.issue(ticket)

    try:
        ticket, token = guest_access.consume(
            body["verification_id"], body["verification_code"], email, "ticket", create
        )
    except guest_access.InvalidCode as exc:
        if contract:
            return None, contract_validation_error({"verification_code": str(exc)})
        return None, JsonResponse({"errors": {"verification_code": str(exc)}}, status=400)

    # SLA, the created activity, notifications, webhooks and workflows hang off this signal.
    ticket_created.send(sender=Ticket, ticket=ticket, user=None)
    ticket.guest_access_token = token
    return ticket, None


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
                # An expiring grant now (it used to be the permanent token).
                "guest_token": ticket.guest_access_token,
                "expires_at": ticket.guest_access_expires_at.isoformat(),
            },
        }
    )


@require_POST
def widget_tickets(request):
    """Create a ticket from the shared widget: 201 with ``reference`` at the top level."""
    ticket, error = _create_ticket(request, contract=True)
    if error is not None:
        return error

    return guest_verification.private(
        JsonResponse(
            {
                "message": "Ticket created.",
                "reference": ticket.reference,
                # An expiring grant: the bearer for GET widget/tickets/<reference>
                # and the token in the guest ticket page's URL (guest/<token>/).
                "guest_access_token": ticket.guest_access_token,
                "expires_at": ticket.guest_access_expires_at.isoformat(),
            },
            status=201,
        )
    )


def widget_verification(request):
    """POST widget/verification: email a code (purpose ticket, chat or lookup)."""
    return guest_verification.verification(request, surface_enabled=_widget_enabled)


def widget_lookup(request):
    """POST widget/lookup: the caller's tickets by reference and proven email, with fresh grants."""
    return guest_verification.lookup(request, surface_enabled=_widget_enabled)


@require_GET
def widget_ticket_status(request, reference):
    """GET widget/tickets/<reference> with ``Authorization: Bearer <grant>``."""
    if not _widget_enabled():
        return JsonResponse({"error": "Widget is disabled", "message": "Widget is disabled"}, status=403)

    not_found = guest_verification.private(JsonResponse({"message": "Ticket not found."}, status=404))
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        return not_found
    ticket = guest_access.resolve(header[7:].strip())
    if ticket is None or not hmac.compare_digest(str(ticket.reference), str(reference)):
        return not_found

    replies = (
        ticket.replies.filter(is_internal_note=False, is_deleted=False)
        .select_related("author")
        .order_by("-created_at")[:20]
    )
    return guest_verification.private(
        JsonResponse(
            {
                "reference": ticket.reference,
                "subject": ticket.subject,
                "status": ticket.status,
                "status_label": ticket.get_status_display(),
                "created_at": ticket.created_at.isoformat(),
                "department": ticket.department.name if ticket.department_id else None,
                "replies": [
                    {
                        "body": reply.body,
                        "author": _author_name(reply, ticket),
                        "is_agent": reply.author_id is not None,
                        "created_at": reply.created_at.isoformat(),
                    }
                    for reply in replies
                ],
            }
        )
    )


def _author_name(reply, ticket):
    author = reply.author
    if author is None:
        return ticket.guest_name or "You"
    name = getattr(author, "get_full_name", lambda: "")()
    return name or "Support"


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
