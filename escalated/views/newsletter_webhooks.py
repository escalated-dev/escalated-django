"""ESP webhook handlers for newsletter tracking events."""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from escalated.services.newsletter.tracker import NewsletterTracker
from escalated.views.newsletter_utils import newsletters_enabled_view, token_from_message_id

HARD_BOUNCE_POSTMARK = frozenset({"HardBounce", "BadEmailAddress", "BlockedRecipient"})


@csrf_exempt
@newsletters_enabled_view
@require_POST
def postmark(request):
    try:
        body = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        body = {}
    token = token_from_message_id(str(body.get("MessageID", "")))
    tracker = NewsletterTracker()
    record_type = str(body.get("RecordType", ""))
    if record_type == "Open":
        tracker.record_open(token)
    elif record_type == "Click":
        tracker.record_click(token, str(body.get("OriginalLink", "")))
    elif record_type == "Bounce":
        kind = "hard" if str(body.get("Type", "")) in HARD_BOUNCE_POSTMARK else "soft"
        tracker.record_bounce(token, kind, str(body.get("Description", "")))
    elif record_type == "SpamComplaint":
        tracker.record_complaint(token)
    return JsonResponse({"ok": True})


@csrf_exempt
@newsletters_enabled_view
@require_POST
def mailgun(request):
    try:
        body = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        body = {}
    event_data = body.get("event-data") or {}
    message_id = str((event_data.get("message") or {}).get("headers", {}).get("message-id", ""))
    token = token_from_message_id(message_id)
    tracker = NewsletterTracker()
    event = str(event_data.get("event", ""))
    if event == "opened":
        tracker.record_open(token)
    elif event == "clicked":
        tracker.record_click(token, str(event_data.get("url", "")))
    elif event == "failed":
        kind = "hard" if event_data.get("severity") == "permanent" else "soft"
        reason = str((event_data.get("delivery-status") or {}).get("description", ""))
        tracker.record_bounce(token, kind, reason)
    elif event == "complained":
        tracker.record_complaint(token)
    return JsonResponse({"ok": True})


@csrf_exempt
@newsletters_enabled_view
@require_POST
def ses(request):
    try:
        body = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        body = {}
    message = body.get("Message")
    if isinstance(message, str):
        try:
            message = json.loads(message)
        except json.JSONDecodeError:
            message = {}
    if not isinstance(message, dict):
        message = body
    token = token_from_message_id(str((message.get("mail") or {}).get("messageId", "")))
    tracker = NewsletterTracker()
    event_type = str(message.get("eventType", ""))
    if event_type == "Open":
        tracker.record_open(token)
    elif event_type == "Click":
        tracker.record_click(token, str((message.get("click") or {}).get("link", "")))
    elif event_type == "Bounce":
        bounce = message.get("bounce") or {}
        kind = "hard" if bounce.get("bounceType") == "Permanent" else "soft"
        tracker.record_bounce(token, kind, bounce.get("bounceSubType"))
    elif event_type == "Complaint":
        tracker.record_complaint(token)
    return JsonResponse({"ok": True})


@csrf_exempt
@newsletters_enabled_view
@require_POST
def sendgrid(request):
    try:
        events = json.loads(request.body.decode() or "[]")
    except json.JSONDecodeError:
        events = []
    if not isinstance(events, list):
        events = []
    tracker = NewsletterTracker()
    for event in events:
        if not isinstance(event, dict):
            continue
        message_id = str(event.get("smtp-id") or event.get("sg_message_id") or "")
        token = token_from_message_id(message_id)
        ev = event.get("event")
        if ev == "open":
            tracker.record_open(token)
        elif ev == "click":
            tracker.record_click(token, str(event.get("url", "")))
        elif ev == "bounce":
            kind = "hard" if event.get("type") == "blocked" else "soft"
            tracker.record_bounce(token, kind, event.get("reason"))
        elif ev == "dropped":
            tracker.record_bounce(token, "hard", event.get("reason"))
        elif ev == "spamreport":
            tracker.record_complaint(token)
    return JsonResponse({"ok": True})
