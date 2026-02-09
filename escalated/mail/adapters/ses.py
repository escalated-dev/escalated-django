import base64
import hashlib
import json
import logging
import re

from escalated.conf import get_setting
from escalated.mail.adapters.base import BaseAdapter
from escalated.mail.inbound_message import InboundMessage

logger = logging.getLogger("escalated")


class SESAdapter(BaseAdapter):
    """
    Adapter for AWS SES inbound email via SNS notifications.

    AWS SES can be configured to publish inbound emails to an SNS topic,
    which then POSTs to a webhook URL. The request body is a JSON-encoded
    SNS notification.

    Flow:
    1. SNS sends a SubscriptionConfirmation request (must auto-confirm).
    2. SNS sends Notification messages with the SES email content.

    The SES notification content includes:
        - mail.source: sender email
        - mail.commonHeaders: { from, to, subject, messageId }
        - content: Raw email (base64-encoded or plain)
    """

    @property
    def name(self) -> str:
        return "ses"

    def verify_request(self, request) -> bool:
        """
        Verify the SNS notification by checking the Topic ARN.

        For production use, full SNS signature verification (using the
        signing certificate) is recommended. This implementation validates
        the Topic ARN as a basic check and logs a warning about full
        verification.
        """
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, TypeError):
            logger.warning("SES adapter: invalid JSON in request body")
            return False

        # Verify Topic ARN if configured
        expected_arn = get_setting("SES_TOPIC_ARN")
        if expected_arn:
            topic_arn = data.get("TopicArn", "")
            if topic_arn != expected_arn:
                logger.warning(
                    f"SES adapter: Topic ARN mismatch. "
                    f"Expected '{expected_arn}', got '{topic_arn}'"
                )
                return False

        return True

    def parse_request(self, request) -> InboundMessage:
        """Parse an SNS notification containing an SES inbound email."""
        try:
            sns_data = json.loads(request.body)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"Invalid SNS JSON payload: {exc}") from exc

        message_type = sns_data.get("Type", "")

        # Handle subscription confirmation
        if message_type == "SubscriptionConfirmation":
            self._handle_subscription_confirmation(sns_data)
            raise ValueError("SNS SubscriptionConfirmation handled")

        if message_type != "Notification":
            raise ValueError(f"Unexpected SNS message type: {message_type}")

        # Parse the SES notification from the Message field
        try:
            ses_message = json.loads(sns_data.get("Message", "{}"))
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(
                f"Invalid SES message in SNS notification: {exc}"
            ) from exc

        mail_data = ses_message.get("mail", {})
        common_headers = mail_data.get("commonHeaders", {})

        # Extract from address
        from_list = common_headers.get("from", [])
        from_header = from_list[0] if from_list else mail_data.get("source", "")
        from_name, from_email = self._parse_from(from_header)

        # Extract to address
        to_list = common_headers.get("to", [])
        to_email = to_list[0] if to_list else ""
        # Strip display name if present
        if "<" in to_email:
            to_email = to_email.split("<")[1].rstrip(">")

        # Extract body from content (if raw email is included)
        body_text = None
        body_html = None
        content = ses_message.get("content", "")

        if content:
            body_text, body_html = self._parse_raw_email(content)

        # Build headers from SES mail headers
        headers = {}
        for header in mail_data.get("headers", []):
            headers[header.get("name", "")] = header.get("value", "")

        return InboundMessage(
            from_email=from_email,
            from_name=from_name or None,
            to_email=to_email,
            subject=common_headers.get("subject", ""),
            body_text=body_text,
            body_html=body_html,
            message_id=common_headers.get("messageId") or mail_data.get("messageId"),
            in_reply_to=headers.get("In-Reply-To"),
            references=headers.get("References"),
            headers=headers,
            attachments=[],  # SES SNS notifications don't include attachments inline
        )

    @staticmethod
    def _handle_subscription_confirmation(data):
        """
        Auto-confirm an SNS subscription by fetching the SubscribeURL.

        This allows the webhook endpoint to be registered with SNS
        automatically when it first receives the confirmation request.
        """
        subscribe_url = data.get("SubscribeURL")
        if not subscribe_url:
            logger.warning("SNS SubscriptionConfirmation missing SubscribeURL")
            return

        try:
            import urllib.request

            urllib.request.urlopen(subscribe_url, timeout=10)
            logger.info(f"SNS subscription confirmed: {data.get('TopicArn', '')}")
        except Exception as exc:
            logger.error(f"Failed to confirm SNS subscription: {exc}")

    @staticmethod
    def _parse_from(from_header: str) -> tuple:
        """Parse a From header into (name, email)."""
        if "<" in from_header and ">" in from_header:
            parts = from_header.rsplit("<", 1)
            name = parts[0].strip().strip('"')
            email = parts[1].rstrip(">").strip()
            return name, email
        return "", from_header.strip()

    @staticmethod
    def _parse_raw_email(raw_content: str) -> tuple:
        """
        Parse a raw email string into (text_body, html_body).

        Uses Python's email module for robust MIME parsing.
        """
        import email
        from email import policy

        try:
            msg = email.message_from_string(raw_content, policy=policy.default)
        except Exception:
            # If parsing fails, return the raw content as plain text
            return raw_content, None

        text_body = None
        html_body = None

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # Skip attachments
                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain" and text_body is None:
                    text_body = part.get_content()
                elif content_type == "text/html" and html_body is None:
                    html_body = part.get_content()
        else:
            content_type = msg.get_content_type()
            body = msg.get_content()
            if content_type == "text/html":
                html_body = body
            else:
                text_body = body

        return text_body, html_body
