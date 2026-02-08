import secrets

from django.http import HttpResponseForbidden, HttpResponseNotFound
from django.shortcuts import redirect
from inertia import render

from escalated.conf import get_setting
from escalated.models import Ticket, Department, Reply, EscalatedSetting
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

    # Create reply without author (guest reply)
    Reply.objects.create(
        ticket=ticket,
        author=None,
        body=body,
        type=Reply.Type.REPLY,
    )

    # Update ticket status if needed
    if ticket.status == Ticket.Status.WAITING_ON_CUSTOMER:
        ticket.status = Ticket.Status.OPEN
        ticket.save(update_fields=["status", "updated_at"])

    # Handle file attachments
    files = request.FILES.getlist("attachments")
    if files:
        from escalated.services.attachment_service import AttachmentService

        reply = ticket.replies.order_by("-created_at").first()
        if reply:
            for f in files[:get_setting("MAX_ATTACHMENTS")]:
                try:
                    AttachmentService.attach(reply, f)
                except Exception:
                    pass

    return redirect("escalated:guest_ticket_show", token=token)
