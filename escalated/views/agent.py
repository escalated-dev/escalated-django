import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Q, Avg
from django.http import HttpResponseForbidden, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect
from inertia import render

from escalated.models import (
    Ticket,
    Tag,
    Department,
    CannedResponse,
    Macro,
    Reply,
    SatisfactionRating,
)
from escalated.permissions import is_agent, is_admin, can_view_ticket, can_update_ticket
from escalated.serializers import (
    TicketSerializer,
    ReplySerializer,
    TagSerializer,
    DepartmentSerializer,
    CannedResponseSerializer,
    ActivitySerializer,
    AttachmentSerializer,
    MacroSerializer,
    SatisfactionRatingSerializer,
)
from escalated.services.ticket_service import TicketService

User = get_user_model()


def _require_agent(request):
    """Return an error response if user is not an agent, else None."""
    if not request.user.is_authenticated:
        return redirect("login")
    if not is_agent(request.user) and not is_admin(request.user):
        return HttpResponseForbidden("Agent access required.")
    return None


@login_required
def dashboard(request):
    """Agent dashboard with ticket statistics."""
    check = _require_agent(request)
    if check:
        return check

    user = request.user
    my_tickets = Ticket.objects.assigned_to(user.pk)

    # CSAT stats
    avg_csat = SatisfactionRating.objects.aggregate(
        avg_rating=Avg("rating")
    )["avg_rating"]
    total_ratings = SatisfactionRating.objects.count()
    resolved_with_rating = SatisfactionRating.objects.filter(
        ticket__status__in=[Ticket.Status.RESOLVED, Ticket.Status.CLOSED]
    ).count()

    stats = {
        "total_open": Ticket.objects.open().count(),
        "my_open": my_tickets.open().count(),
        "unassigned": Ticket.objects.unassigned().open().count(),
        "breached_sla": Ticket.objects.breached_sla().open().count(),
        "by_priority": {
            p.value: Ticket.objects.open().filter(priority=p.value).count()
            for p in Ticket.Priority
        },
        "by_status": {
            s.value: Ticket.objects.filter(status=s.value).count()
            for s in Ticket.Status
        },
        "avg_csat_rating": round(avg_csat, 1) if avg_csat else None,
        "total_ratings": total_ratings,
        "resolved_with_rating_count": resolved_with_rating,
    }

    recent_tickets = my_tickets.open().select_related(
        "department"
    ).prefetch_related("tags")[:10]

    return render(request, "Escalated/Agent/Dashboard", props={
        "stats": stats,
        "recent_tickets": TicketSerializer.serialize_list(recent_tickets),
    })


@login_required
def ticket_list(request):
    """List tickets visible to the agent with filters."""
    check = _require_agent(request)
    if check:
        return check

    tickets = Ticket.objects.select_related(
        "assigned_to", "department"
    ).prefetch_related("tags")

    # Apply filters
    status = request.GET.get("status")
    if status:
        tickets = tickets.filter(status=status)

    priority = request.GET.get("priority")
    if priority:
        tickets = tickets.filter(priority=priority)

    assigned = request.GET.get("assigned")
    if assigned == "me":
        tickets = tickets.filter(assigned_to=request.user)
    elif assigned == "unassigned":
        tickets = tickets.filter(assigned_to__isnull=True)
    elif assigned:
        tickets = tickets.filter(assigned_to_id=assigned)

    department = request.GET.get("department")
    if department:
        tickets = tickets.filter(department_id=department)

    tag = request.GET.get("tag")
    if tag:
        tickets = tickets.filter(tags__slug=tag)

    search = request.GET.get("search")
    if search:
        tickets = tickets.search(search)

    # Following filter
    following = request.GET.get("following")
    if following:
        tickets = tickets.filter(ticket_followers__user=request.user)

    sort = request.GET.get("sort", "-created_at")
    allowed_sorts = [
        "created_at", "-created_at", "priority", "-priority",
        "updated_at", "-updated_at",
    ]
    if sort in allowed_sorts:
        tickets = tickets.order_by(sort)

    paginator = Paginator(tickets, 25)
    page = paginator.get_page(request.GET.get("page", 1))

    return render(request, "Escalated/Agent/Tickets/Index", props={
        "tickets": TicketSerializer.serialize_list(page.object_list),
        "pagination": {
            "current_page": page.number,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
        },
        "filters": {
            "status": status,
            "priority": priority,
            "assigned": assigned,
            "department": department,
            "tag": tag,
            "search": search,
            "sort": sort,
            "following": following,
        },
        "statuses": [{"value": s.value, "label": s.label} for s in Ticket.Status],
        "priorities": [{"value": p.value, "label": p.label} for p in Ticket.Priority],
        "departments": DepartmentSerializer.serialize_list(
            Department.objects.filter(is_active=True)
        ),
        "tags": TagSerializer.serialize_list(Tag.objects.all()),
    })


