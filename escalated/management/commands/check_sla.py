from django.core.management.base import BaseCommand

from escalated.services.sla_service import SlaService


class Command(BaseCommand):
    help = "Check all open tickets for SLA breaches and send warnings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--warning-threshold",
            type=int,
            default=30,
            help="Minutes before SLA deadline to trigger warning (default: 30)",
        )

    def handle(self, *args, **options):
        self.stdout.write("Checking SLA deadlines for all open tickets...")

        breached_count, warned_count = SlaService.check_all_tickets()

        self.stdout.write(
            self.style.SUCCESS(
                f"SLA check complete: {breached_count} breaches detected, "
                f"{warned_count} warnings sent."
            )
        )
