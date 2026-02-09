import logging
import time

from django.core.management.base import BaseCommand

from escalated.conf import get_setting

logger = logging.getLogger("escalated")


class Command(BaseCommand):
    help = (
        "Poll an IMAP mailbox for new inbound emails and process them as "
        "tickets or replies."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--continuous",
            action="store_true",
            default=False,
            help="Run continuously, polling at a regular interval.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Polling interval in seconds when running continuously (default: 60).",
        )

    def handle(self, *args, **options):
        if not get_setting("INBOUND_EMAIL_ENABLED"):
            self.stderr.write(
                self.style.ERROR(
                    "Inbound email processing is disabled. "
                    "Set ESCALATED['INBOUND_EMAIL_ENABLED'] = True in settings."
                )
            )
            return

        host = get_setting("IMAP_HOST")
        if not host:
            self.stderr.write(
                self.style.ERROR(
                    "IMAP host not configured. "
                    "Set ESCALATED['IMAP_HOST'] in settings."
                )
            )
            return

        continuous = options["continuous"]
        interval = options["interval"]

        if continuous:
            self.stdout.write(
                f"Starting continuous IMAP polling (interval: {interval}s)..."
            )
            while True:
                try:
                    self._poll_once()
                except KeyboardInterrupt:
                    self.stdout.write("\nStopping IMAP polling.")
                    break
                except Exception as exc:
                    self.stderr.write(
                        self.style.ERROR(f"Error during IMAP poll: {exc}")
                    )
                    logger.exception("Error during IMAP poll")

                time.sleep(interval)
        else:
            self._poll_once()

    def _poll_once(self):
        """Execute a single IMAP poll cycle."""
        from escalated.mail.adapters.imap import IMAPAdapter
        from escalated.services.inbound_email_service import InboundEmailService

        adapter = IMAPAdapter()

        self.stdout.write("Connecting to IMAP server...")

        try:
            messages = adapter.fetch_messages()
        except ConnectionError as exc:
            self.stderr.write(self.style.ERROR(f"IMAP connection failed: {exc}"))
            return

        if not messages:
            self.stdout.write("No new messages found.")
            return

        self.stdout.write(f"Found {len(messages)} new message(s). Processing...")

        processed = 0
        failed = 0

        for message in messages:
            inbound = InboundEmailService.process(message, adapter_name="imap")
            if inbound.status == "processed":
                processed += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Processed: {message.from_email} - {message.subject}"
                    )
                )
            else:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"  Failed: {message.from_email} - {message.subject}"
                        f" ({inbound.error_message})"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"IMAP poll complete: {processed} processed, {failed} failed."
            )
        )
