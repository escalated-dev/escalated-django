"""
REST API views for Escalated.

All views return JSON responses and require Bearer token authentication
(handled by AuthenticateApiToken middleware). Response format matches
the Laravel implementation for cross-framework compatibility.
"""

import json

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from escalated.api_serializers import (
    ApiAgentSerializer,
    ApiCannedResponseSerializer,
    ApiDepartmentSerializer,
    ApiMacroSerializer,
    ApiReplySerializer,
    ApiTagSerializer,
    ApiTicketCollectionSerializer,
    ApiTicketDetailSerializer,
)
from escalated.models import (
    CannedResponse,
    Department,
    Macro,
    Tag,
    Ticket,
)
from escalated.permissions import is_agent, is_admin
from escalated.services.ticket_service import TicketService

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_ability(request, ability):
    """
    Check that the request's API token has the given ability.
    Returns a 403 JsonResponse on failure, or None on success.
    """
    api_token = getattr(request, "api_token", None)
    if api_token and not api_token.has_ability(ability):
        return JsonResponse({"message": "Insufficient permissions."}, status=403)
    return None


def _json_body(request):
    """Parse JSON request body, returning an empty dict on failure."""
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}


def _resolve_ticket(reference):
    """
    Resolve a ticket by reference string or numeric ID.
    Returns (ticket, None) on success, or (None, JsonResponse) on failure.
    """
    try:
        ticket = Ticket.objects.select_related(
            "assigned_to", "department", "sla_policy"
        ).prefetch_related(
            "tags",
            "replies__author",
            "replies__attachments",
            "activities",
        ).get(reference=reference)
        return ticket, None
    except Ticket.DoesNotExist:
        pass

    # Fall back to lookup by numeric ID
    try:
        ticket_id = int(reference)
        ticket = Ticket.objects.select_related(
            "assigned_to", "department", "sla_policy"
        ).prefetch_related(
            "tags",
            "replies__author",
            "replies__attachments",
            "activities",
        ).get(pk=ticket_id)
        return ticket, None
    except (ValueError, Ticket.DoesNotExist):
        return None, JsonResponse({"message": "Ticket not found."}, status=404)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
def auth_validate(request):
    """
    POST /auth/validate

    Validate the current API token and return user info + abilities.
    """
    user = request.user
    api_token = getattr(request, "api_token", None)

    return JsonResponse({
        "user": {
            "id": user.pk,
            "name": getattr(user, "get_full_name", lambda: str(user))(),
            "email": getattr(user, "email", ""),
        },
        "abilities": api_token.abilities if api_token else [],
        "is_agent": is_agent(user),
        "is_admin": is_admin(user),
        "token_name": api_token.name if api_token else None,
        "expires_at": (
            api_token.expires_at.isoformat() if api_token and api_token.expires_at else None
        ),
    })


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@require_GET
def dashboard(request):
    """
    GET /dashboard

    Return agent dashboard statistics.
    """
    user_id = request.user.pk
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timezone.timedelta(days=today_start.weekday())

    stats = {
        "open": Ticket.objects.open().count(),
        "my_assigned": Ticket.objects.assigned_to(user_id).open().count(),
        "unassigned": Ticket.objects.unassigned().open().count(),
        "sla_breached": Ticket.objects.open().breached_sla().count(),
        "resolved_today": Ticket.objects.filter(
            resolved_at__gte=today_start
        ).count(),
    }

    recent_tickets = (
        Ticket.objects.select_related("assigned_to", "department")
        .order_by("-created_at")[:10]
    )

    recent_tickets_data = [
        {
            "id": t.pk,
            "reference": t.reference,
            "subject": t.subject,
            "status": t.status,
            "priority": t.priority,
            "requester_name": t.requester_name,
            "assignee_name": (
                getattr(t.assigned_to, "get_full_name", lambda: str(t.assigned_to))()
                if t.assigned_to
                else None
            ),
            "created_at": t.created_at.isoformat(),
        }
        for t in recent_tickets
    ]

    # Needs attention: SLA breaching tickets
    sla_breaching = Ticket.objects.open().breached_sla().select_related(
        "assigned_to"
    )[:5]
    sla_breaching_data = [
        {
            "reference": t.reference,
            "subject": t.subject,
            "priority": t.priority,
            "requester_name": t.requester_name,
        }
        for t in sla_breaching
    ]

    # Unassigned urgent tickets
    unassigned_urgent = (
        Ticket.objects.unassigned()
        .open()
        .filter(priority__in=["urgent", "critical"])[:5]
    )
    unassigned_urgent_data = [
        {
            "reference": t.reference,
            "subject": t.subject,
            "priority": t.priority,
            "requester_name": t.requester_name,
        }
        for t in unassigned_urgent
    ]

    # My performance
    my_resolved_this_week = Ticket.objects.assigned_to(user_id).filter(
        resolved_at__gte=week_start
    ).count()

    return JsonResponse({
        "stats": stats,
        "recent_tickets": recent_tickets_data,
        "needs_attention": {
            "sla_breaching": sla_breaching_data,
            "unassigned_urgent": unassigned_urgent_data,
        },
        "my_performance": {
            "resolved_this_week": my_resolved_this_week,
        },
    })


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


