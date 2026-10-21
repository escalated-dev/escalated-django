"""
The browser guest portal: create a ticket after proving the email address,
then read, reply to and rate it through an expiring grant in the URL.
See docs/guest-access.md.
"""

from django.http import HttpResponseForbidden, HttpResponseNotFound
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _

from escalated import attachment_access, guest_access, guest_throttle
from escalated.conf import get_setting
from escalated.models import Contact, Department, EscalatedSetting, SatisfactionRating, Ticket
from escalated.rendering import render_page
from escalated.request_data import request_data
from escalated.serializers import (
    AttachmentSerializer,
    DepartmentSerializer,
    ReplySerializer,
    TicketSerializer,
)
from escalated.views import guest_verification


def _guest_tickets_enabled():
    """Check if guest tickets feature is enabled."""
    return EscalatedSetting.guest_tickets_enabled()


def _create_props(extra=None):
    return {
        "departments": DepartmentSerializer.serialize_list(Department.objects.filter(is_active=True)),
        "priorities": [{"value": p.value, "label": p.label} for p in Ticket.Priority],
        "default_priority": get_setting("DEFAULT_PRIORITY"),
        # The shared Guest/Create page asks for an email code here before it
        # submits, and offers a lookup that renews links to existing tickets.
        "verification_url": reverse("escalated:guest_verification"),
        "lookup_url": reverse("escalated:guest_lookup"),
        **(extra or {}),
    }


def _private(response):
    return guest_verification.private(response)


def ticket_create(request):
    """Show the guest ticket creation form."""
    if not _guest_tickets_enabled():
        return HttpResponseNotFound(_("Guest tickets are not enabled."))

    return render_page(request, "Escalated/Guest/Create", props=_create_props())


def verification(request):
    """POST guest/verification: email a code (purpose ticket, chat or lookup)."""
    return guest_verification.verification(request)


def lookup(request):
    """POST guest/lookup: renew links to the caller's tickets by reference and proven email."""
    return guest_verification.lookup(request)


def ticket_store(request):
    """Handle guest ticket creation form submission."""
    if not _guest_tickets_enabled():
        return HttpResponseNotFound(_("Guest tickets are not enabled."))

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    retry_after = guest_throttle.check(request, guest_throttle.TICKET)
    if retry_after is not None:
        return guest_throttle.too_many_requests(retry_after)

    data = request_data(request)
    # The shared Guest/Create page posts guest_name/guest_email; older forms name/email.
    name = (data.get("guest_name") or data.get("name") or "").strip()
    email = (data.get("guest_email") or data.get("email") or "").strip()
    subject = data.get("subject", "").strip()
    description = data.get("description", "").strip()
    priority = data.get("priority", get_setting("DEFAULT_PRIORITY"))
    department_id = data.get("department_id") or None
    proof = {
        "verification_id": (data.get("verification_id") or "").strip(),
        "verification_code": (data.get("verification_code") or "").strip(),
    }

    # Validate required fields
    errors = {}
    if not name:
        errors["guest_name"] = _("Name is required.")
    if not email:
        errors["guest_email"] = _("Email is required.")
    if not subject:
        errors["subject"] = _("Subject is required.")
    if not description:
        errors["description"] = _("Description is required.")
    errors.update({field: _(message) for field, message in guest_verification.proof_errors(proof).items()})

    def invalid(errors):
        return render_page(
            request,
            "Escalated/Guest/Create",
            props=_create_props(
                {
                    "errors": errors,
                    "old": {
                        "guest_name": name,
                        "guest_email": email,
                        "subject": subject,
                        "description": description,
                        "priority": priority,
                        "department_id": department_id,
                    },
                }
            ),
        )

    if errors:
        return invalid(errors)

    files = request.FILES.getlist("attachments")

    def create():
        # Dedupe repeat guests by email (Pattern B). Inline guest_* fields
        # remain set for the backwards-compat dual-read period.
        contact = Contact.find_or_create_by_email(email, name)

        # Apply the admin-configured guest policy. See
        # escalated.views.widget._apply_guest_policy for the mode reference.
        from escalated.views.widget import _apply_guest_policy

        attrs = _apply_guest_policy(
            {
                "guest_name": name,
                "guest_email": email,
                "subject": subject,
                "description": description,
                "priority": priority,
                "department_id": department_id,
                "contact": contact,
            }
        )
        ticket = Ticket.objects.create(**attrs)

        if files:
            from escalated.services.attachment_service import AttachmentService

            for f in files[: get_setting("MAX_ATTACHMENTS")]:
                try:
                    AttachmentService.attach(ticket, f)
                except Exception:
                    pass

        guest_access.mark_verified(ticket, email)
        return ticket, guest_access.issue(ticket)

    # The ticket, its attachments and the code's consumption commit together.
    try:
        ticket, token = guest_access.consume(
            proof["verification_id"], proof["verification_code"], email, "ticket", create
        )
    except guest_access.InvalidCode as exc:
        return invalid({"verification_code": str(exc)})

    # SLA, the created activity, notifications, webhooks and workflows hang off this signal.
    from escalated.signals import ticket_created

    ticket_created.send(sender=Ticket, ticket=ticket, user=None)

    return redirect("escalated:guest_ticket_show", token=token)


