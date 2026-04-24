"""
Email threading support for outbound emails.

Delegates to :mod:`escalated.mail.message_id_util` so the Message-ID
format matches the canonical NestJS reference
(``<ticket-{id}@{domain}>`` / ``<ticket-{id}-reply-{replyId}@{domain}>``)
and the inbound adapters' Reply-To verification has something to check
against.

Also provides :func:`get_signed_reply_to` for setting the Reply-To
header on outbound messages when ``ESCALATED_EMAIL_INBOUND_SECRET`` is
configured — inbound providers verify the HMAC prefix before routing
replies to tickets.
"""

from django.conf import settings

from escalated.conf import get_setting
from escalated.mail.message_id_util import (
    build_message_id,
    build_reply_to,
)
from escalated.models import EscalatedSetting


def get_email_domain():
    """Return the domain used for Message-ID generation.

    Resolution order (first non-blank wins):
      1. ``EscalatedSetting("email_domain")`` — admin-configurable
      2. ``ESCALATED_EMAIL_DOMAIN`` Django setting
      3. Host portion of ``DEFAULT_FROM_EMAIL``
      4. ``"escalated.dev"``
    """
    domain = EscalatedSetting.get("email_domain")
    if domain:
        return domain
    configured = get_setting("EMAIL_DOMAIN")
    if configured:
        return configured
    default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "support@escalated.dev")
    if "@" in default_from:
        return default_from.split("@", 1)[1]
    return "escalated.dev"


def get_inbound_secret():
    """Return the HMAC secret used to sign Reply-To addresses.

    Returns an empty string when unset — callers MUST treat that as
    "skip signed Reply-To".
    """
    return get_setting("EMAIL_INBOUND_SECRET") or ""


def make_message_id(ticket):
    """Canonical Message-ID for the ticket root (initial notification)."""
    return build_message_id(ticket.pk, None, get_email_domain())


def make_reply_message_id(ticket, reply):
    """Canonical Message-ID for a reply, threaded off the ticket root."""
    return build_message_id(ticket.pk, reply.pk, get_email_domain())


def get_threading_headers(ticket, reply=None):
    """
    Return a dict of email headers for threading.

    For new ticket notifications:
        - Message-ID is set (anchor for the thread)

    For reply notifications:
        - Message-ID for this specific reply
        - In-Reply-To pointing to the ticket's Message-ID
        - References listing the ticket's Message-ID
    """
    headers = {}
    ticket_msg_id = make_message_id(ticket)

    if reply is None:
        # New ticket notification — anchor the thread.
        headers["Message-ID"] = ticket_msg_id
    else:
        headers["Message-ID"] = make_reply_message_id(ticket, reply)
        headers["In-Reply-To"] = ticket_msg_id
        headers["References"] = ticket_msg_id

    return headers


def get_signed_reply_to(ticket):
    """
    Return the signed Reply-To address for a ticket, or ``None`` when
    no inbound secret is configured.

    The HMAC prefix on the local part means inbound provider webhooks
    can verify ticket identity without trusting the mail client's
    threading headers.
    """
    secret = get_inbound_secret()
    if not secret:
        return None
    return build_reply_to(ticket.pk, secret, get_email_domain())


def get_branding_context():
    """
    Return branding settings for email templates.

    Returns a dict with email_logo_url, email_accent_color, email_footer_text.
    """
    return {
        "email_logo_url": EscalatedSetting.get("email_logo_url", ""),
        "email_accent_color": EscalatedSetting.get("email_accent_color", "#4f46e5"),
        "email_footer_text": EscalatedSetting.get(
            "email_footer_text",
            "This is an automated message from the support system.",
        ),
    }
