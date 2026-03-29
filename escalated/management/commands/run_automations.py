from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from escalated.services.automation_runner import AutomationRunner


class Command(BaseCommand):
    help = "Run time-based automations against open tickets"

    def handle(self, *args, **options):
        self.stdout.write(_("Running automations against open tickets..."))

        runner = AutomationRunner()
        count = runner.run()

        self.stdout.write(
            self.style.SUCCESS(
                _("Automations complete: %(count)d ticket(s) affected") % {"count": count}
            )
        )