@require_GET
def ticket_list(request):
    """
    GET /tickets

    List tickets with filtering, sorting, and pagination.
    Query params: status, priority, department_id, assigned_to, unassigned,
                  search, sla_breached, following, sort_by, sort_dir, per_page, page
    """
    tickets = Ticket.objects.select_related(
        "assigned_to", "department"
    ).prefetch_related("tags")

    # Filters
    status = request.GET.get("status")
    if status:
        tickets = tickets.filter(status=status)

    priority = request.GET.get("priority")
    if priority:
        tickets = tickets.filter(priority=priority)

    department_id = request.GET.get("department_id")
    if department_id:
        tickets = tickets.filter(department_id=department_id)

    assigned_to = request.GET.get("assigned_to")
    if assigned_to:
        tickets = tickets.filter(assigned_to_id=assigned_to)

    unassigned = request.GET.get("unassigned")
    if unassigned and unassigned.lower() in ("1", "true", "yes"):
        tickets = tickets.filter(assigned_to__isnull=True)

    search = request.GET.get("search")
    if search:
        tickets = tickets.search(search)

    sla_breached = request.GET.get("sla_breached")
    if sla_breached and sla_breached.lower() in ("1", "true", "yes"):
        tickets = tickets.breached_sla()

    following = request.GET.get("following")
    if following and following.lower() in ("1", "true", "yes"):
        tickets = tickets.followed_by(request.user.pk)

    # Sorting
    sort_by = request.GET.get("sort_by", "created_at")
    sort_dir = request.GET.get("sort_dir", "desc")
    allowed_sort_fields = [
        "created_at", "updated_at", "priority", "status", "subject",
    ]
    if sort_by in allowed_sort_fields:
        order = f"-{sort_by}" if sort_dir == "desc" else sort_by
        tickets = tickets.order_by(order)

    # Pagination
    try:
        per_page = min(int(request.GET.get("per_page", 25)), 100)
    except (ValueError, TypeError):
        per_page = 25

    paginator = Paginator(tickets, per_page)
    try:
        page_num = int(request.GET.get("page", 1))
    except (ValueError, TypeError):
        page_num = 1
    page = paginator.get_page(page_num)

    return JsonResponse({
        "data": ApiTicketCollectionSerializer.serialize_list(page.object_list),
        "meta": {
            "current_page": page.number,
            "last_page": paginator.num_pages,
            "per_page": per_page,
            "total": paginator.count,
        },
    })


@require_GET
def ticket_show(request, reference):
    """
    GET /tickets/<reference>

    Return full ticket details with replies and activities.
    """
    ticket, error = _resolve_ticket(reference)
    if error:
        return error

    return JsonResponse({
        "data": ApiTicketDetailSerializer.serialize(ticket),
    })


@csrf_exempt
@require_POST
def ticket_create(request):
    """
    POST /tickets

    Create a new ticket.

    JSON body:
        subject (required), description (required), priority, department_id, tags (array of IDs)
    """
    data = _json_body(request)

    # Validation
    subject = (data.get("subject") or "").strip()
    description = (data.get("description") or "").strip()

    if not subject:
        return JsonResponse(
            {"message": "Validation failed.", "errors": {"subject": "Subject is required."}},
            status=422,
        )
    if not description:
        return JsonResponse(
            {"message": "Validation failed.", "errors": {"description": "Description is required."}},
            status=422,
        )

    priority = data.get("priority", "medium")
    valid_priorities = [p.value for p in Ticket.Priority]
    if priority not in valid_priorities:
        return JsonResponse(
            {"message": "Validation failed.", "errors": {"priority": "Invalid priority."}},
            status=422,
        )

    service = TicketService()
    ticket_data = {
        "subject": subject,
        "description": description,
        "priority": priority,
        "channel": "api",
    }

    department_id = data.get("department_id")
    if department_id:
        ticket_data["department_id"] = department_id

    tag_ids = data.get("tags", [])
    if tag_ids:
        ticket_data["tag_ids"] = tag_ids

    ticket = service.create(request.user, ticket_data)

    # Reload with relations
    ticket = Ticket.objects.select_related(
        "assigned_to", "department"
    ).prefetch_related("tags").get(pk=ticket.pk)

    return JsonResponse(
        {
            "data": ApiTicketDetailSerializer.serialize(
                ticket, include_replies=False, include_activities=False
            ),
            "message": "Ticket created.",
        },
        status=201,
    )


