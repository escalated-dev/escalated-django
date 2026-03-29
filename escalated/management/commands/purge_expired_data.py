from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from escalated.models import ApiToken, ImportJob, WebhookDelivery


class Command(BaseCommand):
    help = "Purge expired API tokens, old webhook deliveries, and stale import jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Delete webhook deliveries older than this many days (default: 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be purged without making changes.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        now = timezone.now()
        threshold = now - timedelta(days=days)
        total_purged = 0

        # 1. Expired API tokens
        expired_tokens = ApiToken.objects.filter(expires_at__lt=now, expires_at__isnull=False)
        token_count = expired_tokens.count()

        # 2. Old webhook deliveries
        old_deliveries = WebhookDelivery.objects.filter(created_at__lt=threshold)
        delivery_count = old_deliveries.count()

        # 3. Stale import jobs (failed/pending > 7 days)
        stale_threshold = now - timedelta(days=7)
        stale_imports = ImportJob.objects.filter(
            status__in=["pending", "failed"],
            created_at__lt=stale_threshold,
        )
        import_count = stale_imports.count()

        if dry_run:
            self.stdout.write(
                f"[DRY RUN] Would purge: "
                f"{token_count} expired tokens, "
                f"{delivery_count} webhook deliveries (>{days}d), "
                f"{import_count} stale import jobs."
            )
            return

        if token_count:
            deleted, _ = expired_tokens.delete()
            total_purged += deleted
            self.stdout.write(f"Purged {deleted} expired API tokens.")

        if delivery_count:
            deleted, _ = old_deliveries.delete()
            total_purged += deleted
            self.stdout.write(f"Purged {deleted} webhook deliveries older than {days} days.")

        if import_count:
            deleted, _ = stale_imports.delete()
            total_purged += deleted
            self.stdout.write(f"Purged {deleted} stale import jobs.")

        if total_purged == 0:
            self.stdout.write("No expired data to purge.")
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Purge complete: {total_purged} total records removed.")
            )
