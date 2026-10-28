"""
Public-facing widget chat endpoints for customers.

All endpoints are unauthenticated and intended for use from a JavaScript
widget embedded on a customer's website.

The shared widget (``@escalated-dev/escalated``) addresses a chat by the
unguessable token ``POST chat/start`` returns as ``id``:
``chat/<token>/messages`` (GET + POST), ``/typing``, ``/end`` and ``/rate``.
The original routes, which take ``session_id`` in the body, keep working.
"""

import json
import time
from datetime import timedelta
from functools import wraps

from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from escalated import chat_tokens, guest_access
from escalated.models import ChatSession, EscalatedSetting
from escalated.services.chat_availability_service import ChatAvailabilityService
from escalated.services.chat_routing_service import ChatRoutingService
from escalated.services.chat_session_service import ChatSessionService
from escalated.views import guest_verification
from escalated.views.widget import _widget_enabled, active_department, chat_enabled, contract_validation_error
from escalated.widget_embed import WidgetMetadata

# An agent counts as typing for this long after their last keystroke signal.
AGENT_TYPING_WINDOW = timedelta(seconds=5)


def _rate_limited(request, scope="widget_chat", limit=None, window=60):
    if limit is None:
        limit = EscalatedSetting.get_int("widget_chat_rate_limit", default=30)

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


def _chat_off_reason():
    """Why the widget's live chat is unavailable, or None when it is on."""
    if not _widget_enabled():
        return "Widget is disabled."
    if not chat_enabled():
        return "Chat is disabled."
    return None


def chat_gated(view):
    """403 unless both the widget and live chat are switched on."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        reason = _chat_off_reason()
        if reason is not None:
            return JsonResponse({"error": reason, "message": reason}, status=403)
        return view(request, *args, **kwargs)

    return wrapped


@require_GET
def chat_availability(request):
    """Check if live chat is currently available."""
    reason = _chat_off_reason()
    if reason is not None:
        return JsonResponse({"available": False, "reason": reason})

    if _rate_limited(request, scope="widget_chat_availability"):
        return _reject()

    # An unknown or inactive department falls back to "any agent".
    department, _ = active_department(request.GET.get("department_id"))
    service = ChatAvailabilityService()
    available = service.is_available(department)

    routing_service = ChatRoutingService()
    routing = routing_service.evaluate_routing()

    return JsonResponse(
        {
            "available": available,
            "online_agents": routing["total_online_agents"],
            "offline_behavior": routing["offline_behavior"],
        }
    )


def _agent_name(user):
    return (user.get_full_name() or user.get_username()) if user else None


def _serialize_messages(session):
    """The chat's public messages, oldest first, in the shape the shared widget renders."""
    replies = (
        session.ticket.replies.filter(is_internal_note=False, is_deleted=False)
        .select_related("author")
        .order_by("-created_at", "-pk")[:100]
    )
    return [
        {
            "id": reply.pk,
            "body": reply.body,
            "is_agent": reply.author_id is not None,
            "author": {"name": _agent_name(reply.author) if reply.author_id else session.ticket.guest_name},
            "created_at": reply.created_at.isoformat(),
        }
        for reply in reversed(list(replies))
    ]


def _start(request, contract):
    """Start a chat from a widget request. Returns ``(ticket, session, None)`` or ``(None, None, error)``."""
    if _rate_limited(request, scope="widget_chat_start", limit=5, window=60):
        return None, None, _reject()

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        body = None
    if not isinstance(body, dict):
        return None, None, JsonResponse({"error": "Invalid JSON", "message": "Invalid JSON"}, status=400)

    name = str(body.get("name") or "").strip()
    email = str(body.get("email") or "").strip()
    subject = str(body.get("subject") or "").strip()[:255]
    message = str(body.get("message") or "").strip()

    errors = {}
    if not name:
        errors["name"] = "Name is required"
    if not email:
        errors["email"] = "Email is required"
    department, department_error = active_department(body.get("department_id"))
    if department_error:
        errors["department_id"] = department_error
    metadata_error = WidgetMetadata.error(body.get("metadata"))
    if metadata_error:
        errors["metadata"] = metadata_error
    # A chat needs an emailed code (purpose "chat"), like a widget ticket.
    errors.update(guest_verification.proof_errors(body))
    if errors:
        if contract:
            return None, None, contract_validation_error(errors)
        return None, None, JsonResponse({"errors": errors}, status=400)

    session_service = ChatSessionService()
    metadata = WidgetMetadata.clean(body.get("metadata"), request)
    try:
        ticket, session = guest_access.consume(
            body["verification_id"],
            body["verification_code"],
            email,
            "chat",
            lambda: session_service.start_chat(
                name=name,
                email=email,
                department=department,
                subject=subject or None,
                metadata=metadata,
            ),
        )
    except guest_access.InvalidCode as exc:
        if contract:
            return None, None, contract_validation_error({"verification_code": str(exc)})
        return None, None, JsonResponse({"errors": {"verification_code": str(exc)}}, status=400)
    if message:
        session_service.send_message(session, body=message, sender=None, sender_type="customer")

    # Try to auto-assign an agent
    routing_service = ChatRoutingService()
    agent = routing_service.find_available_agent(department=department, ticket=ticket)
    if agent:
        session_service.assign_agent(session, agent)
        session.refresh_from_db()

    return ticket, session, None


