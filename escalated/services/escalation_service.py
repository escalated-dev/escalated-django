import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from escalated.models import EscalationRule, Ticket, TicketActivity
from escalated.signals import department_changed, ticket_assigned, ticket_escalated, ticket_priority_changed

logger = logging.getLogger("escalated")

User = get_user_model()


class EscalationService:
    """
    Evaluates escalation rules against tickets and performs configured actions.
    """

    @staticmethod
    def evaluate_all():
        """
        Evaluate all active escalation rules against all open tickets.
        Called by the evaluate_escalations management command.
        """
        rules = EscalationRule.objects.filter(is_active=True).order_by("order")
        open_tickets = Ticket.objects.open().select_related("assigned_to", "department", "sla_policy")

        actions_taken = 0
        for rule in rules:
            for ticket in open_tickets:
                if EscalationService._matches_conditions(ticket, rule):
                    if EscalationService._execute_actions(ticket, rule):
                        actions_taken += 1

        return actions_taken

    @staticmethod
    def evaluate_ticket(ticket):
        """Evaluate escalation rules for a single ticket."""
        rules = EscalationRule.objects.filter(is_active=True).order_by("order")
        actions_taken = 0

        for rule in rules:
            if EscalationService._matches_conditions(ticket, rule):
                if EscalationService._execute_actions(ticket, rule):
                    actions_taken += 1

        return actions_taken

    @staticmethod
    def _matches_conditions(ticket, rule):
        """
        Check whether a ticket matches the conditions defined in an
        escalation rule.
        """
        conditions = rule.conditions or {}

        # Check trigger type first
        if rule.trigger_type == EscalationRule.TriggerType.SLA_BREACH:
            if not (ticket.sla_first_response_breached or ticket.sla_resolution_breached):
                return False

        elif rule.trigger_type == EscalationRule.TriggerType.NO_RESPONSE:
            hours = conditions.get("no_response_hours", 24)
            threshold = timezone.now() - timedelta(hours=hours)
            if ticket.created_at > threshold:
                return False
            if ticket.first_response_at:
                return False

        elif rule.trigger_type == EscalationRule.TriggerType.TIME_BASED:
            hours = conditions.get("hours_since_creation", 48)
            threshold = timezone.now() - timedelta(hours=hours)
            if ticket.created_at > threshold:
                return False

        elif rule.trigger_type == EscalationRule.TriggerType.PRIORITY_CHANGE:
            required_priority = conditions.get("priority")
            if required_priority and ticket.priority != required_priority:
                return False

        # Check additional conditions
        if "status" in conditions:
            allowed_statuses = conditions["status"]
            if isinstance(allowed_statuses, str):
                allowed_statuses = [allowed_statuses]
            if ticket.status not in allowed_statuses:
                return False

        if "priority" in conditions:
            allowed_priorities = conditions["priority"]
            if isinstance(allowed_priorities, str):
                allowed_priorities = [allowed_priorities]
            if ticket.priority not in allowed_priorities:
                return False

        if "department_id" in conditions:
            if ticket.department_id != conditions["department_id"]:
                return False

        if "unassigned_only" in conditions and conditions["unassigned_only"]:
            if ticket.assigned_to is not None:
                return False

        return True

    @staticmethod
    def _execute_actions(ticket, rule):
        """
        Execute the actions defined in an escalation rule on a ticket.
        Returns True if any action was taken.
        """
        actions = rule.actions or {}
        # Signals for each change, sent once the ticket is saved. The driver saves
        # before it signals too, so receivers read the ticket as it is stored.
        pending_signals = []

        # Change priority
        if "set_priority" in actions:
            new_priority = actions["set_priority"]
            if ticket.priority != new_priority:
                old_priority = ticket.priority
                ticket.priority = new_priority
                pending_signals.append(
                    (ticket_priority_changed, {"old_priority": old_priority, "new_priority": new_priority})
                )
                logger.info(
                    f"Escalation rule '{rule.name}' changed priority on "
                    f"{ticket.reference}: {old_priority} -> {new_priority}"
                )

        # Escalate status
        if actions.get("escalate", False):
            if ticket.status != Ticket.Status.ESCALATED:
                ticket.status = Ticket.Status.ESCALATED
                pending_signals.append((ticket_escalated, {"reason": f"Escalation rule: {rule.name}"}))

        # Assign to specific agent
        if "assign_to_id" in actions:
            try:
                agent = User.objects.get(pk=actions["assign_to_id"])
                if ticket.assigned_to != agent:
                    ticket.assigned_to = agent
                    pending_signals.append((ticket_assigned, {"agent": agent}))
                    logger.info(f"Escalation rule '{rule.name}' assigned {ticket.reference} to {agent}")
            except User.DoesNotExist:
                logger.warning(f"Escalation rule '{rule.name}' references non-existent user {actions['assign_to_id']}")

        # Change department
        if "department_id" in actions:
            from escalated.models import Department

            try:
                dept = Department.objects.get(pk=actions["department_id"])
                if ticket.department != dept:
                    old_department = ticket.department
                    ticket.department = dept
                    pending_signals.append(
                        (department_changed, {"old_department": old_department, "new_department": dept})
                    )
            except Department.DoesNotExist:
                logger.warning(
                    f"Escalation rule '{rule.name}' references non-existent department {actions['department_id']}"
                )

        acted = bool(pending_signals)
        if acted:
            ticket.save()
            TicketActivity.objects.create(
                ticket=ticket,
                type=TicketActivity.ActivityType.ESCALATED,
                properties={
                    "rule_id": rule.pk,
                    "rule_name": rule.name,
                    "actions": actions,
                },
            )

            for signal, kwargs in pending_signals:
                signal.send(sender=Ticket, ticket=ticket, user=None, **kwargs)

        return acted
