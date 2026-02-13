from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden, HttpResponseNotFound
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from inertia import render

from escalated.conf import get_setting
from escalated.models import Ticket, Tag, Department, SatisfactionRating
from escalated.permissions import can_view_ticket, can_reply_ticket, can_close_ticket
from escalated.serializers import TicketSerializer, TagSerializer, DepartmentSerializer
from escalated.services.ticket_service import TicketService


@login_required
def ticket_list(request):
    """List all tickets for the authenticated customer."""
    ct = ContentType.objects.get_for_model(request.user)
    tickets = Ticket.objects.filter(
        requester_content_type=ct,
        requester_object_id=request.user.pk,
    ).select_related("assigned_to", "department").prefetch_related("tags")

    # Optional filtering
    status = request.GET.get("status")
    if status:
        tickets = tickets.filter(status=status)

    search = request.GET.get("search")
    if search:
        tickets = tickets.search(search)

    paginator = Paginator(tickets, 15)
    page = paginator.get_page(request.GET.get("page", 1))

    return render(request, "Escalated/Customer/Index", props={
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
            "search": search,
        },
        "statuses": [
            {"value": s.value, "label": s.label} for s in Ticket.Status
        ],
    })


@login_required
def ticket_create(request):
    """Show the ticket creation form."""
    return render(request, "Escalated/Customer/Create", props={
        "departments": DepartmentSerializer.serialize_list(
            Department.objects.filter(is_active=True)
        ),
        "priorities": [
            {"value": p.value, "label": p.label} for p in Ticket.Priority
        ],
        "default_priority": get_setting("DEFAULT_PRIORITY"),
    })


@login_required
def ticket_store(request):
    """Handle ticket creation form submission."""
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    service = TicketService()
    data = {
        "subject": request.POST.get("subject", ""),
        "description": request.POST.get("description", ""),
        "priority": request.POST.get("priority", get_setting("DEFAULT_PRIORITY")),
        "department_id": request.POST.get("department_id") or None,
    }

    # Validate required fields
    errors = {}
    if not data["subject"].strip():
        errors["subject"] = _("Subject is required.")
    if not data["description"].strip():
        errors["description"] = _("Description is required.")

    if errors:
        return render(request, "Escalated/Customer/Create", props={
            "errors": errors,
            "old": data,
            "departments": DepartmentSerializer.serialize_list(
                Department.objects.filter(is_active=True)
            ),
            "priorities": [
                {"value": p.value, "label": p.label} for p in Ticket.Priority
            ],
            "default_priority": get_setting("DEFAULT_PRIORITY"),
        })

    ticket = service.create(request.user, data)

    # Handle file attachments
    files = request.FILES.getlist("attachments")
    if files:
        from escalated.services.attachment_service import AttachmentService
        for f in files[:get_setting("MAX_ATTACHMENTS")]:
            try:
                AttachmentService.attach(ticket, f)
            except Exception:
                pass  # Non-blocking; attachment errors don't fail ticket creation

    from django.shortcuts import redirect
    return redirect("escalated:customer_ticket_show", ticket_id=ticket.pk)


@login_required
def ticket_show(request, ticket_id):
    """Show a single ticket and its replies."""
    try:
        ticket = Ticket.objects.select_related(
            "assigned_to", "department", "sla_policy"
        ).prefetch_related(
            "tags", "replies__author", "replies__attachments", "attachments"
        ).get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    if not can_view_ticket(request.user, ticket):
        return HttpResponseForbidden(_("You cannot view this ticket."))

    # Filter out internal notes for customers
    replies = ticket.replies.filter(is_deleted=False, is_internal_note=False)

    from escalated.serializers import ReplySerializer, AttachmentSerializer
    return render(request, "Escalated/Customer/Show", props={
        "ticket": TicketSerializer.serialize(ticket),
        "replies": ReplySerializer.serialize_list(replies),
        "attachments": AttachmentSerializer.serialize_list(ticket.attachments.all()),
        "can_reply": can_reply_ticket(request.user, ticket),
        "can_close": can_close_ticket(request.user, ticket),
    })


@login_required
def ticket_reply(request, ticket_id):
    """Handle customer reply submission."""
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    if not can_reply_ticket(request.user, ticket):
        return HttpResponseForbidden(_("You cannot reply to this ticket."))

    body = request.POST.get("body", "").strip()
    if not body:
        from django.shortcuts import redirect
        return redirect("escalated:customer_ticket_show", ticket_id=ticket_id)

    service = TicketService()
    reply = service.reply(ticket, request.user, {"body": body})

    # Handle file attachments on reply
    files = request.FILES.getlist("attachments")
    if files:
        from escalated.services.attachment_service import AttachmentService
        for f in files[:get_setting("MAX_ATTACHMENTS")]:
            try:
                AttachmentService.attach(reply, f)
            except Exception:
                pass

    from django.shortcuts import redirect
    return redirect("escalated:customer_ticket_show", ticket_id=ticket_id)


@login_required
def ticket_close(request, ticket_id):
    """Allow a customer to close their ticket."""
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    if not can_close_ticket(request.user, ticket):
        return HttpResponseForbidden(_("You cannot close this ticket."))

    service = TicketService()
    service.close(ticket, request.user)

    from django.shortcuts import redirect
    return redirect("escalated:customer_ticket_show", ticket_id=ticket_id)


@login_required
def ticket_reopen(request, ticket_id):
    """Allow a customer to reopen their ticket."""
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    ct = ContentType.objects.get_for_model(request.user)
    is_requester = (
        ticket.requester_content_type == ct
        and ticket.requester_object_id == request.user.pk
    )
    if not is_requester:
        return HttpResponseForbidden(_("You cannot reopen this ticket."))

    service = TicketService()
    service.reopen(ticket, request.user)

    return redirect("escalated:customer_ticket_show", ticket_id=ticket_id)


@login_required
def ticket_rate(request, ticket_id):
    """Allow a customer to rate a resolved/closed ticket."""
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    # Only allow rating resolved or closed tickets
    if ticket.status not in [Ticket.Status.RESOLVED, Ticket.Status.CLOSED]:
        return HttpResponseForbidden(_("You can only rate resolved or closed tickets."))

    # Check if already rated
    if SatisfactionRating.objects.filter(ticket=ticket).exists():
        return HttpResponseForbidden(_("This ticket has already been rated."))

    rating_value = request.POST.get("rating")
    try:
        rating_value = int(rating_value)
        if not (1 <= rating_value <= 5):
            return HttpResponseForbidden(_("Rating must be between 1 and 5."))
    except (ValueError, TypeError):
        return HttpResponseForbidden(_("Invalid rating value."))

    comment = request.POST.get("comment", "").strip() or None

    ct = ContentType.objects.get_for_model(request.user)
    SatisfactionRating.objects.create(
        ticket=ticket,
        rating=rating_value,
        comment=comment,
        rated_by_content_type=ct,
        rated_by_object_id=request.user.pk,
    )

    return redirect("escalated:customer_ticket_show", ticket_id=ticket_id)
