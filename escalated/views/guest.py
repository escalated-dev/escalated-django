import secrets

from django.http import HttpResponseForbidden, HttpResponseNotFound
from django.shortcuts import redirect
from inertia import render

from escalated.conf import get_setting
from escalated.models import Ticket, Department, EscalatedSetting, SatisfactionRating
from escalated.serializers import (
    TicketSerializer,
    ReplySerializer,
    DepartmentSerializer,
    AttachmentSerializer,
)


def _guest_tickets_enabled():
    """Check if guest tickets feature is enabled."""
    return EscalatedSetting.guest_tickets_enabled()


def ticket_create(request):
    """Show the guest ticket creation form."""
    if not _guest_tickets_enabled():
        return HttpResponseNotFound("Guest tickets are not enabled.")

    return render(request, "Escalated/Guest/Create", props={
        "departments": DepartmentSerializer.serialize_list(
            Department.objects.filter(is_active=True)
        ),
        "priorities": [
            {"value": p.value, "label": p.label} for p in Ticket.Priority
        ],
        "default_priority": get_setting("DEFAULT_PRIORITY"),
    })


def ticket_store(request):
    """Handle guest ticket creation form submission."""
    if not _guest_tickets_enabled():
        return HttpResponseNotFound("Guest tickets are not enabled.")

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    name = request.POST.get("name", "").strip()
    email = request.POST.get("email", "").strip()
    subject = request.POST.get("subject", "").strip()
    description = request.POST.get("description", "").strip()
    priority = request.POST.get("priority", get_setting("DEFAULT_PRIORITY"))
    department_id = request.POST.get("department_id") or None

    # Validate required fields
    errors = {}
    if not name:
        errors["name"] = "Name is required."
    if not email:
        errors["email"] = "Email is required."
    if not subject:
        errors["subject"] = "Subject is required."
    if not description:
        errors["description"] = "Description is required."

    if errors:
        return render(request, "Escalated/Guest/Create", props={
            "errors": errors,
            "old": {
                "name": name,
                "email": email,
                "subject": subject,
                "description": description,
                "priority": priority,
                "department_id": department_id,
            },
            "departments": DepartmentSerializer.serialize_list(
                Department.objects.filter(is_active=True)
            ),
            "priorities": [
                {"value": p.value, "label": p.label} for p in Ticket.Priority
            ],
            "default_priority": get_setting("DEFAULT_PRIORITY"),
        })

    # Generate a unique guest token
    guest_token = secrets.token_hex(32)  # 64-character hex string

    # Create ticket without requester (guest mode)
    ticket = Ticket.objects.create(
        requester_content_type=None,
        requester_object_id=None,
        guest_name=name,
        guest_email=email,
        guest_token=guest_token,
        subject=subject,
        description=description,
        priority=priority,
        department_id=department_id,
    )

    # Handle file attachments
    files = request.FILES.getlist("attachments")
    if files:
        from escalated.services.attachment_service import AttachmentService

        for f in files[:get_setting("MAX_ATTACHMENTS")]:
            try:
                AttachmentService.attach(ticket, f)
            except Exception:
                pass

    return redirect("escalated:guest_ticket_show", token=guest_token)


def ticket_show(request, token):
    """Show a guest ticket by its token."""
    try:
        ticket = Ticket.objects.select_related(
            "assigned_to", "department", "sla_policy"
        ).prefetch_related(
            "tags", "replies__author", "replies__attachments", "attachments"
        ).get(guest_token=token)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found.")

    # Filter out internal notes for guest users
    replies = ticket.replies.filter(is_deleted=False, is_internal_note=False)

    return render(request, "Escalated/Guest/Show", props={
        "ticket": TicketSerializer.serialize(ticket),
        "replies": ReplySerializer.serialize_list(replies),
        "attachments": AttachmentSerializer.serialize_list(ticket.attachments.all()),
        "token": token,
        "can_reply": ticket.is_open,
    })


def ticket_reply(request, token):
    """Handle a guest reply submission."""
    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(guest_token=token)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found.")

    if not ticket.is_open:
        return HttpResponseForbidden("This ticket is closed.")

    body = request.POST.get("body", "").strip()
    if not body:
        return redirect("escalated:guest_ticket_show", token=token)

    # Use the driver to create the reply so signals fire and notifications are sent
    from escalated.drivers import get_driver

    driver = get_driver()
    reply_data = {"body": body, "is_internal_note": False}
    reply_obj = driver.add_reply(ticket, None, reply_data)

    # Handle file attachments
    files = request.FILES.getlist("attachments")
    if files:
        from escalated.services.attachment_service import AttachmentService

        for f in files[:get_setting("MAX_ATTACHMENTS")]:
            try:
                AttachmentService.attach(reply_obj, f)
            except Exception:
                pass

    return redirect("escalated:guest_ticket_show", token=token)


def ticket_rate(request, token):
    """Allow a guest to rate a resolved/closed ticket."""
    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        ticket = Ticket.objects.get(guest_token=token)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound("Ticket not found.")

    # Only allow rating resolved or closed tickets
    if ticket.status not in [Ticket.Status.RESOLVED, Ticket.Status.CLOSED]:
        return HttpResponseForbidden("You can only rate resolved or closed tickets.")

    # Check if already rated
    if SatisfactionRating.objects.filter(ticket=ticket).exists():
        return HttpResponseForbidden("This ticket has already been rated.")

    rating_value = request.POST.get("rating")
    try:
        rating_value = int(rating_value)
        if not (1 <= rating_value <= 5):
            return HttpResponseForbidden("Rating must be between 1 and 5.")
    except (ValueError, TypeError):
        return HttpResponseForbidden("Invalid rating value.")

    comment = request.POST.get("comment", "").strip() or None

    # Guest rating has no authenticated user, so rated_by is null
    SatisfactionRating.objects.create(
        ticket=ticket,
        rating=rating_value,
        comment=comment,
        rated_by_content_type=None,
        rated_by_object_id=None,
    )

    return redirect("escalated:guest_ticket_show", token=token)
