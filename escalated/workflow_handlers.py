"""
Wire the WorkflowEngine to the Django signal stream.

The engine was previously defined but orphaned — nothing invoked
process_event. Workflows configured in the admin UI didn't fire on
ticket events. This module adds @receiver handlers that bridge
each relevant signal to WorkflowEngine.process_event.

Mirrors the pattern used in:
  - escalated-nestjs WorkflowListener
  - escalated-laravel ProcessWorkflows
  - escalated-rails Services::WorkflowSubscriber

Engine errors are caught and warn-logged so a misconfigured
workflow never blocks the signal chain that may have listeners
downstream.
"""
import logging

from django.dispatch import receiver

from escalated.signals import (
    reply_created,
    sla_breached,
    sla_warning,
    ticket_assigned,
    ticket_created,
    ticket_escalated,
    ticket_priority_changed,
    ticket_status_changed,
    ticket_updated,
)
from escalated.support.import_context import ImportContext

logger = logging.getLogger("escalated")


def _process(trigger, ticket, **context):
    """Invoke the WorkflowEngine for one trigger + ticket; swallow errors."""
    if ImportContext.is_importing():
        return
    if ticket is None:
        return
    try:
        from escalated.services.workflow_engine import WorkflowEngine

        WorkflowEngine().process_event(trigger, ticket, context or None)
    except Exception as exc:  # pragma: no cover — defensive log-only path
        logger.warning(
            "WorkflowEngine.%s failed for ticket %s: %s",
            trigger,
            getattr(ticket, "pk", "?"),
            exc,
        )


@receiver(ticket_created)
def _workflow_ticket_created(sender, ticket, user=None, **kwargs):
    _process("ticket.created", ticket, user=user)


@receiver(ticket_updated)
def _workflow_ticket_updated(sender, ticket, user=None, changes=None, **kwargs):
    _process("ticket.updated", ticket, user=user, changes=changes)


@receiver(ticket_status_changed)
def _workflow_status_changed(sender, ticket, old_status=None, new_status=None, **kwargs):
    _process(
        "ticket.status_changed",
        ticket,
        old_status=old_status,
        new_status=new_status,
    )


@receiver(ticket_assigned)
def _workflow_ticket_assigned(sender, ticket, agent=None, **kwargs):
    _process("ticket.assigned", ticket, agent=agent)


@receiver(ticket_priority_changed)
def _workflow_priority_changed(sender, ticket, old_priority=None, new_priority=None, **kwargs):
    _process(
        "ticket.priority_changed",
        ticket,
        old_priority=old_priority,
        new_priority=new_priority,
    )


@receiver(ticket_escalated)
def _workflow_ticket_escalated(sender, ticket, reason=None, **kwargs):
    _process("ticket.escalated", ticket, reason=reason)


@receiver(reply_created)
def _workflow_reply_created(sender, reply=None, ticket=None, **kwargs):
    _process("ticket.replied", ticket, reply=reply)


@receiver(sla_breached)
def _workflow_sla_breached(sender, ticket, breach_type=None, **kwargs):
    _process("sla.breached", ticket, breach_type=breach_type)


@receiver(sla_warning)
def _workflow_sla_warning(sender, ticket, warning_type=None, remaining=None, **kwargs):
    _process(
        "sla.warning",
        ticket,
        warning_type=warning_type,
        remaining=remaining,
    )
