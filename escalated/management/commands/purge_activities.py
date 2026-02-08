from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from escalated.models import TicketActivity


class Command(BaseCommand):
    help = "Purge old ticket activity logs beyond a retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Delete activities older than this many days (default: 90)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be purged without making changes",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]

        threshold = timezone.now() - timedelta(days=days)
        old_activities = TicketActivity.objects.filter(created_at__lt=threshold)
        count = old_activities.count()

        if dry_run:
            self.stdout.write(
                f"[DRY RUN] Would purge {count} activities older than {days} days."
            )
            return

        if count == 0:
            self.stdout.write("No old activities to purge.")
            return

        deleted, _ = old_activities.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Purged {deleted} activity records older than {days} days."
            )
        )
