"""
Agent-facing chat views for managing live chat sessions.
"""

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from escalated.models import AgentProfile, ChatSession
from escalated.permissions import is_admin, is_agent
from escalated.services.chat_session_service import ChatSessionService

User = get_user_model()


def _require_agent(request):
    """Return an error response if user is not an agent, else None."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    if not is_agent(request.user) and not is_admin(request.user):
        return JsonResponse({"error": "Agent access required"}, status=403)
    return None


def _serialize_session(session):
    """Serialize a ChatSession to a dict."""
    return {
        "id": session.pk,
        "ticket_id": session.ticket_id,
        "ticket_reference": session.ticket.reference,
        "customer_session_id": session.customer_session_id,
        "customer_name": session.ticket.guest_name or session.ticket.requester_name,
        "agent_id": session.agent_id,
        "agent_name": session.agent.get_full_name() if session.agent else None,
        "status": session.status,
        "rating": session.rating,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
    }


@login_required
@require_GET
def active_chats(request):
    """List active chats for the current agent."""
    error = _require_agent(request)
    if error:
        return error

    sessions = ChatSession.objects.filter(
        agent=request.user,
        status=ChatSession.Status.ACTIVE,
    ).select_related("ticket", "agent")

    return JsonResponse({"chats": [_serialize_session(s) for s in sessions]})


@login_required
@require_GET
def chat_queue(request):
    """List waiting chats in the queue."""
    error = _require_agent(request)
    if error:
        return error

    sessions = ChatSession.objects.filter(
        status=ChatSession.Status.WAITING,
    ).select_related("ticket", "agent")

    return JsonResponse({"queue": [_serialize_session(s) for s in sessions]})


@login_required
@require_POST
def accept_chat(request, session_id):
    """Accept a waiting chat from the queue."""
    error = _require_agent(request)
    if error:
        return error

    try:
        session = ChatSession.objects.select_related("ticket").get(pk=session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    if session.status != ChatSession.Status.WAITING:
        return JsonResponse({"error": "Chat is not in waiting state"}, status=400)

    service = ChatSessionService()
    session = service.assign_agent(session, request.user)

    return JsonResponse({"chat": _serialize_session(session)})


@login_required
@require_POST
def end_chat(request, session_id):
    """End an active chat session."""
    error = _require_agent(request)
    if error:
        return error

    try:
        session = ChatSession.objects.select_related("ticket").get(pk=session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    if session.status != ChatSession.Status.ACTIVE:
        return JsonResponse({"error": "Chat is not active"}, status=400)

    service = ChatSessionService()
    session = service.end_chat(session, ended_by=request.user)

    return JsonResponse({"chat": _serialize_session(session)})


@login_required
@require_POST
def transfer_chat(request, session_id):
    """Transfer a chat to another agent."""
    error = _require_agent(request)
    if error:
        return error

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    agent_id = body.get("agent_id")
    if not agent_id:
        return JsonResponse({"error": "agent_id is required"}, status=400)

    try:
        session = ChatSession.objects.select_related("ticket").get(pk=session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    if session.status != ChatSession.Status.ACTIVE:
        return JsonResponse({"error": "Chat is not active"}, status=400)

    try:
        to_agent = User.objects.get(pk=agent_id)
    except User.DoesNotExist:
        return JsonResponse({"error": "Target agent not found"}, status=404)

    service = ChatSessionService()
    session = service.transfer_chat(session, from_agent=request.user, to_agent=to_agent)

    return JsonResponse({"chat": _serialize_session(session)})


@login_required
@require_POST
def update_status(request):
    """Update the agent's chat status (online/away/offline)."""
    error = _require_agent(request)
    if error:
        return error

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    status = body.get("status")
    if status not in [c[0] for c in AgentProfile.ChatStatus.choices]:
        return JsonResponse({"error": "Invalid status"}, status=400)

    profile, _ = AgentProfile.objects.get_or_create(user=request.user)
    profile.chat_status = status
    profile.save(update_fields=["chat_status", "updated_at"])

    return JsonResponse({"status": profile.chat_status})


@login_required
@require_POST
def send_message(request, session_id):
    """Send a message in a chat session (agent side)."""
    error = _require_agent(request)
    if error:
        return error

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    message_body = body.get("body", "").strip()
    if not message_body:
        return JsonResponse({"error": "Message body is required"}, status=400)

    try:
        session = ChatSession.objects.select_related("ticket").get(pk=session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    if session.status != ChatSession.Status.ACTIVE:
        return JsonResponse({"error": "Chat is not active"}, status=400)

    service = ChatSessionService()
    reply = service.send_message(session, body=message_body, sender=request.user, sender_type="agent")

    return JsonResponse(
        {
            "message": {
                "id": reply.pk,
                "body": reply.body,
                "sender_type": "agent",
                "created_at": reply.created_at.isoformat(),
            }
        }
    )


@login_required
@require_POST
def update_typing(request, session_id):
    """Update typing indicator for agent."""
    error = _require_agent(request)
    if error:
        return error

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    try:
        session = ChatSession.objects.get(pk=session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    service = ChatSessionService()
    service.update_typing(session, is_typing=body.get("is_typing", False), sender_type="agent")

    return JsonResponse({"ok": True})