@login_required
def ticket_show(request, ticket_id):
    """Show a ticket with all details for an agent."""
    check = _require_agent(request)
    if check:
        return check

    try:
        ticket = Ticket.objects.select_related(
            "assigned_to", "department", "sla_policy"
        ).prefetch_related(
            "tags",
            "replies__author",
            "replies__attachments",
            "activities",
            "attachments",
        ).get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found")

    if not can_view_ticket(request.user, ticket):
        return HttpResponseForbidden("You cannot view this ticket.")

    replies = ticket.replies.filter(is_deleted=False).select_related("author")
    activities = ticket.activities.all()[:50]

    # Available agents for assignment
    agents = User.objects.filter(
        escalated_departments__is_active=True
    ).distinct()

    canned_responses = CannedResponse.objects.filter(
        Q(is_shared=True) | Q(created_by=request.user)
    )

    # Macros available to this agent (shared + own)
    macros = Macro.objects.filter(
        Q(is_shared=True) | Q(created_by=request.user)
    ).order_by("order")

    # Pinned notes
    pinned_notes = ticket.replies.filter(
        is_deleted=False, is_internal_note=True, is_pinned=True
    ).select_related("author")

    # Satisfaction rating
    try:
        satisfaction_rating = ticket.satisfaction_rating
        satisfaction_data = SatisfactionRatingSerializer.serialize(satisfaction_rating)
    except SatisfactionRating.DoesNotExist:
        satisfaction_data = None

    return render(request, "Escalated/Agent/Tickets/Show", props={
        "ticket": TicketSerializer.serialize(ticket),
        "replies": ReplySerializer.serialize_list(replies),
        "activities": [ActivitySerializer.serialize(a) for a in activities],
        "attachments": AttachmentSerializer.serialize_list(ticket.attachments.all()),
        "agents": [
            {"id": a.pk, "name": a.get_full_name() or a.username, "email": a.email}
            for a in agents
        ],
        "departments": DepartmentSerializer.serialize_list(
            Department.objects.filter(is_active=True)
        ),
        "tags": TagSerializer.serialize_list(Tag.objects.all()),
        "canned_responses": CannedResponseSerializer.serialize_list(canned_responses),
        "macros": MacroSerializer.serialize_list(macros),
        "statuses": [{"value": s.value, "label": s.label} for s in Ticket.Status],
        "priorities": [{"value": p.value, "label": p.label} for p in Ticket.Priority],
        "can_update": can_update_ticket(request.user, ticket),
        "is_following": ticket.is_followed_by(request.user.pk),
        "followers_count": ticket.followers_count,
        "pinned_notes": ReplySerializer.serialize_list(pinned_notes),
        "satisfaction_rating": satisfaction_data,
    })


