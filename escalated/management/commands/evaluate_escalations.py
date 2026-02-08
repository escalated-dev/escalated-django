from django.core.management.base import BaseCommand

from escalated.services.escalation_service import EscalationService


class Command(BaseCommand):
    help = "Evaluate all active escalation rules against open tickets."

    def handle(self, *args, **options):
        self.stdout.write("Evaluating escalation rules...")

        actions_taken = EscalationService.evaluate_all()

        self.stdout.write(
            self.style.SUCCESS(
                f"Escalation evaluation complete: {actions_taken} actions taken."
            )
        )
