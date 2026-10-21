"""Test helper: a valid emailed-code proof without going through the mailbox."""

import uuid
from datetime import timedelta

from django.utils import timezone

from escalated import guest_access
from escalated.models import GuestVerification

CODE = "12345678"


def proof(email, purpose="ticket", code=CODE):
    """The ``verification_id``/``verification_code`` fields for a fresh code."""
    verification_id = uuid.uuid4()
    GuestVerification.objects.create(
        id=verification_id,
        email_digest=guest_access.email_digest(email),
        purpose=purpose,
        code_hash=guest_access.digest(f"{verification_id}:{code}"),
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    return {"verification_id": str(verification_id), "verification_code": code}


def grant(ticket, email=None):
    """Prove ``ticket``'s guest email and issue a grant for it."""
    guest_access.mark_verified(ticket, email or ticket.guest_email)
    return guest_access.issue(ticket)


def proven(body, purpose="ticket"):
    """``body`` plus a valid proof for its ``email`` (or ``guest_email``)."""
    email = body.get("email") or body.get("guest_email")
    return {**body, **proof(email, purpose)}


_PROVEN_ROUTES = ("widget/tickets", "widget/tickets/create/", "guest/store/", "chat/start", "chat/start/")


def with_proof(url, body):
    """Add a proof to a ticket-create or chat-start body that names an email but carries none.

    For tests written before verified guest access, whose subject is something else.
    """
    if (
        isinstance(body, dict)
        and (body.get("email") or body.get("guest_email"))
        and "verification_id" not in body
        and str(url).rstrip("/").endswith(tuple(route.rstrip("/") for route in _PROVEN_ROUTES))
    ):
        return proven(body, "chat" if "chat/start" in str(url) else "ticket")
    return body