@login_required
def ticket_update(request, ticket_id):
    """Update ticket fields (subject, description)."""
    check = _require_agent(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found")

    if not can_update_ticket(request.user, ticket):
        return HttpResponseForbidden("You cannot update this ticket.")

    service = TicketService()
    data = {}
    if "subject" in request.POST:
        data["subject"] = request.POST["subject"]
    if "description" in request.POST:
        data["description"] = request.POST["description"]

    service.update(ticket, request.user, data)
    return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)


@login_required
def ticket_reply(request, ticket_id):
    """Agent reply to a ticket."""
    check = _require_agent(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found")

    body = request.POST.get("body", "").strip()
    if not body:
        return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)

    service = TicketService()
    reply = service.reply(ticket, request.user, {"body": body})

    # Handle attachments
    files = request.FILES.getlist("attachments")
    if files:
        from escalated.services.attachment_service import AttachmentService
        from escalated.conf import get_setting
        for f in files[:get_setting("MAX_ATTACHMENTS")]:
            try:
                AttachmentService.attach(reply, f)
            except Exception:
                pass

    return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)


@login_required
def ticket_note(request, ticket_id):
    """Add an internal note to a ticket."""
    check = _require_agent(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found")

    body = request.POST.get("body", "").strip()
    if not body:
        return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)

    service = TicketService()
    service.add_note(ticket, request.user, body)

    return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)


@login_required
def ticket_assign(request, ticket_id):
    """Assign a ticket to an agent."""
    check = _require_agent(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found")

    agent_id = request.POST.get("agent_id")
    if not agent_id:
        # Unassign
        service = TicketService()
        service.unassign(ticket, request.user)
    else:
        try:
            agent = User.objects.get(pk=agent_id)
        except User.DoesNotExist:
            return HttpResponseNotFound("Agent not found")

        service = TicketService()
        service.assign(ticket, request.user, agent)

    return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)


@login_required
def ticket_status(request, ticket_id):
    """Change ticket status."""
    check = _require_agent(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found")

    new_status = request.POST.get("status")
    valid_statuses = [s.value for s in Ticket.Status]
    if new_status not in valid_statuses:
        return HttpResponseForbidden("Invalid status.")

    service = TicketService()
    service.change_status(ticket, request.user, new_status)

    return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)


@login_required
def ticket_priority(request, ticket_id):
    """Change ticket priority."""
    check = _require_agent(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found")

    new_priority = request.POST.get("priority")
    valid_priorities = [p.value for p in Ticket.Priority]
    if new_priority not in valid_priorities:
        return HttpResponseForbidden("Invalid priority.")

    service = TicketService()
    service.change_priority(ticket, request.user, new_priority)

    return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)


@login_required
def ticket_tags(request, ticket_id):
    """Add or remove tags from a ticket."""
    check = _require_agent(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found")

    service = TicketService()

    add_tags = request.POST.getlist("add_tags")
    if add_tags:
        service.add_tags(ticket, request.user, [int(t) for t in add_tags])

    remove_tags = request.POST.getlist("remove_tags")
    if remove_tags:
        service.remove_tags(ticket, request.user, [int(t) for t in remove_tags])

    return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)


@login_required
def ticket_department(request, ticket_id):
    """Change ticket department."""
    check = _require_agent(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found")

    department_id = request.POST.get("department_id")
    try:
        department = Department.objects.get(pk=department_id)
    except Department.DoesNotExist:
        return HttpResponseNotFound("Department not found")

    service = TicketService()
    service.change_department(ticket, request.user, department)

    return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)


# ---------------------------------------------------------------------------
# Bulk Actions
# ---------------------------------------------------------------------------


