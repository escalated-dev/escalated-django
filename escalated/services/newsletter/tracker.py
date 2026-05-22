"""Records tracking events on delivery rows idempotently."""

from __future__ import annotations

from django.db.models import F
from django.utils import timezone

from escalated.models import Newsletter, NewsletterDelivery

from .bounce_suppression_store import BounceSuppressionStore


TERMINAL = ("bounced", "complained", "failed")


class NewsletterTracker:
    def __init__(self, bounces: BounceSuppressionStore | None = None) -> None:
        self.bounces = bounces or BounceSuppressionStore()

    def record_open(self, token: str) -> None:
        d = NewsletterDelivery.objects.filter(tracking_token=token).first()
        if not d or d.status in TERMINAL or d.opened_at:
            return
        d.opened_at = timezone.now()
        d.save(update_fields=["opened_at"])
        Newsletter.objects.filter(id=d.newsletter_id).update(summary_opened=F("summary_opened") + 1)

    def record_click(self, token: str, _url: str) -> None:
        d = NewsletterDelivery.objects.filter(tracking_token=token).first()
        if not d or d.status in TERMINAL:
            return
        first_click = d.clicks_count == 0
        update_fields = ["clicks_count", "last_clicked_at"]
        d.clicks_count = d.clicks_count + 1
        d.last_clicked_at = timezone.now()
        if not d.opened_at:
            d.opened_at = timezone.now()
            update_fields.append("opened_at")
            Newsletter.objects.filter(id=d.newsletter_id).update(summary_opened=F("summary_opened") + 1)
        d.save(update_fields=update_fields)
        if first_click:
            Newsletter.objects.filter(id=d.newsletter_id).update(summary_clicked=F("summary_clicked") + 1)

    def record_bounce(self, token: str, kind: str, reason: str | None = None) -> None:
        if kind != "hard":
            return
        d = NewsletterDelivery.objects.filter(tracking_token=token).first()
        if not d or d.status == "bounced":
            return
        d.status = "bounced"
        d.bounce_reason = reason
        d.save(update_fields=["status", "bounce_reason"])
        Newsletter.objects.filter(id=d.newsletter_id).update(summary_bounced=F("summary_bounced") + 1)
        self.bounces.mark_bounced(d.email_at_send)

    def record_complaint(self, token: str) -> None:
        d = NewsletterDelivery.objects.filter(tracking_token=token).first()
        if not d or d.status == "complained":
            return
        d.status = "complained"
        d.save(update_fields=["status"])
        Newsletter.objects.filter(id=d.newsletter_id).update(summary_complained=F("summary_complained") + 1)
        self.bounces.mark_complained(d.email_at_send)
