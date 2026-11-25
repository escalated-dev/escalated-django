from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from escalated.services.workflow_engine import WorkflowEngine


class Command(BaseCommand):
    help = "Run the workflow actions whose delay has passed (escalated-laravel's escalated:process-delayed-actions)."

    def handle(self, *args, **options):
        processed = WorkflowEngine().process_delayed_actions()
        self.stdout.write(self.style.SUCCESS(_("Processed %(count)d delayed actions.") % {"count": processed}))
