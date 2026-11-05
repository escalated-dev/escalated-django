"""
Signal receivers for the agent panel's data (ADR 2026-11-05-agent-panel-data):
customer activity for unread markers, and the agents' in-app notifications.
The agent who caused an event is never notified of it. A failure here never
fails the action that raised it.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from escalated.services import agent_panel
from escalated.signals import chat_transferred, sla_breached, sla_warning, ticket_assigned

logger = logging.getLogger("escalated.agent_panel")


def _safely(work, *args, **kwargs):
    try:
        work(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Agent panel update failed: %s", exc)


@receiver(post_save, sender="escalated.Reply", dispatch_uid="escalated_agent_panel_reply")
def on_reply_saved(sender, instance, created, **kwargs):
    """A customer-side public reply is unread activity and notifies the assignee and followers."""
    if not created:
        return
    _safely(agent_panel.record_reply_activity, instance)
    _safely(_notify_reply, instance)
    _safely(_process_mentions, instance)


def _process_mentions(reply):
    """@mentions in an agent's reply or note (escalated-laravel's MentionService); a customer's mention nobody."""
    from escalated.services.mention_service import MentionService
    from escalated.support.import_context import ImportContext

    if ImportContext.is_importing() or not reply.body or agent_panel.is_customer_side(reply):
        return
    MentionService().process_mentions(reply)


def _notify_reply(reply):
    from escalated.support.import_context import ImportContext

    if ImportContext.is_importing() or not agent_panel.is_customer_side(reply):
        return
    ticket = reply.ticket
    recipients = []
    if ticket.assigned_to_id:
        recipients.append(ticket.assigned_to_id)
    recipients += list(ticket.followers.values_list("pk", flat=True))
    for agent_id in dict.fromkeys(recipients):
        agent_panel.notify(agent_id, "ticket_reply", ticket, causer_id=reply.author_id)


@receiver(ticket_assigned, dispatch_uid="escalated_agent_panel_assigned")
def on_ticket_assigned(sender, ticket, user, agent, **kwargs):
    _safely(
        agent_panel.notify,
        getattr(agent, "pk", None),
        "ticket_assigned",
        ticket,
        causer_id=getattr(user, "pk", None),
    )


@receiver(sla_warning, dispatch_uid="escalated_agent_panel_sla_warning")
def on_sla_warning(sender, ticket, warning_type=None, **kwargs):
    _safely(agent_panel.notify, ticket.assigned_to_id, "sla_warning", ticket, {"sla_type": str(warning_type or "")})


@receiver(sla_breached, dispatch_uid="escalated_agent_panel_sla_breached")
def on_sla_breached(sender, ticket, breach_type=None, **kwargs):
    _safely(agent_panel.notify, ticket.assigned_to_id, "sla_breached", ticket, {"sla_type": str(breach_type or "")})


@receiver(chat_transferred, dispatch_uid="escalated_agent_panel_chat_transferred")
def on_chat_transferred(sender, session, ticket, from_agent=None, to_agent=None, **kwargs):
    _safely(
        agent_panel.notify,
        getattr(to_agent, "pk", None),
        "chat_transferred",
        ticket,
        {"session_id": getattr(session, "pk", None)},
        causer_id=getattr(from_agent, "pk", None),
    )
