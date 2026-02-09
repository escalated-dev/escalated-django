import hashlib
import hmac
import json
import logging

from escalated.conf import get_setting
from escalated.mail.adapters.base import BaseAdapter
from escalated.mail.inbound_message import InboundMessage

logger = logging.getLogger("escalated")


class MailgunAdapter(BaseAdapter):
    """
    Adapter for Mailgun inbound email webhooks.

    Mailgun sends inbound emails as multipart/form-data POST requests.
    Signature verification uses HMAC-SHA256 with the Mailgun signing key.

    Expected POST fields:
        - sender: From email address
        - from: Full From header (e.g. "Name <email@example.com>")
        - recipient: To email address
        - subject: Email subject
        - body-plain: Plain text body
        - body-html: HTML body
        - Message-Id: Message-ID header
        - In-Reply-To: In-Reply-To header
        - References: References header
        - message-headers: JSON-encoded list of [name, value] pairs
        - timestamp: Unix timestamp
        - token: Unique token
        - signature: HMAC signature
        - attachment-count: Number of attachments
        - attachment-N: Uploaded file attachments
    """

    @property
    def name(self) -> str:
        return "mailgun"

    def verify_request(self, request) -> bool:
        """
        Verify the Mailgun webhook signature.

        The signature is an HMAC-SHA256 hex digest of:
            timestamp + token
        signed with the Mailgun API key.
        """
        signing_key = get_setting("MAILGUN_SIGNING_KEY")
        if not signing_key:
            logger.warning(
                "Mailgun signing key not configured. "
                "Set ESCALATED['MAILGUN_SIGNING_KEY'] in settings."
            )
            return False

        timestamp = request.POST.get("timestamp", "")
        token = request.POST.get("token", "")
        signature = request.POST.get("signature", "")

        if not all([timestamp, token, signature]):
            logger.warning("Mailgun webhook missing signature fields")
            return False

        expected = hmac.new(
            signing_key.encode("utf-8"),
            f"{timestamp}{token}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def parse_request(self, request) -> InboundMessage:
        """Parse a Mailgun inbound webhook into an InboundMessage."""
        from_header = request.POST.get("from", "")
        from_name, from_email = self._parse_from(from_header)

        # Fall back to "sender" field if "from" parsing gives empty email
        if not from_email:
            from_email = request.POST.get("sender", "")

        # Parse headers from JSON
        headers = {}
        raw_headers_json = request.POST.get("message-headers", "")
        if raw_headers_json:
            try:
                header_pairs = json.loads(raw_headers_json)
                headers = {h[0]: h[1] for h in header_pairs if len(h) >= 2}
            except (json.JSONDecodeError, TypeError):
                pass

        # Collect attachments
        attachments = []
        attachment_count = int(request.POST.get("attachment-count", 0))
        for i in range(1, attachment_count + 1):
            uploaded_file = request.FILES.get(f"attachment-{i}")
            if uploaded_file:
                attachments.append({
                    "filename": uploaded_file.name,
                    "content_type": uploaded_file.content_type,
                    "size": uploaded_file.size,
                    "file": uploaded_file,
                })

        return InboundMessage(
            from_email=from_email,
            from_name=from_name or None,
            to_email=request.POST.get("recipient", ""),
            subject=request.POST.get("subject", ""),
            body_text=request.POST.get("body-plain"),
            body_html=request.POST.get("body-html"),
            message_id=request.POST.get("Message-Id"),
            in_reply_to=request.POST.get("In-Reply-To"),
            references=request.POST.get("References"),
            headers=headers,
            attachments=attachments,
        )

    @staticmethod
    def _parse_from(from_header: str) -> tuple:
        """
        Parse a From header like "John Doe <john@example.com>" into
        (name, email). Returns ("", raw_header) if parsing fails.
        """
        if "<" in from_header and ">" in from_header:
            parts = from_header.rsplit("<", 1)
            name = parts[0].strip().strip('"')
            email = parts[1].rstrip(">").strip()
            return name, email
        return "", from_header.strip()
