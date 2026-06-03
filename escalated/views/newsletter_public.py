"""Public newsletter tracking and unsubscribe views."""

from __future__ import annotations

import base64
import html
import re
from time import time
from urllib.parse import urlparse

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from escalated.models import Contact, NewsletterDelivery, NewsletterTemplate
from escalated.models import Newsletter as NL
from escalated.services.newsletter.renderer import NewsletterRenderer
from escalated.services.newsletter.tracker import NewsletterTracker
from escalated.views.newsletter_utils import newsletters_enabled_view

PIXEL_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63fcffff3f030005fe02fedccc59e70000000049454e44ae426082"
)

_unsubscribe_attempts: dict[str, tuple[int, float]] = {}


def _decode_tracked_url(encoded: str) -> str | None:
    if not encoded:
        return None
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode())
        url = raw.decode()
    except (ValueError, UnicodeDecodeError):
        return None
    scheme = urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        return None
    return url


def _too_many_unsubscribes(ip: str) -> bool:
    now = time()
    count, expires = _unsubscribe_attempts.get(ip, (0, 0.0))
    if expires <= now:
        _unsubscribe_attempts[ip] = (1, now + 60)
        return False
    count += 1
    _unsubscribe_attempts[ip] = (count, expires)
    return count > 60


def _unsubscribe_html(token: str, email: str | None, confirmed: bool) -> str:
    esc_token = html.escape(token)
    esc_email = html.escape(email or "")
    message = (
        "You have been unsubscribed."
        if confirmed
        else "Confirm that you want to unsubscribe from marketing emails."
    )
    return (
        f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>Unsubscribe</title></head><body><main><h1>Unsubscribe</h1>"
        f"<p>{message}</p><p>{esc_email}</p>"
        f"<form method=\"post\" action=\"/escalated/n/u/{esc_token}\">"
        f"<button type=\"submit\">Unsubscribe</button></form></main></body></html>"
    )


@newsletters_enabled_view
@require_GET
def open_pixel(request, token: str):
    clean = re.sub(r"\.(gif|png|jpg)$", "", token, flags=re.IGNORECASE)
    NewsletterTracker().record_open(clean)
    response = HttpResponse(PIXEL_BYTES, content_type="image/png", status=200)
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response


@newsletters_enabled_view
@require_GET
def click(request, token: str):
    destination = _decode_tracked_url(request.GET.get("u", ""))
    if not destination:
        return HttpResponse("Bad Request", status=400)
    NewsletterTracker().record_click(token, destination)
    response = HttpResponse(status=302)
    response["Location"] = destination
    return response


@csrf_exempt
@newsletters_enabled_view
def unsubscribe(request, token: str):
    if request.method == "POST":
        return _unsubscribe_store(request, token)
    if request.method != "GET":
        return HttpResponse(status=405)
    delivery = NewsletterDelivery.objects.filter(tracking_token=token).first()
    email = delivery.email_at_send if delivery else None
    return HttpResponse(_unsubscribe_html(token, email, False), content_type="text/html", status=200)


def _unsubscribe_store(request, token: str):
    ip = request.META.get("REMOTE_ADDR", "unknown")
    if _too_many_unsubscribes(ip):
        return HttpResponse("Too Many Requests", status=429)
    delivery = NewsletterDelivery.objects.filter(tracking_token=token).first()
    if delivery and delivery.contact_id:
        Contact.objects.filter(id=delivery.contact_id).update(marketing_opt_out_at=timezone.now())
    email = delivery.email_at_send if delivery else None
    return HttpResponse(_unsubscribe_html(token, email, True), content_type="text/html", status=200)


@newsletters_enabled_view
@require_GET
def view_in_browser(request, token: str):
    delivery = NewsletterDelivery.objects.filter(tracking_token=token).first()
    if not delivery:
        body = (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<title>Email unavailable</title></head><body>"
            "<p>This email is no longer available.</p></body></html>"
        )
        return HttpResponse(body, content_type="text/html", status=200)
    nl = NL.objects.filter(id=delivery.newsletter_id).first()
    if not nl:
        return HttpResponse(
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<title>Email unavailable</title></head><body>"
            "<p>This email is no longer available.</p></body></html>",
            content_type="text/html",
            status=200,
        )
    delivery.newsletter = nl
    nl.template = NewsletterTemplate.objects.filter(id=nl.template_id).first() if nl.template_id else None
    delivery.contact = Contact.objects.filter(id=delivery.contact_id).first()
    html_body = NewsletterRenderer().render(delivery)
    return HttpResponse(html_body, content_type="text/html", status=200)