def _start_payload(ticket, session):
    return {
        "session_id": session.visitor_token,
        "expires_at": session.customer_token_expires_at.isoformat(),
        "ticket_reference": ticket.reference,
        "status": session.status,
        "queue_position": ChatAvailabilityService().get_queue_position(session),
        "agent_name": _agent_name(session.agent) if session.agent else None,
    }


@chat_gated
@require_POST
def start_chat(request):
    """Start a new chat session from the widget. Original route and answer shape."""
    ticket, session, error = _start(request, contract=False)
    if error is not None:
        return error
    return JsonResponse(_start_payload(ticket, session))


@chat_gated
@require_POST
def chat_start(request):
    """Start a chat for the shared widget: 201 with the session token as ``id``."""
    ticket, session, error = _start(request, contract=True)
    if error is not None:
        return error
    return JsonResponse(
        {
            "id": session.visitor_token,
            **_start_payload(ticket, session),
            "messages": _serialize_messages(session),
            "agent": {"name": _agent_name(session.agent)} if session.agent else None,
        },
        status=201,
    )


# ---------------------------------------------------------------------------
# Token-addressed chat routes (shared widget): chat/<token>/...
# ---------------------------------------------------------------------------


def _session_for(token):
    """The chat session the guest's unexpired token unlocks, or ``None`` (answered with 404)."""
    return chat_tokens.find_session(token, ChatSession.objects.select_related("ticket", "agent"))


def _not_found():
    return JsonResponse({"error": "Chat session not found", "message": "Chat session not found"}, status=404)


def _ended():
    return JsonResponse({"error": "Chat has ended", "message": "Chat has ended."}, status=422)


def _is_open(session):
    return session.status in [ChatSession.Status.ACTIVE, ChatSession.Status.WAITING]


def _json_body(request):
    """The request's JSON object body; an empty body is ``{}``, anything else unparseable is ``None``."""
    if not request.body:
        return {}
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return None
    return body if isinstance(body, dict) else None


@chat_gated
def chat_messages(request, token):
    """GET the chat's messages and state, or POST ``{body}`` as the guest."""
    if request.method == "GET":
        return _list_messages(request, token)
    if request.method == "POST":
        return _post_message(request, token)
    return JsonResponse({"error": "Method not allowed"}, status=405, headers={"Allow": "GET, POST"})


def _list_messages(request, token):
    if _rate_limited(request, scope="widget_chat_poll", limit=120, window=60):
        return _reject()

    session = _session_for(token)
    if session is None:
        return _not_found()

    agent_typing = (
        session.agent is not None
        and session.agent_typing_at is not None
        and session.agent_typing_at > timezone.now() - AGENT_TYPING_WINDOW
    )
    return JsonResponse(
        {
            "messages": _serialize_messages(session),
            "agent": {"name": _agent_name(session.agent)} if session.agent else None,
            # The widget renders this as text: "<name> is typing...".
            "typing": _agent_name(session.agent) if agent_typing else None,
            "ended": not _is_open(session),
        }
    )


def _post_message(request, token):
    if _rate_limited(request, scope="widget_chat_message", limit=30, window=60):
        return _reject()

    session = _session_for(token)
    if session is None:
        return _not_found()
    if not _is_open(session):
        return _ended()

    body = _json_body(request)
    if body is None:
        return JsonResponse({"error": "Invalid JSON", "message": "Invalid JSON"}, status=400)
    message_body = str(body.get("body") or "").strip()
    if not message_body:
        return contract_validation_error({"body": "Message body is required"})
    if len(message_body) > 5000:
        return contract_validation_error({"body": "Message body may not be longer than 5000 characters"})

    reply = ChatSessionService().send_message(session, body=message_body, sender=None, sender_type="customer")
    return JsonResponse({"message": "Message sent.", "id": reply.pk})


@chat_gated
@require_POST
def chat_typing(request, token):
    """Mark the guest as typing."""
    if _rate_limited(request, scope="widget_chat_typing", limit=60, window=60):
        return _reject()

    session = _session_for(token)
    if session is None:
        return _not_found()
    if not _is_open(session):
        return _ended()

    ChatSessionService().update_typing(session, is_typing=True, sender_type="customer")
    return JsonResponse({"ok": True})


