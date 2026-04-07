from unittest.mock import MagicMock, patch

import pytest

from escalated.models import WebhookDelivery
from escalated.services.webhook_dispatcher import WebhookDispatcher
from tests.factories import WebhookFactory


@pytest.mark.django_db
class TestWebhookDispatcher:
    def test_creates_delivery_record(self):
        webhook = WebhookFactory(events=["ticket.created"], active=True)
        dispatcher = WebhookDispatcher()

        with patch("escalated.services.webhook_dispatcher.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, text="OK")
            dispatcher.dispatch("ticket.created", {"ticket_id": 1})

        assert WebhookDelivery.objects.filter(webhook=webhook).exists()

    def test_skips_inactive_webhook(self):
        WebhookFactory(events=["ticket.created"], active=False)
        dispatcher = WebhookDispatcher()

        with patch("escalated.services.webhook_dispatcher.requests.post") as mock_post:
            dispatcher.dispatch("ticket.created", {"ticket_id": 1})
            mock_post.assert_not_called()

        assert WebhookDelivery.objects.count() == 0

    def test_skips_unsubscribed_event(self):
        WebhookFactory(events=["ticket.resolved"], active=True)
        dispatcher = WebhookDispatcher()

        with patch("escalated.services.webhook_dispatcher.requests.post") as mock_post:
            dispatcher.dispatch("ticket.created", {"ticket_id": 1})
            mock_post.assert_not_called()

        assert WebhookDelivery.objects.count() == 0

    def test_includes_signature_when_secret_set(self):
        WebhookFactory(events=["ticket.created"], active=True, secret="my-secret")
        dispatcher = WebhookDispatcher()

        with patch("escalated.services.webhook_dispatcher.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, text="OK")
            dispatcher.dispatch("ticket.created", {"ticket_id": 1})

            call_kwargs = mock_post.call_args
            assert "X-Escalated-Signature" in call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
