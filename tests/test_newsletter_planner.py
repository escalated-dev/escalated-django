import pytest

from escalated.models import Contact, Newsletter, NewsletterDelivery, NewsletterList
from escalated.services.newsletter.bounce_suppression_store import BounceSuppressionStore
from escalated.services.newsletter.planner import NewsletterPlanner


@pytest.mark.django_db
class TestNewsletterPlanner:
    def test_creates_deliveries_for_sendable_contacts(self):
        lst = NewsletterList.objects.create(name="L", kind="static")
        c1 = Contact.objects.create(email="a@example.com")
        c2 = Contact.objects.create(email="b@example.com")
        from escalated.models import NewsletterListMember

        NewsletterListMember.objects.create(list_id=lst.id, contact_id=c1.id)
        NewsletterListMember.objects.create(list_id=lst.id, contact_id=c2.id)
        nl = Newsletter.objects.create(
            subject="S",
            from_email="s@example.com",
            target_list_id=lst.id,
            status="draft",
        )
        NewsletterPlanner().plan(nl)
        nl.refresh_from_db()
        assert nl.status == "sending"
        assert nl.summary_total == 2
        assert NewsletterDelivery.objects.filter(newsletter_id=nl.id).count() == 2

    def test_skips_opted_out(self):
        lst = NewsletterList.objects.create(name="L", kind="static")
        from django.utils import timezone
        from escalated.models import NewsletterListMember

        ok = Contact.objects.create(email="ok@example.com")
        out = Contact.objects.create(email="out@example.com", marketing_opt_out_at=timezone.now())
        NewsletterListMember.objects.create(list_id=lst.id, contact_id=ok.id)
        NewsletterListMember.objects.create(list_id=lst.id, contact_id=out.id)
        nl = Newsletter.objects.create(
            subject="S",
            from_email="s@example.com",
            target_list_id=lst.id,
            status="draft",
        )
        NewsletterPlanner().plan(nl)
        assert NewsletterDelivery.objects.filter(newsletter_id=nl.id).count() == 1

    def test_skips_suppressed_emails(self):
        lst = NewsletterList.objects.create(name="L", kind="static")
        from escalated.models import NewsletterListMember

        ok = Contact.objects.create(email="ok@example.com")
        bad = Contact.objects.create(email="bounced@example.com")
        NewsletterListMember.objects.create(list_id=lst.id, contact_id=ok.id)
        NewsletterListMember.objects.create(list_id=lst.id, contact_id=bad.id)
        BounceSuppressionStore().mark_bounced("bounced@example.com")
        nl = Newsletter.objects.create(
            subject="S",
            from_email="s@example.com",
            target_list_id=lst.id,
            status="draft",
        )
        NewsletterPlanner().plan(nl)
        assert NewsletterDelivery.objects.filter(newsletter_id=nl.id).count() == 1

    def test_snapshots_email_at_send(self):
        lst = NewsletterList.objects.create(name="L", kind="static")
        from escalated.models import NewsletterListMember

        c = Contact.objects.create(email="snap@example.com")
        NewsletterListMember.objects.create(list_id=lst.id, contact_id=c.id)
        nl = Newsletter.objects.create(
            subject="S",
            from_email="s@example.com",
            target_list_id=lst.id,
            status="draft",
        )
        NewsletterPlanner().plan(nl)
        c.email = "changed@example.com"
        c.save()
        d = NewsletterDelivery.objects.get(newsletter_id=nl.id)
        assert d.email_at_send == "snap@example.com"

    def test_unique_tracking_tokens(self):
        lst = NewsletterList.objects.create(name="L", kind="static")
        from escalated.models import NewsletterListMember

        for i in range(3):
            c = Contact.objects.create(email=f"u{i}@example.com")
            NewsletterListMember.objects.create(list_id=lst.id, contact_id=c.id)
        nl = Newsletter.objects.create(
            subject="S",
            from_email="s@example.com",
            target_list_id=lst.id,
            status="draft",
        )
        NewsletterPlanner().plan(nl)
        tokens = list(NewsletterDelivery.objects.filter(newsletter_id=nl.id).values_list("tracking_token", flat=True))
        assert len(tokens) == len(set(tokens))