@login_required
def ticket_bulk_action(request):
    """Perform bulk actions on multiple tickets."""
    check = _require_agent(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        body = request.POST

    action = body.get("action", "")
    ticket_ids = body.get("ticket_ids", [])
    value = body.get("value")

    if not action or not ticket_ids:
        return redirect("escalated:agent_ticket_list")

    service = TicketService()
    user = request.user
    success_count = 0

    tickets = Ticket.objects.filter(pk__in=ticket_ids)

    for ticket in tickets:
        try:
            if action == "assign":
                if value:
                    try:
                        agent = User.objects.get(pk=int(value))
                        service.assign(ticket, user, agent)
                    except User.DoesNotExist:
                        continue
                else:
                    service.unassign(ticket, user)
            elif action == "status":
                valid_statuses = [s.value for s in Ticket.Status]
                if value in valid_statuses:
                    service.change_status(ticket, user, value)
            elif action == "priority":
                valid_priorities = [p.value for p in Ticket.Priority]
                if value in valid_priorities:
                    service.change_priority(ticket, user, value)
            elif action == "tag":
                tag_ids = value if isinstance(value, list) else [value]
                service.add_tags(ticket, user, [int(t) for t in tag_ids])
            elif action == "close":
                service.close(ticket, user)
            elif action == "delete":
                ticket.delete()
            else:
                continue
            success_count += 1
        except Exception:
            pass

    return redirect("escalated:agent_ticket_list")


# ---------------------------------------------------------------------------
# Apply Macro
# ---------------------------------------------------------------------------


@login_required
def ticket_apply_macro(request, ticket_id):
    """Apply a macro to a ticket."""
    check = _require_agent(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found")

    macro_id = request.POST.get("macro_id")
    if not macro_id:
        return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)

    try:
        macro = Macro.objects.filter(
            Q(is_shared=True) | Q(created_by=request.user)
        ).get(pk=macro_id)
    except Macro.DoesNotExist:
        return HttpResponseNotFound("Macro not found")

    from escalated.services.macro_service import MacroService
    macro_service = MacroService()
    macro_service.apply(macro, ticket, request.user)

    return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)


# ---------------------------------------------------------------------------
# Follow / Unfollow
# ---------------------------------------------------------------------------


@login_required
def ticket_follow(request, ticket_id):
    """Toggle follow/unfollow on a ticket."""
    check = _require_agent(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found")

    user_id = request.user.pk

    if ticket.is_followed_by(user_id):
        ticket.unfollow(user_id)
    else:
        ticket.follow(user_id)

    return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)


# ---------------------------------------------------------------------------
# Presence Indicators
# ---------------------------------------------------------------------------


@login_required
def ticket_presence(request, ticket_id):
    """Report presence on a ticket and return other viewers."""
    check = _require_agent(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found")

    user_id = request.user.pk
    user_name = request.user.get_full_name() or request.user.username
    cache_key = f"escalated.presence.{ticket.pk}.{user_id}"

    # Store this user's presence with 30s TTL
    cache.set(cache_key, {"id": user_id, "name": user_name}, 30)

    # Track active user IDs for this ticket (with 120s TTL)
    list_key = f"escalated.presence_list.{ticket.pk}"
    active_ids = cache.get(list_key, [])
    if user_id not in active_ids:
        active_ids.append(user_id)
    cache.set(list_key, active_ids, 120)

    # Collect viewers (other users who are still present)
    viewers = []
    for uid in active_ids:
        if uid != user_id:
            viewer_data = cache.get(f"escalated.presence.{ticket.pk}.{uid}")
            if viewer_data:
                viewers.append(viewer_data)

    return JsonResponse({"viewers": viewers})


# ---------------------------------------------------------------------------
# Pin / Unpin Reply
# ---------------------------------------------------------------------------


@login_required
def ticket_pin_reply(request, ticket_id, reply_id):
    """Toggle pin on an internal note."""
    check = _require_agent(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found")

    try:
        reply = Reply.objects.get(pk=reply_id, ticket=ticket)
    except Reply.DoesNotExist:
        return HttpResponseNotFound("Reply not found")

    if not reply.is_internal_note:
        return HttpResponseForbidden("Only internal notes can be pinned.")

    reply.is_pinned = not reply.is_pinned
    reply.save(update_fields=["is_pinned", "updated_at"])

    return redirect("escalated:agent_ticket_show", ticket_id=ticket_id)
