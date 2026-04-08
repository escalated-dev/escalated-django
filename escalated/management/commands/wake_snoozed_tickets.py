from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from escalated.models import Ticket


class Command(BaseCommand):
    help = "Unsnooze tickets whose snooze period has expired."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_("Show what would be unsnoozed without making changes"),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        expired = Ticket.objects.snooze_expired()
        count = expired.count()

        if dry_run:
            self.stdout.write(_("[DRY RUN] Would unsnooze %(count)d tickets.") % {"count": count})
            for ticket in expired[:20]:
                self.stdout.write(f"  - {ticket.reference}: snoozed_until={ticket.snoozed_until}")
            return

        if count == 0:
            self.stdout.write(_("No snoozed tickets to wake."))
            return

        woken = 0
        for ticket in expired:
            ticket.unsnooze()
            woken += 1

        self.stdout.write(self.style.SUCCESS(_("Unsnoozed %(count)d tickets.") % {"count": woken}))
