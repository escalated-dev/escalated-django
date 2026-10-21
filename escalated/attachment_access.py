"""
Private attachment delivery (the port of escalated-laravel's AttachmentAccess).

Serialized attachments carry a link to the ``escalated:attachment_download``
view instead of the file's MEDIA URL. The link is signed and expires after
``ATTACHMENT_DOWNLOAD_TTL_MINUTES`` (default 10, 1 to 60). Following it also
needs current access to the attachment's ticket:

- an agent or admin who can view the ticket;
- the ticket's requester, for attachments on the ticket and on public replies;
- a guest holding a link issued by a guest page for that ticket. The link is
  bound to the ticket's active guest grant, so renewing or revoking the grant
  revokes the link, and it never outlives the grant.

Attachments on internal notes are only ever served to agents and admins.
"""

import hashlib
import time
from contextlib import contextmanager
from contextvars import ContextVar

from django.core import signing
from django.urls import reverse

from escalated.conf import get_setting

SALT = "escalated.attachment-download"

_guest_ticket = ContextVar("escalated_attachment_guest_ticket", default=None)


@contextmanager
def for_guest(ticket):
    """Serialize inside this block to give a guest page's links the guest capability.

    Call only after the guest's credential for ``ticket`` has been checked.
    """
    token = _guest_ticket.set(ticket)
    try:
        yield
    finally:
        _guest_ticket.reset(token)


def ttl_seconds():
    try:
        minutes = int(get_setting("ATTACHMENT_DOWNLOAD_TTL_MINUTES") or 10)
    except (TypeError, ValueError):
        minutes = 10
    return max(1, min(60, minutes)) * 60


def parent_of(attachment):
    try:
        return attachment.content_object
    except Exception:
        return None


def ticket_of(attachment):
    from escalated.models import Reply, Ticket

    parent = parent_of(attachment)
    if isinstance(parent, Ticket):
        return parent
    if isinstance(parent, Reply):
        return parent.ticket
    return None


def is_public(attachment):
    """On the ticket itself or on a public reply; never on an internal note."""
    from escalated.models import Reply, Ticket

    parent = parent_of(attachment)
    return isinstance(parent, Ticket) or (isinstance(parent, Reply) and not parent.is_internal_note)


def guest_capability(ticket):
    """A digest of the ticket's current guest credential, or None if it has none.

    The credential is the active grant's nonce hash, so renewing or revoking
    the grant revokes every link issued with it. A legacy permanent token only
    counts while ``GUEST_ACCESS["LEGACY_TOKENS"]`` is on.
    """
    from escalated import guest_access

    if guest_access.active(ticket):
        secret = ticket.guest_access_hash
    elif guest_access.legacy_tokens_enabled():
        secret = getattr(ticket, "guest_token", None)
    else:
        secret = None
    if not secret:
        return None
    return hashlib.sha256(f"escalated-attachment:{secret}".encode()).hexdigest()


def download_url(attachment):
    """A signed, expiring link to download ``attachment``."""
    payload = {"a": attachment.pk}
    guest = _guest_ticket.get()
    if guest is not None and is_public(attachment):
        ticket = ticket_of(attachment)
        capability = guest_capability(guest)
        if ticket is not None and ticket.pk == guest.pk and capability:
            payload["g"] = capability
            if guest.guest_access_expires_at is not None:
                payload["x"] = int(guest.guest_access_expires_at.timestamp())
    token = signing.dumps(payload, salt=SALT, compress=True)
    return f"{reverse('escalated:attachment_download', args=[attachment.pk])}?token={token}"


def read_token(token, attachment_id):
    """The signed payload for ``attachment_id``, or None if it is invalid or expired."""
    if not isinstance(token, str) or not token:
        return None
    try:
        payload = signing.loads(token, salt=SALT, max_age=ttl_seconds())
    except signing.BadSignature:
        return None
    if not isinstance(payload, dict) or payload.get("a") != attachment_id:
        return None
    return payload


def is_requester(user, ticket):
    from django.contrib.contenttypes.models import ContentType

    if not user or not getattr(user, "is_authenticated", False) or ticket.requester_content_type_id is None:
        return False
    return ticket.requester_content_type_id == ContentType.objects.get_for_model(user).pk and str(
        ticket.requester_object_id
    ) == str(user.pk)


def allows(user, attachment, payload):
    """Whether this request may download ``attachment`` (signature already checked)."""
    from escalated.permissions import can_view_ticket, is_admin, is_agent

    ticket = ticket_of(attachment)
    if ticket is None:
        return False
    public = is_public(attachment)

    guest = payload.get("g")
    expires = payload.get("x")
    if isinstance(expires, int) and expires <= int(time.time()):
        guest = None
    if guest and public:
        capability = guest_capability(ticket)
        if capability and signing.constant_time_compare(capability, guest):
            return True

    if not user or not getattr(user, "is_authenticated", False):
        return False
    staff = is_agent(user) or is_admin(user)
    if staff:
        return can_view_ticket(user, ticket)
    return public and is_requester(user, ticket)
