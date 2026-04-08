from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.translation import gettext as _

from escalated.models import ChatSession, Ticket


class Command(BaseCommand):
    help = "Mark waiting chat sessions as abandoned after a configurable timeout."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes",
            type=int,
            default=10,
            help=_("Minutes before a waiting chat is considered abandoned (default: 10)"),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_("Show what would be cleaned up without making changes"),
        )

    def handle(self, *args, **options):
        minutes = options["minutes"]
        dry_run = options["dry_run"]
        threshold = timezone.now() - timedelta(minutes=minutes)

        abandoned_sessions = ChatSession.objects.filter(
            status=ChatSession.Status.WAITING,
            created_at__lt=threshold,
        )

        count = abandoned_sessions.count()

        if dry_run:
            self.stdout.write(
                _("[DRY RUN] Would mark %(count)d chat sessions as abandoned (waiting > %(minutes)d min).")
                % {"count": count, "minutes": minutes}
            )
            for session in abandoned_sessions[:20]:
                self.stdout.write(f"  - Session {session.pk}: ticket {session.ticket.reference}")
            return

        if count == 0:
            self.stdout.write(_("No abandoned chat sessions to clean up."))
            return

        now = timezone.now()
        cleaned = 0
        for session in abandoned_sessions:
            session.status = ChatSession.Status.ABANDONED
            session.ended_at = now
            session.save(update_fields=["status", "ended_at", "updated_at"])

            ticket = session.ticket
            ticket.chat_ended_at = now
            ticket.status = Ticket.Status.CLOSED
            ticket.closed_at = now
            ticket.save(update_fields=["chat_ended_at", "status", "closed_at", "updated_at"])
            cleaned += 1

        self.stdout.write(
            self.style.SUCCESS(
                _("Marked %(count)d chat sessions as abandoned (waiting > %(minutes)d min).")
                % {"count": cleaned, "minutes": minutes}
            )
        )
