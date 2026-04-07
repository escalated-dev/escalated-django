import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


class AutomationRunner:
    def run(self):
        """Run all active automations against open tickets. Returns count of affected tickets."""
        from escalated.models import Automation

        automations = Automation.objects.active()
        affected = 0

        for automation in automations:
            tickets = self._find_matching_tickets(automation)
            for ticket in tickets:
                self._execute_actions(automation, ticket)
                affected += 1
            automation.last_run_at = timezone.now()
            automation.save(update_fields=["last_run_at", "updated_at"])

        return affected

    def _find_matching_tickets(self, automation):

        from escalated.models import Ticket

        query = Ticket.objects.filter(
            status__in=["open", "in_progress", "waiting_on_customer", "waiting_on_agent", "escalated", "reopened"]
        )

        for condition in automation.conditions or []:
            field = condition.get("field", "")
            operator = condition.get("operator", ">")
            value = condition.get("value")

            if field == "hours_since_created":
                threshold = timezone.now() - timedelta(hours=int(value))
                op = self._resolve_operator(operator)
                query = query.filter(**{f"created_at{op}": threshold})
            elif field == "hours_since_updated":
                threshold = timezone.now() - timedelta(hours=int(value))
                op = self._resolve_operator(operator)
                query = query.filter(**{f"updated_at{op}": threshold})
            elif field == "hours_since_assigned":
                # Approximation: use updated_at where assigned_to is set
                threshold = timezone.now() - timedelta(hours=int(value))
                op = self._resolve_operator(operator)
                query = query.filter(assigned_to__isnull=False).filter(**{f"updated_at{op}": threshold})
            elif field == "status":
                query = query.filter(status=value)
            elif field == "priority":
                query = query.filter(priority=value)
            elif field == "assigned":
                if value == "unassigned":
                    query = query.filter(assigned_to__isnull=True)
                elif value == "assigned":
                    query = query.filter(assigned_to__isnull=False)
            elif field == "ticket_type":
                query = query.filter(ticket_type=value)
            elif field == "subject_contains":
                query = query.filter(subject__icontains=value)

        return query

    def _execute_actions(self, automation, ticket):
        from escalated.models import Reply, Tag, Ticket

        for action in automation.actions or []:
            action_type = action.get("type", "")
            value = action.get("value")

            try:
                if action_type == "change_status":
                    ticket.status = value
                    ticket.save(update_fields=["status", "updated_at"])
                elif action_type == "assign":
                    ticket.assigned_to_id = int(value)
                    ticket.save(update_fields=["assigned_to_id", "updated_at"])
                elif action_type == "add_tag":
                    tag = Tag.objects.filter(name=value).first()
                    if tag:
                        ticket.tags.add(tag)
                elif action_type == "change_priority":
                    ticket.priority = value
                    ticket.save(update_fields=["priority", "updated_at"])
                elif action_type == "add_note":
                    Reply.objects.create(
                        ticket=ticket,
                        body=value,
                        is_internal_note=True,
                        is_pinned=False,
                        metadata={"system_note": True, "automation_id": automation.pk},
                    )
                elif action_type == "set_ticket_type":
                    valid_types = [choice.value for choice in Ticket.TicketType]
                    if value in valid_types:
                        ticket.ticket_type = value
                        ticket.save(update_fields=["ticket_type", "updated_at"])
            except Exception as e:
                logger.warning(
                    "Escalated automation action failed",
                    extra={
                        "automation_id": automation.pk,
                        "ticket_id": ticket.pk,
                        "action": action_type,
                        "error": str(e),
                    },
                )

    @staticmethod
    def _resolve_operator(operator):
        """
        Resolve a condition operator to a Django ORM lookup suffix.
        For hours_since fields, > hours means < datetime (older).
        """
        mapping = {
            ">": "__lte",  # more hours ago = earlier datetime
            ">=": "__lte",
            "<": "__gte",
            "<=": "__gte",
            "=": "",
        }
        return mapping.get(operator, "__lte")
