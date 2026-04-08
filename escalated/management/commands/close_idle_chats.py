from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.translation import gettext as _

from escalated.models import ChatSession, Ticket


class Command(BaseCommand):
    help = "Close chat sessions that have been idle (no messages) for a configurable duration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes",
            type=int,
            default=30,
            help=_("Minutes of inactivity before closing a chat (default: 30)"),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_("Show what would be closed without making changes"),
        )

    def handle(self, *args, **options):
        minutes = options["minutes"]
        dry_run = options["dry_run"]
        threshold = timezone.now() - timedelta(minutes=minutes)

        idle_sessions = ChatSession.objects.filter(
            status=ChatSession.Status.ACTIVE,
            updated_at__lt=threshold,
        )

        count = idle_sessions.count()

        if dry_run:
            self.stdout.write(
                _("[DRY RUN] Would close %(count)d idle chat sessions (inactive > %(minutes)d min).")
                % {"count": count, "minutes": minutes}
            )
            for session in idle_sessions[:20]:
                self.stdout.write(f"  - Session {session.pk}: ticket {session.ticket.reference}")
            return

        if count == 0:
            self.stdout.write(_("No idle chat sessions to close."))
            return

        now = timezone.now()
        closed = 0
        for session in idle_sessions:
            session.status = ChatSession.Status.ENDED
            session.ended_at = now
            session.save(update_fields=["status", "ended_at", "updated_at"])

            ticket = session.ticket
            ticket.chat_ended_at = now
            ticket.status = Ticket.Status.RESOLVED
            ticket.resolved_at = now
            ticket.save(update_fields=["chat_ended_at", "status", "resolved_at", "updated_at"])
            closed += 1

        self.stdout.write(
            self.style.SUCCESS(
                _("Closed %(count)d idle chat sessions (inactive > %(minutes)d min).")
                % {"count": closed, "minutes": minutes}
            )
        )
