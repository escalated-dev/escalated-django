from io import StringIO

import pytest
from django.core.management import call_command

from escalated.models import Contact, Newsletter, NewsletterDelivery, NewsletterList


@pytest.fixture(autouse=True)
def _newsletter_escalated(settings):
    settings.ESCALATED = {**settings.ESCALATED, "enable_newsletters": True}
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.mark.django_db
class TestDispatchNewslettersCommand:
    def test_disabled_exits_cleanly(self, settings):
        out = StringIO()
        settings.ESCALATED["enable_newsletters"] = False
        call_command("dispatch_newsletters", stdout=out)
        assert "disabled" in out.getvalue().lower()

    def test_disabled_mid_flight_leaves_pending(self, settings):
        lst = NewsletterList.objects.create(name="L", kind="static")
        nl = Newsletter.objects.create(
            subject="S",
            from_email="s@example.com",
            target_list_id=lst.id,
            status="sending",
        )
        for i in range(5):
            c = Contact.objects.create(email=f"p{i}@example.com")
            NewsletterDelivery.objects.create(
                newsletter_id=nl.id,
                contact_id=c.id,
                email_at_send=c.email,
                status="pending",
                tracking_token=f"cmd{i}" + "q" * 34,
            )
        out = StringIO()
        settings.ESCALATED["enable_newsletters"] = False
        call_command("dispatch_newsletters", stdout=out)
        assert NewsletterDelivery.objects.filter(status="pending").count() == 5
        nl.refresh_from_db()
        assert nl.summary_sent == 0
