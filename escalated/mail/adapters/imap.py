from __future__ import annotations

import email
import imaplib
import logging
from email import policy

from escalated.conf import get_setting
from escalated.mail.adapters.base import BaseAdapter
from escalated.mail.inbound_message import InboundMessage

logger = logging.getLogger("escalated")


class IMAPAdapter(BaseAdapter):
    """
    Adapter for polling an IMAP mailbox for inbound emails.

    Unlike the webhook-based adapters, this adapter is not called from a
    web request. Instead, it connects to an IMAP server, fetches unread
    messages, and returns them as InboundMessage instances.

    Used by the `poll_imap` management command.
    """

    @property
    def name(self) -> str:
        return "imap"

    def verify_request(self, request) -> bool:
        """IMAP adapter does not receive webhook requests."""
        return False

    def parse_request(self, request) -> InboundMessage:
        """IMAP adapter does not parse webhook requests."""
        raise NotImplementedError(
            "IMAPAdapter does not handle webhook requests. "
            "Use fetch_messages() instead."
        )

    def connect(self) -> imaplib.IMAP4_SSL | imaplib.IMAP4:
        """
        Establish a connection to the configured IMAP server.

        Returns:
            An authenticated IMAP connection.

        Raises:
            ConnectionError: If connection or authentication fails.
        """
        host = get_setting("IMAP_HOST")
        port = get_setting("IMAP_PORT")
        encryption = get_setting("IMAP_ENCRYPTION")
        username = get_setting("IMAP_USERNAME")
        password = get_setting("IMAP_PASSWORD")

        if not all([host, username, password]):
            raise ConnectionError(
                "IMAP connection settings are incomplete. "
                "Set IMAP_HOST, IMAP_USERNAME, and IMAP_PASSWORD in ESCALATED settings."
            )

        try:
            if encryption == "ssl":
                conn = imaplib.IMAP4_SSL(host, port or 993)
            else:
                conn = imaplib.IMAP4(host, port or 143)
                if encryption == "starttls":
                    conn.starttls()

            conn.login(username, password)
            logger.info(f"Connected to IMAP server {host}:{port}")
            return conn
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ConnectionError(
                f"Failed to connect to IMAP server {host}:{port}: {exc}"
            ) from exc

    def fetch_messages(self) -> list[InboundMessage]:
        """
        Connect to the IMAP server, fetch all unread messages, parse them
        into InboundMessage instances, and mark them as read.

        Returns:
            List of InboundMessage instances.
        """
        conn = self.connect()
        mailbox = get_setting("IMAP_MAILBOX") or "INBOX"
        messages = []

        try:
            status, data = conn.select(mailbox)
            if status != "OK":
                logger.error(f"Failed to select IMAP mailbox '{mailbox}': {data}")
                return messages

            # Search for unread messages
            status, msg_ids = conn.search(None, "UNSEEN")
            if status != "OK" or not msg_ids[0]:
                logger.debug("No unread messages found in IMAP mailbox")
                return messages

            message_nums = msg_ids[0].split()
            logger.info(f"Found {len(message_nums)} unread message(s) in IMAP mailbox")

            for num in message_nums:
                try:
                    status, msg_data = conn.fetch(num, "(RFC822)")
                    if status != "OK":
                        logger.warning(f"Failed to fetch IMAP message {num}")
                        continue

                    raw_email = msg_data[0][1]
                    if isinstance(raw_email, bytes):
                        raw_email = raw_email.decode("utf-8", errors="replace")

                    inbound_msg = self._parse_raw_email(raw_email)
                    messages.append(inbound_msg)

                    # Mark as read (add \Seen flag)
                    conn.store(num, "+FLAGS", "\\Seen")

                except Exception as exc:
                    logger.error(f"Error processing IMAP message {num}: {exc}")
                    continue

        finally:
            try:
                conn.close()
                conn.logout()
            except Exception:
                pass

        return messages

    def _parse_raw_email(self, raw_email: str) -> InboundMessage:
        """
        Parse a raw RFC822 email string into an InboundMessage.

        Args:
            raw_email: The raw email content as a string.

        Returns:
            InboundMessage instance.
        """
        msg = email.message_from_string(raw_email, policy=policy.default)

        # Parse From header
        from_header = str(msg.get("From", ""))
        from_name, from_email_addr = self._parse_address(from_header)

        # Parse To header
        to_header = str(msg.get("To", ""))
        _, to_email = self._parse_address(to_header)

        # Extract body parts
        text_body = None
        html_body = None
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    filename = part.get_filename() or "unnamed"
                    payload = part.get_payload(decode=True)
                    attachments.append({
                        "filename": filename,
                        "content_type": content_type,
                        "size": len(payload) if payload else 0,
                        "data": payload,
                    })
                    continue

                if content_type == "text/plain" and text_body is None:
                    text_body = part.get_content()
                elif content_type == "text/html" and html_body is None:
                    html_body = part.get_content()
        else:
            content_type = msg.get_content_type()
            body_content = msg.get_content()
            if content_type == "text/html":
                html_body = body_content
            else:
                text_body = body_content

        # Build headers dict
        headers = {}
        raw_headers_lines = []
        for key in msg.keys():
            headers[key] = str(msg[key])
            raw_headers_lines.append(f"{key}: {msg[key]}")

        return InboundMessage(
            from_email=from_email_addr,
            from_name=from_name or None,
            to_email=to_email,
            subject=str(msg.get("Subject", "")),
            body_text=text_body,
            body_html=html_body,
            message_id=str(msg.get("Message-ID", "")),
            in_reply_to=str(msg.get("In-Reply-To", "")) or None,
            references=str(msg.get("References", "")) or None,
            headers=headers,
            attachments=attachments,
        )

    @staticmethod
    def _parse_address(header_value: str) -> tuple:
        """Parse an email address header into (name, email)."""
        if "<" in header_value and ">" in header_value:
            parts = header_value.rsplit("<", 1)
            name = parts[0].strip().strip('"')
            addr = parts[1].rstrip(">").strip()
            return name, addr
        return "", header_value.strip()
