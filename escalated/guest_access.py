"""
Verified guest access (the port of escalated-laravel's GuestEmailVerification
and GuestAccess). See docs/guest-access.md.

A guest proves they can read a mailbox with an eight-digit code emailed to it
(:func:`challenge`, then :func:`consume`). A proven ticket gets an expiring
grant (:func:`issue`): an opaque signed token whose random nonce is stored on
the ticket only as a SHA-256 hash. Issuing again rotates the nonce, which
revokes earlier grants and the attachment links issued with them.
"""

import hashlib
import hmac
import secrets
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.cache import caches
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import router, transaction
from django.utils import timezone

from escalated.conf import get_setting

PURPOSES = ("ticket", "chat", "lookup")
GRANT_PURPOSES = ("ticket",)
CODE_TTL_SECONDS = 600
MAX_ATTEMPTS = 5
GRANT_SALT = "escalated.guest-access"
INVALID_CODE = "This code is invalid, expired or already used. Request a new code."


class TooManyChallenges(Exception):
    def __init__(self, retry_after):
        super().__init__("Please wait before requesting another code.")
        self.retry_after = retry_after


class InvalidEmail(Exception):
    pass


class InvalidCode(Exception):
    pass


def normalize_email(email):
    return str(email or "").strip().lower()


def digest(value):
    """A keyed digest (SECRET_KEY) of ``value``; never stored or compared in the clear."""
    key = str(settings.SECRET_KEY).encode()
    return hmac.new(key, f"escalated-guest-email:{value}".encode(), hashlib.sha256).hexdigest()


def email_digest(email):
    return digest(normalize_email(email))


