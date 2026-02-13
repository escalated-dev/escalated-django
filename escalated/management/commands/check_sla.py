from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from escalated.services.sla_service import SlaService


class Command(BaseCommand):
    help = "Check all open tickets for SLA breaches and send warnings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--warning-threshold",
            type=int,
            default=30,
            help=_("Minutes before SLA deadline to trigger warning (default: 30)"),
        )

    def handle(self, *args, **options):
        self.stdout.write(_("Checking SLA deadlines for all open tickets..."))

        breached_count, warned_count = SlaService.check_all_tickets()

        self.stdout.write(
            self.style.SUCCESS(
                _("SLA check complete: %(breached)d breaches detected, %(warned)d warnings sent.")
                % {"breached": breached_count, "warned": warned_count}
            )
        )
