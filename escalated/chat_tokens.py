"""Widget chat tokens: the visitor's only credential for a live chat.

As in escalated-laravel, a chat token is an expiring grant. Only its SHA-256 is
stored (``ChatSession.customer_session_id``), and it stops working
``ESCALATED["GUEST_ACCESS"]["TTL_MINUTES"]`` after the chat starts (default
1440, clamped to 5 minutes .. 7 days). Unknown and expired tokens find nothing,
which every chat route answers with 404.

Chats started before tokens were hashed hold the plain token and no expiry. The
first request with such a token stores its hash and gives it a full lifetime, so
chats in progress during an upgrade keep working.
"""

import hashlib
import secrets

from django.utils import timezone

from escalated import guest_access


def hash_token(token):
    return hashlib.sha256(str(token).encode()).hexdigest()


def issue():
    """A new ``(token, digest, expires_at)``; return the token, store the rest."""
    token = secrets.token_hex(32)
    return token, hash_token(token), timezone.now() + guest_access.grant_ttl()


def find_session(token, queryset=None):
    """The chat session ``token`` unlocks, or ``None``."""
    from escalated.models import ChatSession

    if not token or not isinstance(token, str) or len(token) > 255:
        return None
    sessions = queryset if queryset is not None else ChatSession.objects.all()
    session = sessions.filter(customer_session_id=hash_token(token)).first()
    if session is None:
        session = sessions.filter(customer_session_id=token, customer_token_expires_at__isnull=True).first()
        if session is None:
            return None
        session.customer_session_id = hash_token(token)
    if session.customer_token_expires_at is None:
        session.customer_token_expires_at = timezone.now() + guest_access.grant_ttl()
        ChatSession.objects.filter(pk=session.pk).update(
            customer_session_id=session.customer_session_id,
            customer_token_expires_at=session.customer_token_expires_at,
        )
    if session.customer_token_expires_at <= timezone.now():
        return None
    return session
