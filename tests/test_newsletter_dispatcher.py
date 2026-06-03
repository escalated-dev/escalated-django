from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.utils import timezone

from escalated.models import Contact, Newsletter, NewsletterDelivery, NewsletterList
from escalated.services.newsletter.dispatcher import NewsletterDispatcher


@pytest.fixture
def newsletter(db):
    lst = NewsletterList.objects.create(name="Main", kind="static", created_by="1")
    return Newsletter.objects.create(
        subject="Hi",
        from_email="sender@example.com",
        target_list_id=lst.id,
        status="sending",
    )


@pytest.fixture(autouse=True)
def _newsletter_escalated(settings):
    settings.ESCALATED = {
        **settings.ESCALATED,
        "enable_newsletters": True,
        "newsletter_batch_size": 50,
        "newsletter_rate_limit_per_minute": 60,
        "app_url": "http://localhost",
    }
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.mark.django_db
class TestNewsletterDispatcher:
    def test_claims_pending_and_marks_sent(self, newsletter):
        contact = Contact.objects.create(email="a@example.com")
        delivery = NewsletterDelivery.objects.create(
            newsletter_id=newsletter.id,
            contact_id=contact.id,
            email_at_send=contact.email,
            status="pending",
            tracking_token="tok1" + "a" * 35,
        )
        NewsletterDispatcher().dispatch_batch()
        delivery.refresh_from_db()
        newsletter.refresh_from_db()
        assert delivery.status == "sent"
        assert delivery.sent_at is not None
        assert newsletter.summary_sent == 1
        assert len(mail.outbox) == 1

    def test_respects_batch_size(self, newsletter, settings):
        contacts = [Contact.objects.create(email=f"u{i}@example.com") for i in range(5)]
        for i, c in enumerate(contacts):
            NewsletterDelivery.objects.create(
                newsletter_id=newsletter.id,
                contact_id=c.id,
                email_at_send=c.email,
                status="pending",
                tracking_token=f"batch{i}" + "x" * 34,
            )
        settings.ESCALATED["newsletter_batch_size"] = 2
        NewsletterDispatcher().dispatch_batch()
        assert NewsletterDelivery.objects.filter(status="sent").count() == 2
        assert NewsletterDelivery.objects.filter(status="pending").count() == 3

    def test_finalizes_newsletter_when_all_terminal(self, newsletter):
        contact = Contact.objects.create(email="done@example.com")
        NewsletterDelivery.objects.create(
            newsletter_id=newsletter.id,
            contact_id=contact.id,
            email_at_send=contact.email,
            status="pending",
            tracking_token="fin1" + "a" * 35,
        )
        NewsletterDispatcher().dispatch_batch()
        newsletter.refresh_from_db()
        assert newsletter.status == "sent"
        assert newsletter.sent_at is not None

    def test_disabled_does_nothing(self, newsletter, settings):
        settings.ESCALATED["enable_newsletters"] = False
        contact = Contact.objects.create(email="idle@example.com")
        delivery = NewsletterDelivery.objects.create(
            newsletter_id=newsletter.id,
            contact_id=contact.id,
            email_at_send=contact.email,
            status="pending",
            tracking_token="idle" + "a" * 35,
        )
        NewsletterDispatcher().dispatch_batch()
        delivery.refresh_from_db()
        newsletter.refresh_from_db()
        assert delivery.status == "pending"
        assert newsletter.summary_sent == 0
        assert len(mail.outbox) == 0

    def test_rate_limit_across_ticks(self, newsletter, settings):
        from django.core.cache import cache

        cache.clear()
        contacts = [Contact.objects.create(email=f"r{i}@example.com") for i in range(5)]
        for i, c in enumerate(contacts):
            NewsletterDelivery.objects.create(
                newsletter_id=newsletter.id,
                contact_id=c.id,
                email_at_send=c.email,
                status="pending",
                tracking_token=f"rate{i}" + "y" * 34,
            )
        settings.ESCALATED["newsletter_rate_limit_per_minute"] = 2
        dispatcher = NewsletterDispatcher()
        dispatcher.dispatch_batch()
        dispatcher.dispatch_batch()
        assert len(mail.outbox) == 2

    def test_skips_future_next_attempt_at(self, newsletter):
        contact = Contact.objects.create(email="later@example.com")
        NewsletterDelivery.objects.create(
            newsletter_id=newsletter.id,
            contact_id=contact.id,
            email_at_send=contact.email,
            status="pending",
            tracking_token="later" + "a" * 34,
            attempt_count=1,
            next_attempt_at=timezone.now() + timedelta(minutes=30),
        )
        NewsletterDispatcher().dispatch_batch()
        assert len(mail.outbox) == 0

    def test_auto_pause_first_n_sample(self, newsletter, settings):
        settings.ESCALATED["newsletter_auto_pause_threshold"] = 4
        settings.ESCALATED["newsletter_auto_pause_bounce_rate"] = 0.05
        contact = Contact.objects.create(email="b@example.com")
        for i, status in enumerate(["bounced", "sent", "sent", "sent"]):
            NewsletterDelivery.objects.create(
                newsletter_id=newsletter.id,
                contact_id=contact.id,
                email_at_send=f"{i}@example.com",
                status=status,
                tracking_token=f"ap{i}" + "z" * 34,
            )
        NewsletterDispatcher().dispatch_batch()
        newsletter.refresh_from_db()
        assert newsletter.status == "paused"

    def test_failure_backoff(self, newsletter):
        contact = Contact.objects.create(email="fail@example.com")
        delivery = NewsletterDelivery.objects.create(
            newsletter_id=newsletter.id,
            contact_id=contact.id,
            email_at_send=contact.email,
            status="pending",
            tracking_token="fail" + "b" * 35,
        )
        with patch(
            "escalated.services.newsletter.dispatcher.EmailMultiAlternatives.send",
            side_effect=Exception("temporary"),
        ):
            NewsletterDispatcher().dispatch_batch()
        delivery.refresh_from_db()
        assert delivery.status == "pending"
        assert delivery.next_attempt_at is not None
