import json

import pytest
from django.core.cache import cache

from escalated.models import EscalatedSetting, Ticket
from escalated.views.widget import _rate_limited
from tests.factories import ArticleCategoryFactory, ArticleFactory, TicketFactory


class FakeRequest:
    """Minimal request-like object for testing rate limiting."""

    def __init__(self, ip="127.0.0.1"):
        self.META = {"REMOTE_ADDR": ip}


@pytest.mark.django_db
class TestRateLimiter:
    def setup_method(self):
        cache.clear()

    def test_allows_under_limit(self):
        req = FakeRequest()
        assert _rate_limited(req, scope="test", limit=5) is False

    def test_blocks_over_limit(self):
        req = FakeRequest()
        for _ in range(5):
            _rate_limited(req, scope="test_block", limit=5)
        assert _rate_limited(req, scope="test_block", limit=5) is True

    def test_different_ips_independent(self):
        req1 = FakeRequest(ip="1.1.1.1")
        req2 = FakeRequest(ip="2.2.2.2")
        for _ in range(5):
            _rate_limited(req1, scope="test_ip", limit=5)

        # req1 should be rate limited, req2 should not
        assert _rate_limited(req1, scope="test_ip", limit=5) is True
        assert _rate_limited(req2, scope="test_ip", limit=5) is False


@pytest.mark.django_db
class TestWidgetConfig:
    def test_returns_config(self, client):
        response = client.get("/support/widget/config/")
        assert response.status_code == 200
        data = response.json()
        assert data["widget_enabled"] is True
        assert "widget_title" in data

    def test_custom_settings(self, client):
        EscalatedSetting.set("widget_title", "Help Center")
        EscalatedSetting.set("widget_accent_color", "#ff0000")

        response = client.get("/support/widget/config/")
        data = response.json()
        assert data["widget_title"] == "Help Center"
        assert data["widget_accent_color"] == "#ff0000"

    def test_disabled_widget(self, client):
        EscalatedSetting.set("widget_enabled", "false")
        response = client.get("/support/widget/config/")
        assert response.status_code == 403


@pytest.mark.django_db
class TestWidgetArticleSearch:
    def test_search_articles(self, client):
        cat = ArticleCategoryFactory()
        ArticleFactory(category=cat, title="How to reset password", status="published")
        ArticleFactory(category=cat, title="Billing FAQ", status="published")

        response = client.get("/support/widget/articles/search/?q=reset")
        data = response.json()
        assert len(data["articles"]) == 1
        assert data["articles"][0]["title"] == "How to reset password"

    def test_empty_query(self, client):
        response = client.get("/support/widget/articles/search/?q=")
        data = response.json()
        assert data["articles"] == []

    def test_short_query(self, client):
        response = client.get("/support/widget/articles/search/?q=a")
        data = response.json()
        assert data["articles"] == []

    def test_excludes_draft_articles(self, client):
        cat = ArticleCategoryFactory()
        ArticleFactory(category=cat, title="Draft Article", status="draft")

        response = client.get("/support/widget/articles/search/?q=Draft")
        data = response.json()
        assert len(data["articles"]) == 0


