"""Dispatcher: claim pending rows, send via Django mail backend,
finalize completed newsletters, auto-pause on high bounce rate."""

from __future__ import annotations

import logging
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from escalated.models import Newsletter, NewsletterDelivery
from escalated.newsletter_conf import newsletter_config, newsletters_enabled

from .renderer import NewsletterRenderer

log = logging.getLogger(__name__)

BACKOFF_MINUTES = (1, 5, 30)


def _conf(key: str, default=None):
    return (getattr(settings, "ESCALATED", {}) or {}).get(key, default)


class NewsletterDispatcher:
    def __init__(self, renderer: NewsletterRenderer | None = None) -> None:
        self.renderer = renderer or NewsletterRenderer()

    def dispatch_batch(self) -> None:
        if not newsletters_enabled():
            return

        self._reclaim_stuck_rows()

        batch_size = int(newsletter_config("batch_size", _conf("newsletter_batch_size", 50)))
        rate_limit = int(newsletter_config("rate_limit_per_minute", _conf("newsletter_rate_limit_per_minute", 60)))
        allowance = max(0, rate_limit - self._sent_this_minute())

        if allowance <= 0:
            self._check_auto_pause()
            self._finalize_completed_newsletters()
            return

        now = timezone.now()
        claim_count = min(batch_size, allowance)

        with transaction.atomic():
            ids = list(
                NewsletterDelivery.objects.select_for_update(skip_locked=True)
                .filter(status="pending")
                .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
                .order_by("id")
                .values_list("id", flat=True)[:claim_count]
            )
            if ids:
                NewsletterDelivery.objects.filter(id__in=ids).update(status="queued", claimed_at=now)

        if ids:
            self._increment_sent_this_minute(len(ids))

        for delivery_id in ids:
            delivery = NewsletterDelivery.objects.filter(id=delivery_id).first()
            if delivery:
                self._dispatch_one(delivery)

        self._check_auto_pause()
        self._finalize_completed_newsletters()

    def _dispatch_one(self, delivery: NewsletterDelivery) -> None:
        from escalated.models import Contact, NewsletterTemplate
        from escalated.models import Newsletter as NL

        delivery_full = NewsletterDelivery.objects.get(id=delivery.id)
        nl = NL.objects.get(id=delivery_full.newsletter_id)
        delivery_full.newsletter = nl
        nl.template = NewsletterTemplate.objects.filter(id=nl.template_id).first() if nl.template_id else None
        delivery_full.contact = Contact.objects.get(id=delivery_full.contact_id)

        try:
            html_body = self.renderer.render(delivery_full)
            unsub = self.renderer.unsubscribe_url(delivery_full)
            base = _conf("app_url", "http://localhost") or "http://localhost"
            host = urlparse(base).hostname or "localhost"

            from_addr = f'"{nl.from_name}" <{nl.from_email}>' if nl.from_name else nl.from_email
            msg = EmailMultiAlternatives(
                subject=nl.subject,
                body=html_body,
                from_email=from_addr,
                to=[delivery_full.email_at_send],
                reply_to=[nl.reply_to] if nl.reply_to else None,
                headers={
                    "List-Unsubscribe": f"<{unsub}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                    "X-Escalated-Newsletter-Id": str(nl.id),
                    "Message-ID": f"<n-{nl.id}-{delivery_full.tracking_token}@{host}>",
                },
            )
            msg.attach_alternative(html_body, "text/html")
            msg.content_subtype = "html"
            msg.send()

            delivery_full.status = "sent"
            delivery_full.sent_at = timezone.now()
            delivery_full.claimed_at = None
            delivery_full.next_attempt_at = None
            delivery_full.save(update_fields=["status", "sent_at", "claimed_at", "next_attempt_at"])
            NL.objects.filter(id=nl.id).update(summary_sent=F("summary_sent") + 1)
        except Exception as e:
            log.warning("Newsletter delivery %s failed: %s", delivery_full.id, e)
            attempts = delivery_full.attempt_count + 1
            if attempts >= 3:
                delivery_full.status = "failed"
                delivery_full.failure_reason = str(e)
                delivery_full.next_attempt_at = None
            else:
                delivery_full.status = "pending"
                minutes = BACKOFF_MINUTES[attempts - 1]
                delivery_full.next_attempt_at = timezone.now() + timedelta(minutes=minutes)
            delivery_full.attempt_count = attempts
            delivery_full.claimed_at = None
            delivery_full.save(
                update_fields=["status", "attempt_count", "claimed_at", "failure_reason", "next_attempt_at"]
            )

    def _minute_cache_key(self) -> str:
        now = timezone.now()
        return f"escalated:newsletters:sent:{now.strftime('%Y%m%d%H%M')}"

    def _sent_this_minute(self) -> int:
        return int(cache.get(self._minute_cache_key(), 0) or 0)

    def _increment_sent_this_minute(self, count: int) -> None:
        key = self._minute_cache_key()
        current = int(cache.get(key, 0) or 0)
        cache.set(key, current + count, timeout=120)

    def _reclaim_stuck_rows(self) -> None:
        minutes = int(_conf("newsletter_claim_timeout_minutes", 10))
        cutoff = timezone.now() - timedelta(minutes=minutes)
        NewsletterDelivery.objects.filter(status="queued", claimed_at__lt=cutoff).update(
            status="pending", claimed_at=None
        )

    def _finalize_completed_newsletters(self) -> None:
        for n in Newsletter.objects.filter(status="sending"):
            has_remaining = NewsletterDelivery.objects.filter(
                newsletter_id=n.id, status__in=["pending", "queued"]
            ).exists()
            if not has_remaining:
                n.status = "sent"
                if not n.sent_at:
                    n.sent_at = timezone.now()
                n.save(update_fields=["status", "sent_at"])

    def _check_auto_pause(self) -> None:
        threshold = int(_conf("newsletter_auto_pause_threshold", 100))
        rate = float(_conf("newsletter_auto_pause_bounce_rate", 0.05))
        terminal_statuses = ["sent", "bounced", "complained", "failed"]
        for n in Newsletter.objects.filter(status="sending"):
            sample = list(
                NewsletterDelivery.objects.filter(newsletter_id=n.id, status__in=terminal_statuses)
                .order_by("id")
                .values_list("status", flat=True)[:threshold]
            )
            if len(sample) < threshold:
                continue
            bounced = sum(1 for s in sample if s == "bounced")
            if bounced / threshold >= rate:
                n.status = "paused"
                n.save(update_fields=["status"])
                log.warning("Newsletter %s auto-paused: %s/%s bounced", n.id, bounced, threshold)
