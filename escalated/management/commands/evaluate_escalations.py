from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from escalated.services.escalation_service import EscalationService


class Command(BaseCommand):
    help = "Evaluate all active escalation rules against open tickets."

    def handle(self, *args, **options):
        self.stdout.write(_("Evaluating escalation rules..."))

        actions_taken = EscalationService.evaluate_all()

        self.stdout.write(
            self.style.SUCCESS(
                _("Escalation evaluation complete: %(count)d actions taken.")
                % {"count": actions_taken}
            )
        )
