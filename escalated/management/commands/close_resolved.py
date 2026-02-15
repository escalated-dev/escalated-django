from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.translation import gettext as _

from escalated.conf import get_setting
from escalated.models import Ticket


class Command(BaseCommand):
    help = "Auto-close tickets that have been resolved for a configurable number of days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help=_("Days after resolution to auto-close (overrides setting)"),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_("Show what would be closed without making changes"),
        )

    def handle(self, *args, **options):
        days = options["days"] or get_setting("AUTO_CLOSE_RESOLVED_AFTER_DAYS")
        dry_run = options["dry_run"]

        threshold = timezone.now() - timedelta(days=days)

        stale_tickets = Ticket.objects.filter(
            status=Ticket.Status.RESOLVED,
            resolved_at__isnull=False,
            resolved_at__lt=threshold,
        )

        count = stale_tickets.count()

        if dry_run:
            self.stdout.write(
                _("[DRY RUN] Would close %(count)d tickets resolved more than %(days)d days ago.")
                % {"count": count, "days": days}
            )
            for ticket in stale_tickets[:20]:
                self.stdout.write(f"  - {ticket.reference}: {ticket.subject}")
            return

        if count == 0:
            self.stdout.write(_("No resolved tickets to auto-close."))
            return

        now = timezone.now()
        updated = stale_tickets.update(
            status=Ticket.Status.CLOSED,
            closed_at=now,
        )

        self.stdout.write(
            self.style.SUCCESS(
                _("Auto-closed %(count)d tickets that were resolved more than %(days)d days ago.")
                % {"count": updated, "days": days}
            )
        )
