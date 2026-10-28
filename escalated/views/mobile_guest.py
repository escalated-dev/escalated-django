"""
The mobile guest API under ``<API_PREFIX>/mobile/guest/`` (registered only
when ``API_ENABLED``). Canonical contract:
https://github.com/escalated-dev/escalated-developer-context/blob/main/domain-model/mobile-guest-api.md

These are the mobile face of verified guest access (docs/guest-access.md):
the same emailed codes (``guest_access.challenge``/``consume``), the same
grants (``guest_access.issue``/``resolve``), the same per-IP guest buckets
(``guest_throttle``) and the same guest identity policy as the browser and
widget routes. Only the prefix and the payload shapes differ.

There is no API token and no session: proof is the emailed code, then the
grant in the URL. A bad, expired, rotated or non-ticket grant is a 404.
"""

import uuid
from functools import wraps

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from escalated import attachment_access, guest_access, guest_throttle
from escalated.conf import get_setting
from escalated.models import Contact, Department, EscalatedSetting, Ticket
from escalated.signals import ticket_created
from escalated.views import guest_verification
from escalated.views.api_auth import public_api

MAX_TEXT = 65535


def guest_route(view):
    """Public, CSRF-exempt, counted against the guest request budget, and never cached.

    The privacy headers go on every answer, errors included.
    """

    @csrf_exempt
    @public_api
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        retry_after = guest_throttle.check(request, guest_throttle.REQUESTS)
        if retry_after is not None:
            response = guest_throttle.too_many_requests(retry_after, json=True)
        else:
            response = view(request, *args, **kwargs)
        return guest_verification.private(response)

    return wrapped


def _method(request, method):
    if request.method != method:
        return JsonResponse({"message": "Method not allowed."}, status=405)
    return None


def _not_found():
    return JsonResponse({"message": "Ticket not found."}, status=404)


def _too_many(request, scope):
    retry_after = guest_throttle.check(request, scope)
    return None if retry_after is None else guest_throttle.too_many_requests(retry_after, json=True)


def _text(body, key):
    value = body.get(key)
    return value.strip() if isinstance(value, str) else ""


def _email_error(email):
    if not email or len(email) > 255:
        return "Enter a valid email address."
    try:
        validate_email(email)
    except ValidationError:
        return "Enter a valid email address."
    return None


def _uploads(request):
    if not request.FILES:
        return []
    return request.FILES.getlist("attachments") + request.FILES.getlist("attachments[]")


def _attachment_errors(files):
    max_count = int(get_setting("MAX_ATTACHMENTS"))
    max_kb = int(get_setting("MAX_ATTACHMENT_SIZE_KB"))
    if len(files) > max_count:
        return {"attachments": f"You may attach at most {max_count} files."}
    for upload in files:
        if getattr(upload, "size", 0) > max_kb * 1024:
            return {"attachments": f"Each attachment must be at most {max_kb} KB."}
    return {}


def _attach(target, files):
    if not files:
        return
    from escalated.services.attachment_service import AttachmentService

    for upload in files:
        AttachmentService.attach(target, upload)


# ---------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------


def _iso(value):
    return value.isoformat() if value else None


def _display_name(user):
    if user is None:
        return None
    name = getattr(user, "get_full_name", lambda: "")() or getattr(user, "name", "") or ""
    return name if isinstance(name, str) and name.strip() else None


def _requester(ticket):
    return {"name": ticket.guest_name or "Guest", "email": ticket.guest_email or ""}


def _reply_author(ticket, reply):
    if reply.author_id is None:
        return {"id": 0, **_requester(ticket)}
    return {"id": 0, "name": _display_name(reply.author) or "Support", "email": ""}


def _attachment(attachment):
    return {
        "id": attachment.pk,
        "filename": attachment.original_filename,
        "mime_type": attachment.mime_type,
        "size": attachment.size,
        "url": attachment_access.download_url(attachment),
    }


