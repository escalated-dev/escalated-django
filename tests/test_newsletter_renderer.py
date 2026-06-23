import pytest

from escalated.models import Contact, Newsletter, NewsletterDelivery, NewsletterList
from escalated.services.newsletter.renderer import NewsletterRenderer


@pytest.fixture(autouse=True)
def _renderer_settings(settings):
    def _markdown(md: str) -> str:
        text = md or ""
        if "<" in text:
            return text
        return f"<p>{text}</p>"

    settings.ESCALATED = {
        **settings.ESCALATED,
        "enable_newsletters": True,
        "app_url": "http://localhost",
        "newsletter_tracking_enabled": True,
        "newsletter_markdown_renderer": _markdown,
    }


@pytest.mark.django_db
class TestNewsletterRenderer:
    def _delivery(self):
        lst = NewsletterList.objects.create(name="L", kind="static")
        nl = Newsletter.objects.create(
            subject="Hello",
            from_email="s@example.com",
            target_list_id=lst.id,
            body_markdown="Hello {{ contact.first_name }} — {{ contact.email }}",
            theme="default",
            status="draft",
        )
        contact = Contact.objects.create(email="user@example.com", name="Ada Lovelace")
        delivery = NewsletterDelivery(
            newsletter_id=nl.id,
            contact_id=contact.id,
            email_at_send=contact.email,
            tracking_token="rendertok" + "x" * 29,
        )
        delivery.newsletter = nl
        delivery.contact = contact
        return delivery

    def test_renders_markdown_and_merge_fields(self):
        html = NewsletterRenderer().render(self._delivery())
        assert "Hello" in html
        assert "Ada" in html
        assert "user@example.com" in html

    def test_unknown_merge_field_empty(self):
        d = self._delivery()
        d.newsletter.body_markdown = "x {{ contact.does_not_exist }} y"
        html = NewsletterRenderer().render(d)
        assert "{{" not in html

    def test_rewrites_links_and_pixel(self):
        d = self._delivery()
        d.newsletter.body_markdown = '<a href="https://example.com/path">link</a>'
        html = NewsletterRenderer().render(d)
        assert "https://example.com/path" not in html
        assert "/escalated/n/c/" in html
        assert ".gif" in html

    def test_tracking_disabled(self, settings):
        settings.ESCALATED["newsletter_tracking_enabled"] = False
        d = self._delivery()
        d.newsletter.body_markdown = '<a href="https://example.com">link</a>'
        html = NewsletterRenderer().render(d)
        assert "https://example.com" in html
        assert "/escalated/n/o/" not in html

    def test_javascript_links_stripped(self):
        d = self._delivery()
        d.newsletter.body_markdown = '<a href="javascript:alert(1)">bad</a>'
        html = NewsletterRenderer().render(d)
        assert "javascript:" not in html

    def test_unsubscribe_not_rewritten(self):
        d = self._delivery()
        renderer = NewsletterRenderer()
        unsub = renderer.unsubscribe_url(d)
        d.newsletter.body_markdown = f'<a href="{unsub}">unsub</a>'
        html = renderer.render(d)
        assert unsub in html