@pytest.mark.django_db
class TestWidgetArticleDetail:
    def test_get_published_article(self, client):
        cat = ArticleCategoryFactory()
        article = ArticleFactory(category=cat, title="Test Article", status="published")

        response = client.get(f"/support/widget/articles/{article.pk}/")
        data = response.json()
        assert data["article"]["title"] == "Test Article"

    def test_increments_view_count(self, client):
        cat = ArticleCategoryFactory()
        article = ArticleFactory(category=cat, status="published", view_count=5)

        client.get(f"/support/widget/articles/{article.pk}/")
        article.refresh_from_db()
        assert article.view_count == 6

    def test_draft_returns_404(self, client):
        cat = ArticleCategoryFactory()
        article = ArticleFactory(category=cat, status="draft")

        response = client.get(f"/support/widget/articles/{article.pk}/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestWidgetCreateTicket:
    def test_create_ticket(self, client):
        response = client.post(
            "/support/widget/tickets/create/",
            data=json.dumps(
                {
                    "name": "John Doe",
                    "email": "john@example.com",
                    "subject": "Help me",
                    "description": "I need help with something",
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "reference" in data["ticket"]
        assert "guest_token" in data["ticket"]

        # Verify ticket created
        ticket = Ticket.objects.get(reference=data["ticket"]["reference"])
        assert ticket.guest_name == "John Doe"
        assert ticket.guest_email == "john@example.com"
        assert ticket.channel == "widget"

    def test_validation_errors(self, client):
        response = client.post(
            "/support/widget/tickets/create/",
            data=json.dumps({"name": "", "email": "", "subject": "", "description": ""}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.json()
        assert "errors" in data
        assert "name" in data["errors"]

    def test_disabled_ticket_creation(self, client):
        EscalatedSetting.set("widget_ticket_creation_enabled", "false")
        response = client.post(
            "/support/widget/tickets/create/",
            data=json.dumps(
                {
                    "name": "Test",
                    "email": "test@example.com",
                    "subject": "Test",
                    "description": "Test",
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_guest_policy_unassigned_default_path(self, client):
        """Default mode leaves requester_* null and records guest_* fields."""
        EscalatedSetting.set("guest_policy_mode", "unassigned")
        response = client.post(
            "/support/widget/tickets/create/",
            data=json.dumps(
                {
                    "name": "Alice",
                    "email": "alice@example.com",
                    "subject": "Hi",
                    "description": "Question.",
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 200
        ticket = Ticket.objects.get(reference=response.json()["ticket"]["reference"])
        assert ticket.requester_content_type_id is None
        assert ticket.requester_object_id is None
        assert ticket.guest_email == "alice@example.com"

    def test_guest_policy_guest_user_routes_to_host_user(self, client):
        """guest_user mode sets requester to the configured host user id."""
        from django.contrib.auth import get_user_model
        from django.contrib.contenttypes.models import ContentType

        User = get_user_model()
        shared = User.objects.create(username="support_bot", email="bot@example.com")

        EscalatedSetting.set("guest_policy_mode", "guest_user")
        EscalatedSetting.set("guest_policy_user_id", str(shared.pk))

        response = client.post(
            "/support/widget/tickets/create/",
            data=json.dumps(
                {
                    "name": "Bob",
                    "email": "bob@example.com",
                    "subject": "Hi",
                    "description": "Another question.",
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 200
        ticket = Ticket.objects.get(reference=response.json()["ticket"]["reference"])
        assert ticket.requester_object_id == shared.pk
        assert ticket.requester_content_type_id == ContentType.objects.get_for_model(User).id
        # Agents still see who actually submitted via guest_email:
        assert ticket.guest_email == "bob@example.com"

    def test_guest_policy_guest_user_with_no_id_falls_through(self, client):
        """Misconfigured guest_user (empty / zero id) falls through to unassigned."""
        EscalatedSetting.set("guest_policy_mode", "guest_user")
        EscalatedSetting.set("guest_policy_user_id", "")

        response = client.post(
            "/support/widget/tickets/create/",
            data=json.dumps(
                {
                    "name": "Charlie",
                    "email": "charlie@example.com",
                    "subject": "Hi",
                    "description": "Misconfig scenario.",
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 200
        ticket = Ticket.objects.get(reference=response.json()["ticket"]["reference"])
        assert ticket.requester_content_type_id is None
        assert ticket.requester_object_id is None

    def test_guest_policy_prompt_signup_uses_unassigned_path(self, client):
        """prompt_signup mode behaves like unassigned for ticket creation today."""
        EscalatedSetting.set("guest_policy_mode", "prompt_signup")

        response = client.post(
            "/support/widget/tickets/create/",
            data=json.dumps(
                {
                    "name": "Dana",
                    "email": "dana@example.com",
                    "subject": "Hi",
                    "description": "Signup prompt scenario.",
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 200
        ticket = Ticket.objects.get(reference=response.json()["ticket"]["reference"])
        assert ticket.requester_content_type_id is None
        assert ticket.guest_email == "dana@example.com"


@pytest.mark.django_db
class TestWidgetLookupTicket:
    def test_lookup_by_reference_and_email(self, client):
        ticket = TicketFactory(guest_email="john@example.com")

        response = client.get(f"/support/widget/tickets/lookup/?reference={ticket.reference}&email=john@example.com")
        assert response.status_code == 200
        data = response.json()
        assert data["ticket"]["reference"] == ticket.reference

    def test_wrong_email_returns_404(self, client):
        ticket = TicketFactory(guest_email="john@example.com")

        response = client.get(f"/support/widget/tickets/lookup/?reference={ticket.reference}&email=wrong@example.com")
        assert response.status_code == 404

    def test_missing_params(self, client):
        response = client.get("/support/widget/tickets/lookup/")
        assert response.status_code == 400