@csrf_exempt
@require_POST
def ticket_reply(request, reference):
    """
    POST /tickets/<reference>/reply

    Add a reply or internal note to a ticket.

    JSON body:
        body (required), is_internal_note (optional bool)
    """
    ticket, error = _resolve_ticket(reference)
    if error:
        return error

    data = _json_body(request)
    body = (data.get("body") or "").strip()
    if not body:
        return JsonResponse(
            {"message": "Validation failed.", "errors": {"body": "Body is required."}},
            status=422,
        )

    is_note = data.get("is_internal_note", False)
    service = TicketService()

    if is_note:
        reply = service.add_note(ticket, request.user, body)
    else:
        reply = service.reply(ticket, request.user, {"body": body})

    user = request.user
    return JsonResponse(
        {
            "data": {
                "id": reply.pk,
                "body": reply.body,
                "is_internal_note": reply.is_internal_note,
                "author": {
                    "id": user.pk,
                    "name": getattr(user, "get_full_name", lambda: str(user))(),
                },
                "created_at": reply.created_at.isoformat(),
            },
            "message": "Note added." if is_note else "Reply sent.",
        },
        status=201,
    )


@csrf_exempt
@require_http_methods(["PATCH"])
def ticket_status(request, reference):
    """
    PATCH /tickets/<reference>/status

    Update ticket status.

    JSON body:
        status (required)
    """
    ticket, error = _resolve_ticket(reference)
    if error:
        return error

    data = _json_body(request)
    new_status = data.get("status")
    valid_statuses = [s.value for s in Ticket.Status]
    if new_status not in valid_statuses:
        return JsonResponse(
            {"message": "Validation failed.", "errors": {"status": "Invalid status."}},
            status=422,
        )

    service = TicketService()
    service.change_status(ticket, request.user, new_status)

    return JsonResponse({"message": "Status updated.", "status": new_status})


@csrf_exempt
@require_http_methods(["PATCH"])
def ticket_priority(request, reference):
    """
    PATCH /tickets/<reference>/priority

    Update ticket priority.

    JSON body:
        priority (required)
    """
    ticket, error = _resolve_ticket(reference)
    if error:
        return error

    data = _json_body(request)
    new_priority = data.get("priority")
    valid_priorities = [p.value for p in Ticket.Priority]
    if new_priority not in valid_priorities:
        return JsonResponse(
            {"message": "Validation failed.", "errors": {"priority": "Invalid priority."}},
            status=422,
        )

    service = TicketService()
    service.change_priority(ticket, request.user, new_priority)

    return JsonResponse({"message": "Priority updated.", "priority": new_priority})


@csrf_exempt
@require_POST
def ticket_assign(request, reference):
    """
    POST /tickets/<reference>/assign

    Assign ticket to an agent.

    JSON body:
        agent_id (required, integer)
    """
    ticket, error = _resolve_ticket(reference)
    if error:
        return error

    data = _json_body(request)
    agent_id = data.get("agent_id")
    if not agent_id:
        return JsonResponse(
            {"message": "Validation failed.", "errors": {"agent_id": "Agent ID is required."}},
            status=422,
        )

    try:
        agent = User.objects.get(pk=int(agent_id))
    except (User.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"message": "Agent not found."}, status=404)

    service = TicketService()
    service.assign(ticket, request.user, agent)

    return JsonResponse({"message": "Ticket assigned."})


