"""Plans a Newsletter for sending: snapshots recipients, applies filters,
inserts delivery rows with tracking tokens."""

from __future__ import annotations

import secrets

from django.db import transaction

from escalated.models import Contact, Newsletter, NewsletterDelivery, NewsletterList

from .bounce_suppression_store import BounceSuppressionStore
from .contact_segment_resolver import ContactSegmentResolver


class NewsletterPlanner:
    def __init__(
        self,
        segments: ContactSegmentResolver | None = None,
        bounces: BounceSuppressionStore | None = None,
    ) -> None:
        self.segments = segments or ContactSegmentResolver()
        self.bounces = bounces or BounceSuppressionStore()

    def plan(self, newsletter: Newsletter) -> None:
        # Atomic: status flip + delivery snapshot + summary must all commit
        # together. Without this, a failure mid-bulk_create left committed
        # partial deliveries with the newsletter stuck in "sending".
        with transaction.atomic():
            newsletter.status = "sending"
            newsletter.save(update_fields=["status"])

            target_list = NewsletterList.objects.filter(id=newsletter.target_list_id).first()
            if not target_list:
                newsletter.summary_total = 0
                newsletter.save(update_fields=["summary_total"])
                return

            contact_ids = self.segments.resolve_sendable(target_list)
            if not contact_ids:
                newsletter.summary_total = 0
                newsletter.save(update_fields=["summary_total"])
                return

            contacts = list(Contact.objects.filter(id__in=contact_ids).values("id", "email"))
            sendable = {e.lower() for e in self.bounces.filter_sendable([c["email"] for c in contacts])}

            rows = []
            for c in contacts:
                if c["email"].lower() not in sendable:
                    continue
                rows.append(
                    NewsletterDelivery(
                        newsletter_id=newsletter.id,
                        contact_id=c["id"],
                        email_at_send=c["email"],
                        status="pending",
                        tracking_token=secrets.token_hex(20),
                        attempt_count=0,
                        is_test=False,
                    )
                )

            for i in range(0, len(rows), 500):
                NewsletterDelivery.objects.bulk_create(rows[i : i + 500])

            newsletter.summary_total = len(rows)
            newsletter.save(update_fields=["summary_total"])