def _ticket_for(token):
    return guest_access.ticket_for_token(token)


def ticket_show(request, token):
    """Show a guest ticket through its grant."""
    found = _ticket_for(token)
    if found is None:
        return _private(HttpResponseNotFound(_("Ticket not found.")))
    ticket = (
        Ticket.unrestricted.select_related("assigned_to", "department", "sla_policy")
        .prefetch_related("tags", "replies__author", "replies__attachments", "attachments")
        .get(pk=found.pk)
    )

    # Filter out internal notes for guest users
    replies = ticket.replies.filter(is_deleted=False, is_internal_note=False)

    # The guest's grant was just checked, so attachment links on this page may
    # carry a guest download capability bound to it.
    with attachment_access.for_guest(ticket):
        ticket_data = TicketSerializer.serialize(ticket)
        # Host-supplied data and agent emails are not for guests.
        ticket_data.pop("metadata", None)
        ticket_data.pop("requester", None)
        if ticket_data.get("assigned_to"):
            ticket_data["assigned_to"] = {"name": ticket_data["assigned_to"].get("name")}
        reply_data = ReplySerializer.serialize_list(replies)
        for reply in reply_data:
            reply.pop("metadata", None)
        props = {
            "ticket": ticket_data,
            "replies": reply_data,
            "attachments": AttachmentSerializer.serialize_list(ticket.attachments.all()),
            "token": token,
            "can_reply": ticket.is_open,
        }
    return _private(render_page(request, "Escalated/Guest/Show", props=props))


def ticket_reply(request, token):
    """Handle a guest reply submission."""
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    # Throttle before the token lookup so requests with a wrong token count too.
    retry_after = guest_throttle.check(request, guest_throttle.REPLY)
    if retry_after is not None:
        return guest_throttle.too_many_requests(retry_after)

    ticket = _ticket_for(token)
    if ticket is None:
        return HttpResponseNotFound(_("Ticket not found."))

    if not ticket.is_open:
        return HttpResponseForbidden(_("This ticket is closed."))

    body = request_data(request).get("body", "").strip()
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

        for f in files[: get_setting("MAX_ATTACHMENTS")]:
            try:
                AttachmentService.attach(reply_obj, f)
            except Exception:
                pass

    return redirect("escalated:guest_ticket_show", token=token)


def ticket_rate(request, token):
    """Allow a guest to rate a resolved/closed ticket."""
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    ticket = _ticket_for(token)
    if ticket is None:
        return HttpResponseNotFound(_("Ticket not found."))

    # Only allow rating resolved or closed tickets
    if ticket.status not in [Ticket.Status.RESOLVED, Ticket.Status.CLOSED]:
        return HttpResponseForbidden(_("You can only rate resolved or closed tickets."))

    # Check if already rated
    if SatisfactionRating.objects.filter(ticket=ticket).exists():
        return HttpResponseForbidden(_("This ticket has already been rated."))

    rating_value = request_data(request).get("rating")
    try:
        rating_value = int(rating_value)
        if not (1 <= rating_value <= 5):
            return HttpResponseForbidden(_("Rating must be between 1 and 5."))
    except (ValueError, TypeError):
        return HttpResponseForbidden(_("Invalid rating value."))

    comment = request_data(request).get("comment", "").strip() or None

    # Guest rating has no authenticated user, so rated_by is null
    SatisfactionRating.objects.create(
        ticket=ticket,
        rating=rating_value,
        comment=comment,
        rated_by_content_type=None,
        rated_by_object_id=None,
    )

    return redirect("escalated:guest_ticket_show", token=token)
