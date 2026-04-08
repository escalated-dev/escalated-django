import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    MAX_ATTEMPTS = 3

    def dispatch(self, event, payload):
        """Send event to all active webhooks subscribed to it."""
        from escalated.models import Webhook

        webhooks = Webhook.objects.active()
        for webhook in webhooks:
            if webhook.subscribed_to(event):
                self.send(webhook, event, payload)

    def send(self, webhook, event, payload, attempt=1):
        """Send a single webhook delivery."""
        from escalated.models import WebhookDelivery

        body = json.dumps(
            {
                "event": event,
                "payload": payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        headers = {
            "Content-Type": "application/json",
            "X-Escalated-Event": event,
        }

        if webhook.secret:
            signature = hmac.new(webhook.secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            headers["X-Escalated-Signature"] = signature

        delivery = WebhookDelivery.objects.create(
            webhook=webhook,
            event=event,
            payload=payload,
            attempts=attempt,
        )

        try:
            response = requests.post(webhook.url, data=body, headers=headers, timeout=10)
            delivery.response_code = response.status_code
            delivery.response_body = response.text[:2000]
            delivery.delivered_at = datetime.now(timezone.utc)
            delivery.attempts = attempt
            delivery.save()

            if not response.ok and attempt < self.MAX_ATTEMPTS:
                self.send(webhook, event, payload, attempt + 1)
        except Exception as e:
            delivery.response_code = 0
            delivery.response_body = str(e)
            delivery.attempts = attempt
            delivery.save()

            logger.warning(
                "Escalated webhook delivery failed",
                extra={
                    "webhook_id": webhook.pk,
                    "event": event,
                    "attempt": attempt,
                    "error": str(e),
                },
            )

            if attempt < self.MAX_ATTEMPTS:
                self.send(webhook, event, payload, attempt + 1)

    def retry_delivery(self, delivery):
        """Retry a specific failed delivery."""
        webhook = delivery.webhook
        if webhook:
            self.send(webhook, delivery.event, delivery.payload or {}, 1)
