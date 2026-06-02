import json
from unittest.mock import patch

import pytest
from django.http import HttpResponse
from django.test import Client, override_settings

from escalated.models import Role
from tests.factories import UserFactory


@pytest.fixture
def admin_client(db):
    user = UserFactory(username="nl_admin", is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def newsletters_on():
    with override_settings(ESCALATED={"enable_newsletters": True, "UI_ENABLED": True, "app_url": "http://testserver"}):
        yield


@pytest.mark.django_db
class TestNewsletterHttp:
    def test_public_routes_404_when_disabled(self, admin_client):
        resp = admin_client.get("/support/escalated/n/o/testtoken/")
        assert resp.status_code == 404

    def test_public_open_when_enabled(self, admin_client, newsletters_on):
        resp = admin_client.get("/support/escalated/n/o/abc123/")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "image/png"

    def test_admin_index_requires_auth(self, newsletters_on):
        client = Client()
        resp = client.get("/support/admin/newsletters/")
        assert resp.status_code in (302, 403)

    def test_admin_index_renders(self, admin_client, newsletters_on):
        with patch("escalated.views.newsletter_admin.render_page") as mock_render:
            mock_render.return_value = HttpResponse(status=200)
            admin_client.get("/support/admin/newsletters/")
            mock_render.assert_called_once()
            assert mock_render.call_args[0][1] == "Escalated/Admin/Newsletters/Index"

    def test_permission_enforcement(self, newsletters_on):
        user = UserFactory(username="agent_nl", is_staff=False)
        role = Role.objects.create(name="No News", slug="no_news")
        client = Client()
        client.force_login(user)
        resp = client.get("/support/admin/newsletters/")
        assert resp.status_code == 403

    def test_webhook_postmark(self, admin_client, newsletters_on):
        resp = admin_client.post(
            "/support/escalated/webhooks/newsletter/postmark/",
            data=json.dumps({"RecordType": "Open", "MessageID": "<n-1-abc123@localhost>"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_view_in_browser_always_200(self, admin_client, newsletters_on):
        resp = admin_client.get("/support/escalated/n/v/missing/")
        assert resp.status_code == 200
        assert "unavailable" in resp.content.decode().lower()
