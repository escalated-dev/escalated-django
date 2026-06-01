from unittest.mock import MagicMock, patch

from escalated.services.notification_service import NotificationService

PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 443))]


class TestNotificationWebhookSecurity:
    def test_blocks_private_legacy_webhook_url(self, settings):
        settings.ESCALATED = {
            "WEBHOOK_URL": "http://127.0.0.1:8000/hook",
        }

        with patch("escalated.services.notification_service.requests.post") as mock_post:
            NotificationService._fire_webhook("ticket.created", {"ticket_id": 1})

        mock_post.assert_not_called()

    def test_sends_public_legacy_webhook_url(self, settings):
        settings.ESCALATED = {
            "WEBHOOK_URL": "https://example.com/hook",
        }

        with (
            patch("escalated.outbound_security.socket.getaddrinfo", return_value=PUBLIC_ADDRINFO),
            patch("escalated.services.notification_service.requests.post") as mock_post,
        ):
            mock_post.return_value = MagicMock(status_code=200, text="OK")

            NotificationService._fire_webhook("ticket.created", {"ticket_id": 1})

        mock_post.assert_called_once()