def _option(name, default, low, high):
    config = get_setting("GUEST_ACCESS") or {}
    try:
        value = int(config.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def grant_ttl():
    return timedelta(minutes=_option("TTL_MINUTES", 1440, 5, 10080))


# ---------------------------------------------------------------------------
# Email codes
# ---------------------------------------------------------------------------


def _budget(key, limit, store):
    """Count one challenge against a one-hour budget. Returns seconds to wait, or None."""
    now = time.time()
    window = 3600
    started = store.get(f"{key}:start")
    if started is None or now - started >= window:
        store.set(f"{key}:start", now, window)
        store.set(f"{key}:count", 0, window)
        started = now
    retry_after = max(1, int(window - (now - started)))
    count = store.get(f"{key}:count") or 0
    if count >= limit:
        return retry_after
    return None


def _hit(key, store):
    store.add(f"{key}:count", 0, 3600)
    try:
        store.incr(f"{key}:count")
    except ValueError:
        store.set(f"{key}:count", 1, 3600)


def challenge(email, purpose, client_ip):
    """Email a one-time code for ``purpose`` and return the verification id.

    Delivery is budgeted per mailbox and client IP, so one client cannot
    exhaust the owner's budget, and per mailbox across all clients, so the
    mailbox cannot be flooded.
    """
    from escalated.models import GuestVerification

    email = normalize_email(email)
    if purpose not in PURPOSES:
        raise InvalidEmail("Enter a valid email address.")
    try:
        validate_email(email)
    except Exception as exc:
        raise InvalidEmail("Enter a valid email address.") from exc

    per_client = _option("CHALLENGES_PER_CLIENT_PER_HOUR", 3, 1, 1000)
    per_mailbox = max(per_client, _option("CHALLENGES_PER_MAILBOX_PER_HOUR", 10, 1, 1000))
    store = caches[(get_setting("GUEST_RATE_LIMIT") or {}).get("CACHE") or "default"]
    mailbox_key = f"escalated.guest_email.{digest(email)}"
    client_key = f"{mailbox_key}.client.{digest(client_ip or '')}"
    for key, limit in ((client_key, per_client), (mailbox_key, per_mailbox)):
        retry_after = _budget(key, limit, store)
        if retry_after is not None:
            raise TooManyChallenges(retry_after)
    _hit(client_key, store)
    _hit(mailbox_key, store)

    verification_id = uuid.uuid4()
    code = f"{secrets.randbelow(100_000_000):08d}"
    verification = GuestVerification.objects.create(
        id=verification_id,
        email_digest=digest(email),
        purpose=purpose,
        code_hash=digest(f"{verification_id}:{code}"),
        expires_at=timezone.now() + timedelta(seconds=CODE_TTL_SECONDS),
    )
    try:
        send_mail(
            "Your support verification code",
            f"Your verification code is {code}.\n\n"
            "It expires in 10 minutes. If you did not ask for it, you can ignore this email.\n",
            None,
            [email],
        )
    except Exception:
        verification.delete()
        raise
    return str(verification_id)


def consume(verification_id, code, email, purpose, callback):
    """Consume a code and run ``callback`` in the same transaction.

    An incorrect attempt stays counted. If ``callback`` raises, the code is
    not consumed and can be retried. Raises :class:`InvalidCode`.
    """
    from escalated.models import GuestVerification

    try:
        verification_id = uuid.UUID(str(verification_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InvalidCode(INVALID_CODE) from exc
    code = str(code or "")
    using = router.db_for_write(GuestVerification)
    with transaction.atomic(using=using):
        verification = GuestVerification.objects.select_for_update().filter(pk=verification_id).first()
        if (
            verification is None
            or verification.used_at is not None
            or verification.expires_at <= timezone.now()
            or verification.attempts >= MAX_ATTEMPTS
        ):
            result = None
        else:
            verification.attempts += 1
            verification.save(update_fields=["attempts"])
            matches = (
                hmac.compare_digest(verification.code_hash, digest(f"{verification_id}:{code}"))
                and hmac.compare_digest(verification.email_digest, email_digest(email))
                and verification.purpose == purpose
            )
            if not matches:
                result = None
            else:
                verification.used_at = timezone.now()
                verification.save(update_fields=["used_at"])
                result = {"value": callback()}
    # Outside the transaction: an incorrect attempt is never rolled back.
    if result is None:
        raise InvalidCode(INVALID_CODE)
    return result["value"]


# ---------------------------------------------------------------------------
# Grants
# ---------------------------------------------------------------------------


def mark_verified(ticket, email):
    ticket.guest_verified_email = email_digest(email)
    ticket.guest_email_verified_at = timezone.now()


def verified(ticket):
    return bool(
        ticket.guest_email_verified_at
        and ticket.guest_email
        and ticket.guest_verified_email
        and hmac.compare_digest(ticket.guest_verified_email, email_digest(ticket.guest_email))
    )


def active(ticket):
    return bool(
        verified(ticket)
        and ticket.guest_access_hash
        and len(ticket.guest_access_hash) == 64
        and ticket.guest_access_expires_at
        and ticket.guest_access_expires_at > timezone.now()
    )


def issue(ticket, purpose="ticket"):
    """A new grant for a ticket whose guest email has been proven. Saves the ticket.

    Revokes earlier grants and the permanent legacy ``guest_token``.
    """
    if purpose not in GRANT_PURPOSES or not verified(ticket):
        raise ValueError("Guest access requires a verified ticket email and a supported purpose.")
    nonce = secrets.token_urlsafe(48)
    expires = (timezone.now() + grant_ttl()).replace(microsecond=0)
    ticket.guest_access_hash = hashlib.sha256(nonce.encode()).hexdigest()
    ticket.guest_access_expires_at = expires
    ticket.guest_token = None
    ticket.save(
        update_fields=[
            "guest_access_hash",
            "guest_access_expires_at",
            "guest_token",
            "guest_verified_email",
            "guest_email_verified_at",
        ]
    )
    claims = {
        "v": 1,
        "t": str(ticket.pk),
        "p": purpose,
        "n": nonce,
        "x": int(expires.timestamp()),
        "e": ticket.guest_verified_email,
    }
    return signing.dumps(claims, salt=GRANT_SALT, compress=True)


def resolve(token, purpose="ticket"):
    """The ticket an active grant names, or None. Never accepts a legacy token."""
    from escalated.models import Ticket

    if not isinstance(token, str) or not token or len(token) > 4096:
        return None
    try:
        claims = signing.loads(token, salt=GRANT_SALT)
    except signing.BadSignature:
        return None
    if not (
        isinstance(claims, dict)
        and claims.get("v") == 1
        and claims.get("p") == purpose
        and isinstance(claims.get("t"), str)
        and isinstance(claims.get("n"), str)
        and isinstance(claims.get("x"), int)
        and claims["x"] > int(time.time())
    ):
        return None
    ticket = Ticket.unrestricted.filter(pk=claims["t"]).first()
    if ticket is None or not active(ticket):
        return None
    if int(ticket.guest_access_expires_at.timestamp()) != claims["x"]:
        return None
    if not hmac.compare_digest(ticket.guest_access_hash, hashlib.sha256(claims["n"].encode()).hexdigest()):
        return None
    if not hmac.compare_digest(str(claims.get("e") or ""), ticket.guest_verified_email or ""):
        return None
    return ticket


def revoke(ticket):
    ticket.guest_access_hash = None
    ticket.guest_access_expires_at = None
    ticket.guest_token = None
    ticket.save(update_fields=["guest_access_hash", "guest_access_expires_at", "guest_token"])


def legacy_tokens_enabled():
    return bool((get_setting("GUEST_ACCESS") or {}).get("LEGACY_TOKENS", False))


def ticket_for_token(token):
    """The ticket a guest route's token opens: an active grant, or (opt-in) a legacy token."""
    from escalated.models import Ticket

    ticket = resolve(token)
    if ticket is None and legacy_tokens_enabled() and isinstance(token, str) and len(token) == 64:
        ticket = Ticket.unrestricted.filter(guest_token=token).first()
    return ticket
