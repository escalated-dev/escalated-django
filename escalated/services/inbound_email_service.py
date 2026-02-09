import logging
import os
import re
import secrets

from django.contrib.auth import get_user_model
from django.utils import timezone

from escalated.conf import get_setting
from escalated.mail.inbound_message import InboundMessage
from escalated.models import InboundEmail, Ticket

logger = logging.getLogger("escalated")

# Pattern to match ticket references in subject lines, e.g. [ESC-A1B2C3]
REFERENCE_PATTERN = re.compile(r"\[([A-Za-z]+-[A-Za-z0-9]+)\]")


class InboundEmailService:
    """
    Service responsible for processing inbound emails and converting them
    into tickets or replies within the Escalated system.

    Processing flow:
    1. Check for duplicate message_id
    2. Create InboundEmail log record
    3. Find existing ticket by subject reference pattern
    4. Look up sender as a registered user, fall back to guest
    5. Create a new ticket or add a reply via TicketService/driver
    6. Handle attachments
    7. Update InboundEmail record with result
    """

    ALLOWED_TAGS = {
        'p', 'br', 'b', 'strong', 'i', 'em', 'u', 'a', 'ul', 'ol', 'li',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'code',
        'table', 'thead', 'tbody', 'tr', 'th', 'td', 'img', 'hr', 'div', 'span',
        'sub', 'sup',
    }

    BLOCKED_EXTENSIONS = {
        'exe', 'bat', 'cmd', 'com', 'msi', 'scr', 'pif', 'vbs', 'vbe',
        'js', 'jse', 'wsf', 'wsh', 'ps1', 'psm1', 'psd1', 'reg',
        'cpl', 'hta', 'inf', 'lnk', 'sct', 'shb', 'sys', 'drv',
        'php', 'phtml', 'php3', 'php4', 'php5', 'phar',
        'sh', 'bash', 'csh', 'ksh', 'pl', 'py', 'rb',
        'dll', 'so', 'dylib',
    }

    @staticmethod
    def _sanitize_html(html: str | None) -> str | None:
        """Sanitize HTML to remove dangerous tags, event handlers, and protocols."""
        if not html or not html.strip():
            return html

        allowed = InboundEmailService.ALLOWED_TAGS

        def replace_tag(match):
            tag_name = match.group(1).strip().split()[0].lower().lstrip('/')
            if tag_name in allowed:
                return match.group(0)
            return ''

        clean = re.sub(r'<(/?\s*[a-zA-Z][a-zA-Z0-9]*(?:\s[^>]*)?)>', replace_tag, html)

        # Remove event handler attributes
        clean = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s+on\w+\s*=\s*\S+', '', clean, flags=re.IGNORECASE)

        # Remove javascript: protocol
        clean = re.sub(
            r'\b(href|src|action)\s*=\s*["\']?\s*javascript\s*:',
            r'\1="', clean, flags=re.IGNORECASE,
        )

        # Remove data: URLs except data:image
        clean = re.sub(
            r'\b(href|src|action)\s*=\s*["\']?\s*data\s*:(?!image/)',
            r'\1="', clean, flags=re.IGNORECASE,
        )

        # Remove style with expression()
        clean = re.sub(
            r'style\s*=\s*["\'][^"\']*expression\s*\([^"\']*["\']',
            '', clean, flags=re.IGNORECASE,
        )
        clean = re.sub(
            r'style\s*=\s*["\'][^"\']*url\s*\(\s*["\']?\s*javascript:[^"\']*["\']',
            '', clean, flags=re.IGNORECASE,
        )

        return clean

    @staticmethod
    def _get_sanitized_body(message) -> str:
        """Return the best available body, sanitizing HTML if no plain text is available."""
        if message.body_text:
            return message.body_text
        if message.body_html:
            return InboundEmailService._sanitize_html(message.body_html) or ''
        return ''

    @staticmethod
    def process(message: InboundMessage, adapter_name: str = "unknown") -> InboundEmail:
        """
        Process a single inbound email message.

        Args:
            message: Normalized InboundMessage from an adapter.
            adapter_name: Name of the adapter that produced this message.

        Returns:
            InboundEmail record with processing result.
        """
        # Check for duplicate message_id
        if message.message_id:
            existing = InboundEmail.objects.filter(
                message_id=message.message_id,
                status=InboundEmail.Status.PROCESSED,
            ).first()
            if existing:
                logger.info(
                    f"Duplicate inbound email (message_id={message.message_id}), skipping"
                )
                return existing

        # Create the InboundEmail log record
        inbound = InboundEmail.objects.create(
            message_id=message.message_id,
            from_email=message.from_email,
            from_name=message.from_name,
            to_email=message.to_email,
            subject=message.subject,
            body_text=message.body_text,
            body_html=InboundEmailService._sanitize_html(message.body_html),
            raw_headers="\n".join(
                f"{k}: {v}" for k, v in message.headers.items()
            ) if message.headers else None,
            adapter=adapter_name,
            status=InboundEmail.Status.PENDING,
        )

        try:
            ticket, reply = InboundEmailService._process_message(message, inbound)
            inbound.mark_processed(ticket, reply)
            logger.info(
                f"Inbound email processed: {message.from_email} -> "
                f"ticket {ticket.reference}"
                + (f" (reply #{reply.pk})" if reply else " (new ticket)")
            )
        except Exception as exc:
            inbound.mark_failed(str(exc))
            logger.error(
                f"Failed to process inbound email from {message.from_email}: {exc}"
            )

        return inbound

    @staticmethod
    def _process_message(message: InboundMessage, inbound: InboundEmail):
        """
        Core processing logic. Returns (ticket, reply_or_none).

        Raises an exception on failure (caught by process()).
        """
        from escalated.drivers import get_driver
        from escalated.services.attachment_service import AttachmentService

        driver = get_driver()

        # Try to find an existing ticket by subject reference
        ticket = InboundEmailService._find_ticket_by_reference(message.subject)

        # Also try by In-Reply-To / References headers
        if ticket is None and message.in_reply_to:
            ticket = InboundEmailService._find_ticket_by_message_id(
                message.in_reply_to
            )
        if ticket is None and message.references:
            ticket = InboundEmailService._find_ticket_by_references(
                message.references
            )

        # Resolve sender — try to find a registered user first
        User = get_user_model()
        user = None
        try:
            user = User.objects.get(email__iexact=message.from_email)
        except User.DoesNotExist:
            pass
        except User.MultipleObjectsReturned:
            user = User.objects.filter(email__iexact=message.from_email).first()

        if ticket is not None:
            # Existing ticket — add a reply
            reply = InboundEmailService._add_reply(
                driver, ticket, user, message
            )

            # Handle attachments on the reply
            InboundEmailService._handle_attachments(
                reply, message.attachments
            )

            return ticket, reply
        else:
            # New ticket
            ticket, reply = InboundEmailService._create_ticket(
                driver, user, message
            )

            # Handle attachments on the ticket
            InboundEmailService._handle_attachments(
                ticket, message.attachments
            )

            return ticket, reply

    @staticmethod
    def _find_ticket_by_reference(subject: str):
        """
        Search the email subject for a ticket reference pattern like [ESC-A1B2C3].

        Returns the Ticket instance if found, None otherwise.
        """
        match = REFERENCE_PATTERN.search(subject)
        if match:
            reference = match.group(1)
            try:
                return Ticket.objects.get(reference=reference)
            except Ticket.DoesNotExist:
                logger.debug(
                    f"Reference '{reference}' found in subject but no matching ticket"
                )
        return None

    @staticmethod
    def _find_ticket_by_message_id(message_id: str):
        """
        Find a ticket by looking for an InboundEmail with the given message_id
        that was already processed.
        """
        previous = InboundEmail.objects.filter(
            message_id=message_id,
            status=InboundEmail.Status.PROCESSED,
            ticket__isnull=False,
        ).select_related("ticket").first()
        return previous.ticket if previous else None

    @staticmethod
    def _find_ticket_by_references(references: str):
        """
        Search the References header for any known message_ids.

        The References header can contain multiple message IDs separated
        by whitespace.
        """
        message_ids = references.strip().split()
        for mid in reversed(message_ids):  # Check most recent first
            mid = mid.strip("<>")
            ticket = InboundEmailService._find_ticket_by_message_id(mid)
            if ticket:
                return ticket
        return None

    @staticmethod
    def _add_reply(driver, ticket, user, message: InboundMessage):
        """Add a reply to an existing ticket."""
        body = InboundEmailService._get_sanitized_body(message) or "(empty email body)"

        reply_data = {
            "body": body,
            "is_internal_note": False,
            "metadata": {
                "source": "inbound_email",
                "message_id": message.message_id,
            },
        }

        reply = driver.add_reply(ticket, user, reply_data)
        return reply

    @staticmethod
    def _create_ticket(driver, user, message: InboundMessage):
        """
        Create a new ticket from an inbound email.

        If the sender is a registered user, create a normal ticket.
        If not, create a guest ticket.
        """
        body = InboundEmailService._get_sanitized_body(message) or "(empty email body)"
        subject = message.subject or "(no subject)"

        if user is not None:
            # Authenticated user ticket
            ticket = driver.create_ticket(user, {
                "subject": subject,
                "description": body,
                "priority": get_setting("DEFAULT_PRIORITY"),
                "channel": "email",
                "metadata": {
                    "source": "inbound_email",
                    "message_id": message.message_id,
                },
            })
        else:
            # Guest ticket (follows the same pattern as views/guest.py)
            guest_token = secrets.token_hex(32)
            ticket = Ticket.objects.create(
                requester_content_type=None,
                requester_object_id=None,
                guest_name=message.from_name or message.from_email,
                guest_email=message.from_email,
                guest_token=guest_token,
                subject=subject,
                description=body,
                priority=get_setting("DEFAULT_PRIORITY"),
                channel="email",
                metadata={
                    "source": "inbound_email",
                    "message_id": message.message_id,
                },
            )

            # Fire the ticket_created signal manually for guest tickets
            # (the driver.create_ticket handles this for auth users)
            from escalated.signals import ticket_created

            ticket_created.send(sender=Ticket, ticket=ticket, user=None)

        return ticket, None  # No reply for new tickets

    @staticmethod
    def _handle_attachments(content_object, attachments: list):
        """
        Attach files from the inbound email to the ticket or reply.

        Handles both uploaded file objects (Mailgun) and raw data (IMAP).
        """
        if not attachments:
            return

        from escalated.services.attachment_service import AttachmentService

        max_attachments = get_setting("MAX_ATTACHMENTS")

        for i, att in enumerate(attachments):
            if i >= max_attachments:
                logger.warning(
                    f"Attachment limit ({max_attachments}) reached, "
                    f"skipping remaining attachments"
                )
                break

            # Block dangerous file extensions
            filename = att.get('filename', '')
            _, extension = os.path.splitext(filename)
            extension = extension.lower().lstrip('.')
            if extension and extension in InboundEmailService.BLOCKED_EXTENSIONS:
                logger.info(
                    f'Escalated: Blocked dangerous inbound attachment.',
                    extra={
                        'filename': filename,
                        'extension': extension,
                    },
                )
                continue

            try:
                # Adapter may provide a Django UploadedFile (Mailgun)
                # or raw data (IMAP) or base64 content (Postmark)
                uploaded_file = att.get("file")

                if uploaded_file is not None:
                    # Django UploadedFile (from Mailgun multipart upload)
                    AttachmentService.attach(
                        content_object,
                        uploaded_file,
                        original_filename=att.get("filename"),
                    )
                elif att.get("data") is not None:
                    # Raw bytes (from IMAP)
                    from django.core.files.base import ContentFile

                    filename = att.get("filename", "unnamed")
                    content_file = ContentFile(att["data"], name=filename)
                    AttachmentService.attach(
                        content_object,
                        content_file,
                        original_filename=filename,
                    )
                elif att.get("content_base64") is not None:
                    # Base64-encoded content (from Postmark)
                    import base64

                    from django.core.files.base import ContentFile

                    filename = att.get("filename", "unnamed")
                    raw_data = base64.b64decode(att["content_base64"])
                    content_file = ContentFile(raw_data, name=filename)
                    AttachmentService.attach(
                        content_object,
                        content_file,
                        original_filename=filename,
                    )
                else:
                    logger.warning(
                        f"Attachment '{att.get('filename', 'unnamed')}' "
                        f"has no file data, skipping"
                    )
            except Exception as exc:
                logger.error(
                    f"Failed to attach file '{att.get('filename', 'unnamed')}': {exc}"
                )
