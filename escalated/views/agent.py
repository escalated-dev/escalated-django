from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, HttpResponseNotFound
from django.shortcuts import redirect
from inertia import render

from escalated.models import Ticket, Tag, Department, CannedResponse
from escalated.permissions import is_agent, is_admin, can_view_ticket, can_update_ticket
from escalated.serializers import (
    TicketSerializer,
    ReplySerializer,
    TagSerializer,
    DepartmentSerializer,
    CannedResponseSerializer,
    ActivitySerializer,
    AttachmentSerializer,
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
        "statuses": [{"value": s.value, "label": s.label} for s in Ticket.Status],
        "priorities": [{"value": p.value, "label": p.label} for p in Ticket.Priority],
        "can_update": can_update_ticket(request.user, ticket),
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
