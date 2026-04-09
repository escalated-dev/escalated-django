import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from escalated.permissions import is_agent
from escalated.services.mention_service import MentionService


@login_required
def mention_list(request):
    """List unread mentions for current user."""
    if not is_agent(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    svc = MentionService()
    mentions = svc.unread_mentions(request.user.pk)
    return JsonResponse(
        [
            {
                "id": m.id,
                "reply_id": m.reply_id,
                "ticket_id": m.reply.ticket_id,
                "ticket_reference": m.reply.ticket.reference,
                "ticket_subject": m.reply.ticket.subject,
                "created_at": m.created_at.isoformat(),
                "read_at": m.read_at.isoformat() if m.read_at else None,
            }
            for m in mentions
        ],
        safe=False,
    )


@login_required
@require_POST
def mention_mark_read(request):
    """Mark mentions as read."""
    if not is_agent(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    data = json.loads(request.body)
    mention_ids = data.get("mention_ids", [])
    svc = MentionService()
    svc.mark_as_read(mention_ids, request.user.pk)
    return JsonResponse({"marked_read": len(mention_ids)})


@login_required
def search_agents(request):
    """Search agents for @mention autocomplete."""
    if not is_agent(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    query = request.GET.get("q", "")
    limit = int(request.GET.get("limit", 10))
    svc = MentionService()
    results = svc.search_agents(query, limit=limit)
    return JsonResponse(results, safe=False)
