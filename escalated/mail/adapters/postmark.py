import hmac as hmac_module
import json
import logging

from escalated.conf import get_setting
from escalated.mail.adapters.base import BaseAdapter
from escalated.mail.inbound_message import InboundMessage

logger = logging.getLogger("escalated")


class PostmarkAdapter(BaseAdapter):
    """
    Adapter for Postmark inbound email webhooks.

    Postmark sends inbound emails as JSON POST requests.

    Expected JSON fields:
        - FromFull: { Email, Name }
        - ToFull: [{ Email, Name }]
        - Subject: string
        - TextBody: plain text body
        - HtmlBody: HTML body
        - MessageID: Postmark message ID
        - Headers: [{ Name, Value }]
        - Attachments: [{ Name, ContentType, ContentLength, Content (base64) }]
    """

    @property
    def name(self) -> str:
        return "postmark"

    def verify_request(self, request) -> bool:
        """
        Verify the Postmark inbound webhook.

        Postmark does not use signature-based verification for inbound webhooks.
        Instead, it relies on the unique inbound address hash. We verify the
        request by checking for the presence of the configured inbound token
        in the request headers (X-Postmark-Inbound-Token) if one is set.
        """
        expected_token = get_setting("POSTMARK_INBOUND_TOKEN")
        if not expected_token:
            # No token configured — reject request for security
            logger.warning(
                "Escalated: Postmark inbound token not configured — "
                "rejecting request."
            )
            return False

        # Postmark can include the token as a query param or header
        request_token = request.headers.get("X-Postmark-Inbound-Token", "")
        if not request_token:
            request_token = request.GET.get("token", "")

        if not request_token:
            logger.warning("Postmark webhook missing inbound token")
            return False

        return hmac_module.compare_digest(request_token, expected_token)

    def parse_request(self, request) -> InboundMessage:
        """Parse a Postmark inbound webhook JSON payload into an InboundMessage."""
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"Invalid Postmark JSON payload: {exc}") from exc

        from_full = data.get("FromFull", {})
        from_email = from_full.get("Email", data.get("From", ""))
        from_name = from_full.get("Name") or None

        # Extract first To address
        to_full = data.get("ToFull", [])
        to_email = to_full[0]["Email"] if to_full else data.get("To", "")

        # Parse headers into dict
        headers = {}
        for header in data.get("Headers", []):
            headers[header.get("Name", "")] = header.get("Value", "")

        in_reply_to = headers.get("In-Reply-To")
        references = headers.get("References")
        message_id = data.get("MessageID") or headers.get("Message-ID")

        # Collect attachments (Postmark sends base64-encoded content)
        attachments = []
        for att in data.get("Attachments", []):
            attachments.append({
                "filename": att.get("Name", "unnamed"),
                "content_type": att.get("ContentType", "application/octet-stream"),
                "size": att.get("ContentLength", 0),
                "content_base64": att.get("Content"),
            })

        # Build raw headers string for storage
        raw_headers = "\n".join(
            f"{h.get('Name', '')}: {h.get('Value', '')}"
            for h in data.get("Headers", [])
        )

        return InboundMessage(
            from_email=from_email,
            from_name=from_name,
            to_email=to_email,
            subject=data.get("Subject", ""),
            body_text=data.get("TextBody"),
            body_html=data.get("HtmlBody"),
            message_id=message_id,
            in_reply_to=in_reply_to,
            references=references,
            headers=headers,
            attachments=attachments,
        )
