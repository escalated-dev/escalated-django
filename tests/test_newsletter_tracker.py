import pytest
from django.utils import timezone

from escalated.models import Contact, Newsletter, NewsletterDelivery, NewsletterList
from escalated.services.newsletter.bounce_suppression_store import BounceSuppressionStore
from escalated.services.newsletter.tracker import NewsletterTracker


@pytest.fixture
def delivery(db):
    lst = NewsletterList.objects.create(name="L", kind="static")
    nl = Newsletter.objects.create(
        subject="S",
        from_email="s@example.com",
        target_list_id=lst.id,
        status="sending",
    )
    contact = Contact.objects.create(email="track@example.com")
    return NewsletterDelivery.objects.create(
        newsletter_id=nl.id,
        contact_id=contact.id,
        email_at_send=contact.email,
        status="sent",
        tracking_token="tracktoken" + "a" * 29,
    )


@pytest.mark.django_db
class TestNewsletterTracker:
    def test_record_open_first_event_wins(self, delivery):
        tracker = NewsletterTracker()
        tracker.record_open(delivery.tracking_token)
        tracker.record_open(delivery.tracking_token)
        delivery.refresh_from_db()
        nl = Newsletter.objects.get(id=delivery.newsletter_id)
        assert delivery.opened_at is not None
        assert nl.summary_opened == 1

    def test_record_click_and_complaint(self, delivery):
        tracker = NewsletterTracker()
        tracker.record_click(delivery.tracking_token, "https://example.com")
        tracker.record_click(delivery.tracking_token, "https://example.com")
        delivery.refresh_from_db()
        nl = Newsletter.objects.get(id=delivery.newsletter_id)
        assert delivery.clicks_count == 2
        assert nl.summary_clicked == 1

        tracker.record_bounce(delivery.tracking_token, "hard", "bad")
        delivery.refresh_from_db()
        assert delivery.status == "bounced"
        assert BounceSuppressionStore().is_bounced(delivery.email_at_send)

        d2 = NewsletterDelivery.objects.create(
            newsletter_id=delivery.newsletter_id,
            contact_id=delivery.contact_id,
            email_at_send="c2@example.com",
            status="sent",
            tracking_token="complaint" + "b" * 30,
        )
        tracker.record_complaint(d2.tracking_token)
        assert BounceSuppressionStore().is_bounced("c2@example.com")

    def test_unknown_token_is_silent(self):
        NewsletterTracker().record_open("does-not-exist")

    def test_open_after_bounce_ignored(self, delivery):
        delivery.status = "bounced"
        delivery.save()
        NewsletterTracker().record_open(delivery.tracking_token)
        delivery.refresh_from_db()
        assert delivery.opened_at is None
