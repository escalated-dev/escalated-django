from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from escalated.conf import get_setting


class Command(BaseCommand):
    help = (
        "Run the cron schedules of SDK plugins that are due this minute (UTC), "
        "through the plugin runtime. Schedule it every minute."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--at",
            default=None,
            help="The minute to run, as an ISO 8601 time such as 2026-10-29T09:00:00Z (default: now).",
        )

    def handle(self, *args, **options):
        at = options.get("at")
        if at:
            try:
                now = datetime.fromisoformat(at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise CommandError("--at must be a time, such as 2026-10-29T09:00:00Z.") from exc
        else:
            now = datetime.now(timezone.utc)

        if not get_setting("SDK_ENABLED"):
            self.stdout.write("SDK plugins are off (ESCALATED['SDK_ENABLED']); no plugin cron ran.")
            return

        from escalated.bridge.plugin_bridge import get_bridge

        ran = get_bridge().run_due_cron(now)
        self.stdout.write(self.style.SUCCESS(f"Ran {ran} plugin cron schedule(s)."))
