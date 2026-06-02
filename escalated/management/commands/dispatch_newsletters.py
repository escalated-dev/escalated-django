"""Plan due scheduled newsletters and dispatch pending delivery batches."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from escalated.models import Newsletter
from escalated.newsletter_conf import newsletters_enabled
from escalated.services.newsletter.dispatcher import NewsletterDispatcher
from escalated.services.newsletter.planner import NewsletterPlanner


class Command(BaseCommand):
    help = "Plan scheduled newsletters whose time has come and dispatch a batch of pending deliveries."

    def handle(self, *args, **options):
        if not newsletters_enabled():
            self.stdout.write("Newsletter feature disabled — skipping.")
            return

        planner = NewsletterPlanner()
        due = Newsletter.objects.filter(status="scheduled", scheduled_at__lte=timezone.now())
        for newsletter in due:
            planner.plan(newsletter)

        NewsletterDispatcher().dispatch_batch()
        self.stdout.write(self.style.SUCCESS("Newsletter dispatch complete."))
