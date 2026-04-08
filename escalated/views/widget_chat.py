"""
Public-facing widget chat endpoints for customers.

All endpoints are unauthenticated and intended for use from a JavaScript
widget embedded on a customer's website.
"""

import json
import time

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from escalated.models import ChatSession, EscalatedSetting
from escalated.services.chat_availability_service import ChatAvailabilityService
from escalated.services.chat_routing_service import ChatRoutingService
from escalated.services.chat_session_service import ChatSessionService


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


@require_GET
def chat_availability(request):
    """Check if live chat is currently available."""
    if _rate_limited(request, scope="widget_chat_availability"):
        return _reject()

    service = ChatAvailabilityService()
    available = service.is_available()

    routing_service = ChatRoutingService()
    routing = routing_service.evaluate_routing()

    return JsonResponse(
        {
            "available": available,
            "online_agents": routing["total_online_agents"],
            "offline_behavior": routing["offline_behavior"],
        }
    )


@csrf_exempt
@require_POST
def start_chat(request):
    """Start a new chat session from the widget."""
    if _rate_limited(request, scope="widget_chat_start", limit=5, window=60):
        return _reject()

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = body.get("name", "").strip()
    email = body.get("email", "").strip()

    errors = {}
    if not name:
        errors["name"] = "Name is required"
    if not email:
        errors["email"] = "Email is required"
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    session_service = ChatSessionService()
    ticket, session = session_service.start_chat(
        name=name,
        email=email,
        metadata=body.get("metadata"),
    )

    # Try to auto-assign an agent
    routing_service = ChatRoutingService()
    agent = routing_service.find_available_agent()
    if agent:
        session_service.assign_agent(session, agent)
        session.refresh_from_db()

    availability_service = ChatAvailabilityService()
    queue_position = availability_service.get_queue_position(session)

    return JsonResponse(
        {
            "session_id": session.customer_session_id,
            "ticket_reference": ticket.reference,
            "status": session.status,
            "queue_position": queue_position,
            "agent_name": session.agent.get_full_name() if session.agent else None,
        }
    )


@csrf_exempt
@require_POST
def send_message(request):
    """Send a message from the customer."""
    if _rate_limited(request, scope="widget_chat_message", limit=30, window=60):
        return _reject()

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    session_id = body.get("session_id", "").strip()
    message_body = body.get("body", "").strip()

    if not session_id:
        return JsonResponse({"error": "session_id is required"}, status=400)
    if not message_body:
        return JsonResponse({"error": "Message body is required"}, status=400)

    try:
        session = ChatSession.objects.select_related("ticket").get(customer_session_id=session_id)
    except ChatSession.DoesNotExist:
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


@csrf_exempt
@require_POST
def update_typing(request):
    """Update typing indicator from customer."""
    if _rate_limited(request, scope="widget_chat_typing", limit=60, window=60):
        return _reject()

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    session_id = body.get("session_id", "").strip()
    if not session_id:
        return JsonResponse({"error": "session_id is required"}, status=400)

    try:
        session = ChatSession.objects.get(customer_session_id=session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    service = ChatSessionService()
    service.update_typing(session, is_typing=body.get("is_typing", False), sender_type="customer")

    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def end_chat(request):
    """End a chat from the customer side."""
    if _rate_limited(request, scope="widget_chat_end", limit=10, window=60):
        return _reject()

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    session_id = body.get("session_id", "").strip()
    if not session_id:
        return JsonResponse({"error": "session_id is required"}, status=400)

    try:
        session = ChatSession.objects.select_related("ticket").get(customer_session_id=session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    if session.status not in [ChatSession.Status.ACTIVE, ChatSession.Status.WAITING]:
        return JsonResponse({"error": "Chat session is not active"}, status=400)

    service = ChatSessionService()
    service.end_chat(session, ended_by=None)

    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def rate_chat(request):
    """Rate a completed chat session."""
    if _rate_limited(request, scope="widget_chat_rate", limit=5, window=60):
        return _reject()

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    session_id = body.get("session_id", "").strip()
    rating = body.get("rating")
    comment = body.get("comment", "")

    if not session_id:
        return JsonResponse({"error": "session_id is required"}, status=400)
    if rating is None or not isinstance(rating, int) or rating < 1 or rating > 5:
        return JsonResponse({"error": "rating must be an integer between 1 and 5"}, status=400)

    try:
        session = ChatSession.objects.get(customer_session_id=session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    if session.status != ChatSession.Status.ENDED:
        return JsonResponse({"error": "Can only rate ended chats"}, status=400)

    service = ChatSessionService()
    service.rate_chat(session, rating=rating, comment=comment)

    return JsonResponse({"ok": True})
