"""
Pure helpers for RFC 5322 Message-ID threading and signed Reply-To
addresses. Mirrors the NestJS reference
``escalated-nestjs/src/services/email/message-id.ts`` and the Spring /
WordPress / .NET / Phoenix / Laravel / Rails ports.

Coexists with the existing :mod:`escalated.mail.threading` module during
the migration window — new outbound paths should prefer these helpers so
inbound Reply-To verification has something to check against.

Message-ID format::

    <ticket-{ticket_id}@{domain}>             initial ticket email
    <ticket-{ticket_id}-reply-{reply_id}@{domain}>  agent reply

Signed Reply-To format::

    reply+{ticket_id}.{hmac8}@{domain}

The signed Reply-To carries ticket identity even when clients strip the
Message-ID / In-Reply-To headers — the inbound provider webhook
verifies the 8-char HMAC-SHA256 prefix before routing a reply to its
ticket.
"""

from __future__ import annotations

import hmac
import re
from hashlib import sha256

_TICKET_ID_PATTERN = re.compile(r"ticket-(\d+)(?:-reply-\d+)?@", re.IGNORECASE)
_REPLY_LOCAL_PATTERN = re.compile(r"^reply\+(\d+)\.([a-f0-9]{8})$", re.IGNORECASE)


def build_message_id(ticket_id: int, reply_id: int | None, domain: str) -> str:
    """Build an RFC 5322 Message-ID.

    Pass ``None`` for ``reply_id`` on the initial ticket email; the
    ``-reply-{id}`` tail is appended only when ``reply_id`` is non-None.
    """
    if reply_id is None:
        body = f"ticket-{ticket_id}"
    else:
        body = f"ticket-{ticket_id}-reply-{reply_id}"
    return f"<{body}@{domain}>"


def parse_ticket_id_from_message_id(raw: str | None) -> int | None:
    """Extract the ticket id from a Message-ID we issued.

    Accepts the header value with or without angle brackets. Returns
    ``None`` when the input doesn't match our shape.
    """
    if not raw:
        return None
    match = _TICKET_ID_PATTERN.search(raw)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def build_reply_to(ticket_id: int, secret: str, domain: str) -> str:
    """Build a signed Reply-To address ``reply+{id}.{hmac8}@{domain}``."""
    return f"reply+{ticket_id}.{_sign(ticket_id, secret)}@{domain}"


def verify_reply_to(address: str | None, secret: str) -> int | None:
    """Verify a reply-to address (full or just the local part).

    Returns the ticket id on match, ``None`` otherwise. Uses
    :func:`hmac.compare_digest` for timing-safe verification.
    """
    if not address:
        return None
    local = address.split("@", 1)[0] if "@" in address else address
    match = _REPLY_LOCAL_PATTERN.match(local)
    if not match:
        return None
    try:
        ticket_id = int(match.group(1))
    except (TypeError, ValueError):
        return None
    expected = _sign(ticket_id, secret)
    if hmac.compare_digest(expected.lower(), match.group(2).lower()):
        return ticket_id
    return None


def _sign(ticket_id: int, secret: str) -> str:
    """8-character HMAC-SHA256 prefix over the ticket id."""
    digest = hmac.new(
        secret.encode("utf-8"),
        str(ticket_id).encode("utf-8"),
        sha256,
    ).hexdigest()
    return digest[:8]