def mobile_ticket(ticket, token=None, replies=()):
    """The allow-listed mobile ticket object. Never the model: no metadata, notes or staff emails."""
    with attachment_access.for_guest(ticket):
        reply_rows = [
            {
                "id": reply.pk,
                "body": reply.body,
                "is_internal_note": False,
                "is_pinned": bool(reply.is_pinned),
                "author": _reply_author(ticket, reply),
                "attachments": [_attachment(a) for a in reply.attachments.all()],
                "created_at": _iso(reply.created_at),
            }
            for reply in replies
            if not reply.is_internal_note
        ]
    assignee = ticket.assigned_to if ticket.assigned_to_id else None
    return {
        "id": ticket.pk,
        "reference": ticket.reference,
        "guest_access_token": token,
        "guest_access_expires_at": _iso(ticket.guest_access_expires_at) if token else None,
        "subject": ticket.subject,
        "description": ticket.description or "",
        "status": {"value": ticket.status, "label": str(ticket.get_status_display())},
        "priority": {"value": ticket.priority, "label": str(ticket.get_priority_display())},
        "channel": ticket.channel,
        "metadata": {},
        "requester": _requester(ticket),
        "assignee": (
            {"id": 0, "name": _display_name(assignee) or "Support", "email": ""} if assignee is not None else None
        ),
        "department": ({"id": ticket.department.pk, "name": ticket.department.name} if ticket.department_id else None),
        "tags": [],
        "replies": reply_rows,
        "activities": [],
        "sla": {
            "first_response_due_at": _iso(ticket.first_response_due_at),
            "first_response_at": _iso(ticket.first_response_at),
            "first_response_breached": bool(ticket.sla_first_response_breached),
            "resolution_due_at": _iso(ticket.resolution_due_at),
            "resolution_breached": bool(ticket.sla_resolution_breached),
        },
        "is_following": False,
        "followers_count": 0,
        "resolved_at": _iso(ticket.resolved_at),
        "closed_at": _iso(ticket.closed_at),
        "created_at": _iso(ticket.created_at),
        "updated_at": _iso(ticket.updated_at),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@guest_route
def verification(request):
    """POST guest/verification: the shared handler (submissions bucket)."""
    return guest_verification.verification(request)


@guest_route
def lookup(request):
    """POST guest/lookup: the shared handler (replies bucket)."""
    return guest_verification.lookup(request)


@guest_route
def tickets(request):
    """POST guest/tickets: create a ticket after proving the email. 201 with a grant."""
    error = _method(request, "POST") or _too_many(request, guest_throttle.TICKET)
    if error is not None:
        return error
    if not EscalatedSetting.guest_tickets_enabled():
        return JsonResponse({"message": "Guest tickets are not enabled."}, status=403)

    body = guest_verification.json_body(request)
    name = _text(body, "name")
    email = guest_access.normalize_email(_text(body, "email"))
    subject = _text(body, "subject")
    description = _text(body, "description")
    priority = body.get("priority") or get_setting("DEFAULT_PRIORITY")
    department_id = body.get("department_id") or None
    files = _uploads(request)

    errors = {}
    if not name or len(name) > 255:
        errors["name"] = "The name field is required (at most 255 characters)."
    email_error = _email_error(email)
    if email_error:
        errors["email"] = email_error
    if not subject or len(subject) > 255:
        errors["subject"] = "The subject field is required (at most 255 characters)."
    if not description or len(description) > MAX_TEXT:
        errors["description"] = "The description field is required (at most 65535 characters)."
    if priority not in Ticket.Priority.values:
        errors["priority"] = "The selected priority is invalid."
    department = None
    if department_id is not None:
        try:
            department = Department.objects.filter(pk=int(department_id)).first()
        except (TypeError, ValueError):
            department = None
        if department is None:
            errors["department_id"] = "The selected department is invalid."
    errors.update(guest_verification.proof_errors(body))
    if "verification_id" not in errors:
        try:
            uuid.UUID(str(body.get("verification_id")))
        except ValueError:
            errors["verification_id"] = "The verification id must be a valid UUID."
    errors.update(_attachment_errors(files))
    if errors:
        return guest_verification.validation_error(errors)

    def create():
        contact = Contact.find_or_create_by_email(email, name)

        from escalated.views.widget import _apply_guest_policy

        attrs = _apply_guest_policy(
            {
                "guest_name": name,
                "guest_email": email,
                "subject": subject,
                "description": description,
                "priority": priority,
                "channel": "web",
                "department": department,
                "contact": contact,
            }
        )
        ticket = Ticket.objects.create(**attrs)
        _attach(ticket, files)
        guest_access.mark_verified(ticket, email)
        return ticket, guest_access.issue(ticket)

    # Spending the code, the contact, the ticket, its attachments and the grant
    # commit together; a failure rolls back and leaves the code usable.
    try:
        ticket, token = guest_access.consume(
            body["verification_id"], body["verification_code"], email, "ticket", create
        )
    except guest_access.InvalidCode as exc:
        return guest_verification.validation_error({"verification_code": str(exc)})

    # SLA, the created activity, notifications, webhooks and workflows hang off this signal.
    ticket_created.send(sender=Ticket, ticket=ticket, user=None)

    ticket = Ticket.unrestricted.select_related("department", "assigned_to").get(pk=ticket.pk)
    return JsonResponse({"data": mobile_ticket(ticket, token), "message": "Ticket created."}, status=201)


@guest_route
def ticket_show(request, token):
    """GET guest/tickets/<grant>: the ticket with its public replies, newest first."""
    error = _method(request, "GET")
    if error is not None:
        return error
    found = guest_access.resolve(token)
    if found is None:
        return _not_found()
    ticket = Ticket.unrestricted.select_related("department", "assigned_to").get(pk=found.pk)
    replies = (
        ticket.replies.filter(is_internal_note=False, is_deleted=False)
        .select_related("author")
        .prefetch_related("attachments")
        .order_by("-created_at", "-pk")
    )
    return JsonResponse({"data": mobile_ticket(ticket, token, replies)})


@guest_route
def ticket_reply(request, token):
    """POST guest/tickets/<grant>/replies: a public reply from the guest."""
    error = _method(request, "POST") or _too_many(request, guest_throttle.REPLY)
    if error is not None:
        return error
    ticket = guest_access.resolve(token)
    if ticket is None:
        return _not_found()
    if ticket.status == Ticket.Status.CLOSED:
        return JsonResponse({"message": "This ticket is closed."}, status=422)

    body = guest_verification.json_body(request)
    text = body.get("body")
    email = _text(body, "email")
    files = _uploads(request)
    errors = {}
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        errors["body"] = "The body field is required (at most 65535 characters)."
    email_error = _email_error(email)
    if email_error:
        errors["email"] = email_error
    errors.update(_attachment_errors(files))
    if errors:
        return guest_verification.validation_error(errors)

    # A second factor on top of the grant, not a substitute for it.
    if guest_access.normalize_email(email) != guest_access.normalize_email(ticket.guest_email):
        return JsonResponse({"message": "The provided email does not match this ticket."}, status=403)

    from escalated.drivers import get_driver

    reply = get_driver().add_reply(ticket, None, {"body": text, "is_internal_note": False})
    _attach(reply, files)
    return JsonResponse({"message": "Reply sent."}, status=201)
