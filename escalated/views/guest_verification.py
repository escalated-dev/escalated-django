"""
``POST verification`` and ``POST lookup`` for every guest surface (browser
``guest/``, ``widget/`` and the mobile API). See docs/guest-access.md.
"""

import json
import logging

from django.http import JsonResponse

from escalated import guest_access, guest_throttle
from escalated.models import EscalatedSetting, Ticket

logger = logging.getLogger("escalated")

MAX_LOOKUP_RESULTS = 20


def json_body(request):
    """The request's JSON object, or the form fields as a dict."""
    content_type = (request.content_type or "").split(";")[0].strip().lower()
    if content_type == "application/json":
        try:
            body = json.loads(request.body or b"{}")
        except (ValueError, UnicodeDecodeError):
            return {}
        return body if isinstance(body, dict) else {}
    return {key: request.POST.get(key) for key in request.POST}


def validation_error(errors):
    errors = {field: message if isinstance(message, list) else [message] for field, message in errors.items()}
    return JsonResponse({"message": next(iter(errors.values()))[0], "errors": errors}, status=422)


def private(response):
    """Guest answers carry access credentials: never cache them or leak them in a Referer."""
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


def proof_errors(body):
    """Validation errors for the proof fields of a guest create/start/lookup body."""
    errors = {}
    verification_id = body.get("verification_id")
    code = body.get("verification_code")
    if not isinstance(verification_id, str) or not verification_id.strip():
        errors["verification_id"] = "The verification id field is required."
    if not isinstance(code, str) or not code.strip():
        errors["verification_code"] = "The verification code field is required."
    elif len(code) > 16:
        errors["verification_code"] = "The verification code is invalid."
    return errors


def _str(body, key):
    value = body.get(key)
    return value.strip() if isinstance(value, str) else ""


def purpose_allowed(purpose):
    if purpose == "chat":
        return EscalatedSetting.get_bool("chat_enabled", default=False)
    return EscalatedSetting.guest_tickets_enabled()


def verification(request, surface_enabled=lambda: True):
    """Email a code: 202 ``{verification_id, expires_in, message}``."""
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed."}, status=405)
    if not surface_enabled():
        return JsonResponse({"message": "Not available."}, status=403)
    retry_after = guest_throttle.check(request, guest_throttle.TICKET)
    if retry_after is not None:
        return guest_throttle.too_many_requests(retry_after, json=True)

    body = json_body(request)
    email = _str(body, "email")
    purpose = _str(body, "purpose")
    errors = {}
    if not email or len(email) > 255:
        errors["email"] = "Enter a valid email address."
    if purpose not in guest_access.PURPOSES:
        errors["purpose"] = "The selected purpose is invalid."
    if errors:
        return validation_error(errors)
    if not purpose_allowed(purpose):
        return JsonResponse({"message": "Not available."}, status=403)

    try:
        verification_id = guest_access.challenge(email, purpose, guest_throttle.client_ip(request))
    except guest_access.InvalidEmail as exc:
        return validation_error({"email": str(exc)})
    except guest_access.TooManyChallenges as exc:
        response = JsonResponse({"message": str(exc)}, status=429)
        response["Retry-After"] = str(exc.retry_after)
        return response
    except Exception:
        logger.exception("Could not send a guest verification code")
        return JsonResponse({"message": "Could not send a verification code. Try again later."}, status=503)

    return private(
        JsonResponse(
            {
                "verification_id": verification_id,
                "expires_in": guest_access.CODE_TTL_SECONDS,
                "message": "Check your email for a verification code.",
            },
            status=202,
        )
    )


def lookup(request, surface_enabled=lambda: True):
    """Find the caller's tickets by reference and proven email: ``{data: [...]}`` with fresh grants."""
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed."}, status=405)
    if not surface_enabled() or not EscalatedSetting.guest_tickets_enabled():
        return JsonResponse({"message": "Not available."}, status=403)
    retry_after = guest_throttle.check(request, guest_throttle.REPLY)
    if retry_after is not None:
        return guest_throttle.too_many_requests(retry_after, json=True)

    body = json_body(request)
    email = _str(body, "email")
    reference = _str(body, "reference")
    errors = {}
    if not email or len(email) > 255:
        errors["email"] = "Enter a valid email address."
    if not reference or len(reference) > 255:
        errors["reference"] = "The reference field is required."
    errors.update(proof_errors(body))
    if errors:
        return validation_error(errors)

    def find():
        tickets = Ticket.unrestricted.filter(
            reference=reference, guest_email__iexact=guest_access.normalize_email(email)
        ).order_by("-created_at")[:MAX_LOOKUP_RESULTS]
        matches = []
        for ticket in tickets:
            guest_access.mark_verified(ticket, email)
            token = guest_access.issue(ticket)
            matches.append(
                {
                    "reference": ticket.reference,
                    "subject": ticket.subject,
                    "guest_access_token": token,
                    "expires_at": ticket.guest_access_expires_at.isoformat(),
                }
            )
        return matches

    try:
        matches = guest_access.consume(body["verification_id"], body["verification_code"], email, "lookup", find)
    except guest_access.InvalidCode as exc:
        return validation_error({"verification_code": str(exc)})
    return private(JsonResponse({"data": matches}))
