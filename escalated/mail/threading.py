"""
Email threading support for outbound emails.

Generates Message-ID, In-Reply-To, and References headers so that email
clients can group ticket conversations into a single thread.
"""

from django.conf import settings

from escalated.models import EscalatedSetting


def get_email_domain():
    """Return the domain used for Message-ID generation."""
    domain = EscalatedSetting.get("email_domain")
    if domain:
        return domain
    default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "support@escalated.dev")
    if "@" in default_from:
        return default_from.split("@", 1)[1]
    return "escalated.dev"


def make_message_id(ticket):
    """Generate a Message-ID for the initial ticket notification."""
    domain = get_email_domain()
    return f"<ticket-{ticket.pk}-{ticket.reference}@{domain}>"


def make_reply_message_id(ticket, reply):
    """Generate a Message-ID for a reply notification."""
    domain = get_email_domain()
    return f"<ticket-{ticket.pk}-reply-{reply.pk}@{domain}>"


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
        # New ticket notification
        headers["Message-ID"] = ticket_msg_id
    else:
        # Reply notification
        headers["Message-ID"] = make_reply_message_id(ticket, reply)
        headers["In-Reply-To"] = ticket_msg_id
        headers["References"] = ticket_msg_id

    return headers


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
