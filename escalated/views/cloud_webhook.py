"""
Applies cloud-side changes to the local ticket in Synced mode.

cloud.escalated.dev posts ``ticket.updated`` / ``ticket.status_changed`` with
the projected ticket. The projection carries this site's own reference as
``external_id``; tickets without one never came from here and are ignored.
Changes go through LocalDriver so signals, notifications and workflows fire
exactly as for a local edit, while SyncedDriver is bypassed so nothing is
echoed back to the cloud.
"""

import hashlib
import hmac
import json
import logging

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from escalated.conf import get_setting
from escalated.drivers.local import LocalDriver
from escalated.models import Ticket
from escalated.support import cloud_vocabulary

logger = logging.getLogger("escalated")

APPLIED_EVENTS = ("ticket.updated", "ticket.status_changed")
REPLAY_TTL_SECONDS = 24 * 60 * 60


def _ignored(reason):
    return JsonResponse({"received": True, "applied": False, "reason": reason}, status=202)


@csrf_exempt
@require_POST
def cloud_webhook(request):
    secret = get_setting("HOSTED_SIGNING_SECRET") or ""

    if not secret:
        logger.warning("Escalated cloud webhook received but HOSTED_SIGNING_SECRET is not configured.")
        return JsonResponse({"error": "Cloud webhook signing secret is not configured."}, status=503)

    raw = request.body or b""
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    signature = request.META.get("HTTP_X_ESCALATED_SIGNATURE", "")

    if not signature or not signature.isascii() or not hmac.compare_digest(expected, signature):
        return JsonResponse({"error": "Invalid signature."}, status=401)

    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        body = {}
    if not isinstance(body, dict):
        body = {}

    event = str(body.get("event") or "")
    event_id = body.get("event_id")
    cloud_ticket = body.get("ticket") if isinstance(body.get("ticket"), dict) else {}

    if (
        isinstance(event_id, str)
        and event_id
        and not cache.add(f"escalated:cloud-event:{event_id}", 1, REPLAY_TTL_SECONDS)
    ):
        return JsonResponse({"received": True, "applied": False, "replay": True})

    if event not in APPLIED_EVENTS:
        return _ignored(f"Event {event} carries no changes for the site.")

    reference = cloud_ticket.get("external_id")
    if not isinstance(reference, str) or not reference:
        return _ignored("Ticket did not originate from this site.")

    ticket = Ticket.objects.filter(reference=reference).first()
    if ticket is None:
        return _ignored(f"No local ticket with reference {reference}.")

    try:
        applied = _apply(ticket, cloud_ticket)
    except Exception as exc:  # noqa: BLE001 - a permanent failure must not make the cloud retry forever
        logger.warning(f"Escalated cloud webhook could not apply {event} to {reference}: {exc}")
        return JsonResponse({"received": True, "applied": False, "reason": str(exc)})

    return JsonResponse({"received": True, "applied": bool(applied), "changes": applied})


# Keep signed webhooks public when the host enables Django 5.1+ LoginRequiredMiddleware.
# Setting the attribute directly also supports Django versions without login_not_required.
cloud_webhook.login_required = False


def _apply(ticket, cloud_ticket):
    driver = LocalDriver()
    applied = []

    content = {}
    for field in ("subject", "description"):
        value = cloud_ticket.get(field)
        if value is not None and str(value) != str(getattr(ticket, field) or ""):
            content[field] = str(value)

    if content:
        ticket = driver.update_ticket(ticket, None, content)
        applied.extend(content.keys())

    if "priority" in cloud_ticket:
        priority = cloud_vocabulary.priority_from_cloud(cloud_ticket["priority"])
        if priority in cloud_vocabulary.LOCAL_PRIORITIES and priority != ticket.priority:
            ticket = driver.change_priority(ticket, None, priority)
            applied.append("priority")

    if "status" in cloud_ticket:
        status = cloud_vocabulary.status_from_cloud(cloud_ticket["status"])
        if status in cloud_vocabulary.LOCAL_STATUSES and status != ticket.status:
            driver.transition_status(ticket, None, status)
            applied.append("status")

    return applied
