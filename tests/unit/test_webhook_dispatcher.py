from unittest.mock import MagicMock, patch

import pytest

from escalated.models import WebhookDelivery
from escalated.services.webhook_dispatcher import WebhookDispatcher
from tests.factories import WebhookFactory

PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 443))]


@pytest.mark.django_db
class TestWebhookDispatcher:
    def test_creates_delivery_record(self):
        webhook = WebhookFactory(events=["ticket.created"], active=True)
        dispatcher = WebhookDispatcher()

        with (
            patch("escalated.outbound_security.socket.getaddrinfo", return_value=PUBLIC_ADDRINFO),
            patch("escalated.services.webhook_dispatcher.requests.post") as mock_post,
        ):
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

        with (
            patch("escalated.outbound_security.socket.getaddrinfo", return_value=PUBLIC_ADDRINFO),
            patch("escalated.services.webhook_dispatcher.requests.post") as mock_post,
        ):
            mock_post.return_value = MagicMock(status_code=200, text="OK")
            dispatcher.dispatch("ticket.created", {"ticket_id": 1})

            call_kwargs = mock_post.call_args
            assert "X-Escalated-Signature" in call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))

    def test_does_not_follow_redirects_after_validation(self):
        WebhookFactory(events=["ticket.created"], active=True, url="https://example.com/hook")
        dispatcher = WebhookDispatcher()

        with (
            patch("escalated.outbound_security.socket.getaddrinfo", return_value=PUBLIC_ADDRINFO),
            patch("escalated.services.webhook_dispatcher.requests.post") as mock_post,
        ):
            mock_post.return_value = MagicMock(status_code=302, text="redirect")
            dispatcher.dispatch("ticket.created", {"ticket_id": 1})

        assert mock_post.call_args.kwargs["allow_redirects"] is False

    def test_blocks_private_webhook_target(self):
        webhook = WebhookFactory(events=["ticket.created"], active=True, url="http://127.0.0.1:8000/hook")
        dispatcher = WebhookDispatcher()

        with patch("escalated.services.webhook_dispatcher.requests.post") as mock_post:
            dispatcher.dispatch("ticket.created", {"ticket_id": 1})

        mock_post.assert_not_called()
        delivery = WebhookDelivery.objects.get(webhook=webhook)
        assert delivery.response_code == 0
        assert "non-public address" in delivery.response_body