@csrf_exempt
@require_POST
def ticket_follow(request, reference):
    """
    POST /tickets/<reference>/follow

    Toggle follow/unfollow on a ticket.
    """
    ticket, error = _resolve_ticket(reference)
    if error:
        return error

    user_id = request.user.pk

    if ticket.is_followed_by(user_id):
        ticket.unfollow(user_id)
        return JsonResponse({"message": "Unfollowed ticket.", "following": False})

    ticket.follow(user_id)
    return JsonResponse({"message": "Following ticket.", "following": True})


@csrf_exempt
@require_POST
def ticket_apply_macro(request, reference):
    """
    POST /tickets/<reference>/macro

    Apply a macro to a ticket.

    JSON body:
        macro_id (required, integer)
    """
    ticket, error = _resolve_ticket(reference)
    if error:
        return error

    data = _json_body(request)
    macro_id = data.get("macro_id")
    if not macro_id:
        return JsonResponse(
            {"message": "Validation failed.", "errors": {"macro_id": "Macro ID is required."}},
            status=422,
        )

    try:
        macro = Macro.objects.filter(
            Q(is_shared=True) | Q(created_by=request.user)
        ).get(pk=int(macro_id))
    except (Macro.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"message": "Macro not found."}, status=404)

    from escalated.services.macro_service import MacroService

    macro_service = MacroService()
    macro_service.apply(macro, ticket, request.user)

    return JsonResponse({"message": f'Macro "{macro.name}" applied.'})


@csrf_exempt
@require_POST
def ticket_tags(request, reference):
    """
    POST /tickets/<reference>/tags

    Sync tags on a ticket. Sends the desired list of tag IDs;
    tags not in the list are removed, tags in the list are added.

    JSON body:
        tag_ids (required, array of integers)
    """
    ticket, error = _resolve_ticket(reference)
    if error:
        return error

    data = _json_body(request)
    tag_ids = data.get("tag_ids")
    if tag_ids is None or not isinstance(tag_ids, list):
        return JsonResponse(
            {"message": "Validation failed.", "errors": {"tag_ids": "tag_ids array is required."}},
            status=422,
        )

    new_tag_ids = set(int(t) for t in tag_ids)
    current_tag_ids = set(ticket.tags.values_list("pk", flat=True))

    to_add = list(new_tag_ids - current_tag_ids)
    to_remove = list(current_tag_ids - new_tag_ids)

    service = TicketService()
    if to_add:
        service.add_tags(ticket, request.user, to_add)
    if to_remove:
        service.remove_tags(ticket, request.user, to_remove)

    return JsonResponse({"message": "Tags updated."})


@csrf_exempt
@require_http_methods(["DELETE"])
def ticket_destroy(request, reference):
    """
    DELETE /tickets/<reference>

    Delete (soft-delete) a ticket.
    """
    ticket, error = _resolve_ticket(reference)
    if error:
        return error

    ticket.delete()

    return JsonResponse({"message": "Ticket deleted."})


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@require_GET
def resource_agents(request):
    """
    GET /agents

    List all agents (users who belong to active departments or are staff).
    """
    users = User.objects.filter(is_active=True)
    agents = [u for u in users if is_agent(u) or is_admin(u)]

    return JsonResponse({"data": ApiAgentSerializer.serialize_list(agents)})


@require_GET
def resource_departments(request):
    """
    GET /departments

    List all active departments.
    """
    departments = Department.objects.filter(is_active=True)
    return JsonResponse({"data": ApiDepartmentSerializer.serialize_list(departments)})


@require_GET
def resource_tags(request):
    """
    GET /tags

    List all tags.
    """
    tags = Tag.objects.all()
    return JsonResponse({"data": ApiTagSerializer.serialize_list(tags)})


@require_GET
def resource_canned_responses(request):
    """
    GET /canned-responses

    List canned responses available to the authenticated user.
    """
    responses = CannedResponse.objects.filter(
        Q(is_shared=True) | Q(created_by=request.user)
    )
    return JsonResponse({"data": ApiCannedResponseSerializer.serialize_list(responses)})


@require_GET
def resource_macros(request):
    """
    GET /macros

    List macros available to the authenticated user.
    """
    macros = Macro.objects.filter(
        Q(is_shared=True) | Q(created_by=request.user)
    ).order_by("order")
    return JsonResponse({"data": ApiMacroSerializer.serialize_list(macros)})


@require_GET
def resource_realtime_config(request):
    """
    GET /realtime/config

    Return WebSocket/realtime configuration (if any).
    """
    # Django doesn't have a standard broadcasting config, so return null.
    # Consumers can override this in their project.
    return JsonResponse(None, safe=False)