@chat_gated
@require_POST
def chat_end(request, token):
    """End the chat from the guest's side."""
    if _rate_limited(request, scope="widget_chat_end", limit=10, window=60):
        return _reject()

    session = _session_for(token)
    if session is None:
        return _not_found()
    if not _is_open(session):
        return JsonResponse({"error": "Chat has already ended", "message": "Chat has already ended."}, status=422)

    ChatSessionService().end_chat(session, ended_by=None)
    return JsonResponse({"ok": True, "message": "Chat ended."})


@chat_gated
@require_POST
def chat_rate(request, token):
    """Rate an ended chat: ``{rating: 1-5, comment?}``."""
    if _rate_limited(request, scope="widget_chat_rate", limit=5, window=60):
        return _reject()

    session = _session_for(token)
    if session is None:
        return _not_found()
    if session.status != ChatSession.Status.ENDED:
        message = "Chat must be ended before rating."
        return JsonResponse({"error": message, "message": message}, status=422)

    body = _json_body(request)
    if body is None:
        return JsonResponse({"error": "Invalid JSON", "message": "Invalid JSON"}, status=400)
    rating = body.get("rating")
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
        return contract_validation_error({"rating": "Rating must be an integer between 1 and 5"})
    comment = body.get("comment") or ""
    if not isinstance(comment, str) or len(comment) > 1000:
        return contract_validation_error({"comment": "Comment must be text of at most 1000 characters"})

    ChatSessionService().rate_chat(session, rating=rating, comment=comment)
    return JsonResponse({"ok": True, "message": "Rating submitted."})


@chat_gated
@require_POST
def send_message(request):
    """Send a message from the customer."""
    if _rate_limited(request, scope="widget_chat_message", limit=30, window=60):
        return _reject()

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    session_id = str(body.get("session_id") or "").strip()
    message_body = str(body.get("body") or "").strip()

    if not session_id:
        return JsonResponse({"error": "session_id is required"}, status=400)
    if not message_body:
        return JsonResponse({"error": "Message body is required"}, status=400)

    session = _session_for(session_id)
    if session is None:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    if session.status not in [ChatSession.Status.ACTIVE, ChatSession.Status.WAITING]:
        return JsonResponse({"error": "Chat session is not active"}, status=400)

    service = ChatSessionService()
    reply = service.send_message(session, body=message_body, sender=None, sender_type="customer")

    return JsonResponse(
        {
            "message": {
                "id": reply.pk,
                "body": reply.body,
                "sender_type": "customer",
                "created_at": reply.created_at.isoformat(),
            }
        }
    )


@chat_gated
@require_POST
def update_typing(request):
    """Update typing indicator from customer."""
    if _rate_limited(request, scope="widget_chat_typing", limit=60, window=60):
        return _reject()

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    session_id = str(body.get("session_id") or "").strip()
    if not session_id:
        return JsonResponse({"error": "session_id is required"}, status=400)

    session = _session_for(session_id)
    if session is None:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    service = ChatSessionService()
    service.update_typing(session, is_typing=body.get("is_typing", False), sender_type="customer")

    return JsonResponse({"ok": True})


@chat_gated
@require_POST
def end_chat(request):
    """End a chat from the customer side."""
    if _rate_limited(request, scope="widget_chat_end", limit=10, window=60):
        return _reject()

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    session_id = str(body.get("session_id") or "").strip()
    if not session_id:
        return JsonResponse({"error": "session_id is required"}, status=400)

    session = _session_for(session_id)
    if session is None:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    if session.status not in [ChatSession.Status.ACTIVE, ChatSession.Status.WAITING]:
        return JsonResponse({"error": "Chat session is not active"}, status=400)

    service = ChatSessionService()
    service.end_chat(session, ended_by=None)

    return JsonResponse({"ok": True})


@chat_gated
@require_POST
def rate_chat(request):
    """Rate a completed chat session."""
    if _rate_limited(request, scope="widget_chat_rate", limit=5, window=60):
        return _reject()

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    session_id = str(body.get("session_id") or "").strip()
    rating = body.get("rating")
    comment = body.get("comment", "")

    if not session_id:
        return JsonResponse({"error": "session_id is required"}, status=400)
    if rating is None or not isinstance(rating, int) or rating < 1 or rating > 5:
        return JsonResponse({"error": "rating must be an integer between 1 and 5"}, status=400)

    session = _session_for(session_id)
    if session is None:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    if session.status != ChatSession.Status.ENDED:
        return JsonResponse({"error": "Can only rate ended chats"}, status=400)

    service = ChatSessionService()
    service.rate_chat(session, rating=rating, comment=comment)

    return JsonResponse({"ok": True})
