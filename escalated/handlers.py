import logging

from django.dispatch import receiver
from django.utils import timezone

from escalated.signals import (
    ticket_created,
    ticket_updated,
    ticket_status_changed,
    ticket_assigned,
    ticket_priority_changed,
    reply_created,
    sla_breached,
    ticket_resolved,
    ticket_closed,
    ticket_escalated,
)

logger = logging.getLogger("escalated")


@receiver(ticket_created)
def on_ticket_created(sender, ticket, user, **kwargs):
    """Attach default SLA policy and send notification when a ticket is created."""
    from escalated.models import SlaPolicy, TicketActivity
    from escalated.services.sla_service import SlaService
    from escalated.services.notification_service import NotificationService

    # Attach default SLA policy if none set
    if not ticket.sla_policy:
        default_policy = SlaPolicy.objects.filter(
            is_default=True, is_active=True
        ).first()
        if default_policy:
            ticket.sla_policy = default_policy
            SlaService.apply_sla_deadlines(ticket)
            ticket.save(
                update_fields=[
                    "sla_policy",
                    "first_response_due_at",
                    "resolution_due_at",
                    "updated_at",
                ]
            )

    # Log activity
    TicketActivity.objects.create(
        ticket=ticket,
        type=TicketActivity.ActivityType.CREATED,
        properties={"subject": ticket.subject, "priority": ticket.priority},
    )

    # Send notification
    NotificationService.notify_ticket_created(ticket)
    logger.info(f"Ticket {ticket.reference} created by user {user}")


@receiver(reply_created)
def on_reply_created(sender, reply, ticket, user, **kwargs):
    """Record first response time and send notification when a reply is added."""
    from escalated.models import TicketActivity
    from escalated.services.notification_service import NotificationService

    # Record first response if this is the first agent reply
    if (
        not ticket.first_response_at
        and ticket.assigned_to
        and user == ticket.assigned_to
    ):
        ticket.first_response_at = timezone.now()
        ticket.save(update_fields=["first_response_at", "updated_at"])

    # Log activity
    TicketActivity.objects.create(
        ticket=ticket,
        type=TicketActivity.ActivityType.REPLY_ADDED,
        properties={"reply_id": reply.id, "is_internal": reply.is_internal_note},
    )

    # Send notification
    if not reply.is_internal_note:
        NotificationService.notify_reply_added(ticket, reply)

    logger.info(f"Reply added to ticket {ticket.reference} by user {user}")


@receiver(ticket_status_changed)
def on_status_changed(sender, ticket, user, old_status, new_status, **kwargs):
    """Log status change activity and send notification."""
    from escalated.models import TicketActivity
    from escalated.services.notification_service import NotificationService

    TicketActivity.objects.create(
        ticket=ticket,
        type=TicketActivity.ActivityType.STATUS_CHANGED,
        properties={"old_status": old_status, "new_status": new_status},
    )

    NotificationService.notify_status_changed(ticket, old_status, new_status)
    logger.info(
        f"Ticket {ticket.reference} status changed: {old_status} -> {new_status}"
    )


@receiver(ticket_assigned)
def on_ticket_assigned(sender, ticket, user, agent, **kwargs):
    """Log assignment activity and notify the assigned agent."""
    from escalated.models import TicketActivity
    from escalated.services.notification_service import NotificationService

    TicketActivity.objects.create(
        ticket=ticket,
        type=TicketActivity.ActivityType.ASSIGNED,
        properties={
            "agent_id": agent.id,
            "agent_name": getattr(agent, "get_full_name", lambda: str(agent))(),
        },
    )

    NotificationService.notify_ticket_assigned(ticket, agent)
    logger.info(f"Ticket {ticket.reference} assigned to {agent}")


@receiver(sla_breached)
def on_sla_breached(sender, ticket, breach_type, **kwargs):
    """Log SLA breach and send notification."""
    from escalated.models import TicketActivity
    from escalated.services.notification_service import NotificationService

    TicketActivity.objects.create(
        ticket=ticket,
        type=TicketActivity.ActivityType.SLA_BREACHED,
        properties={"breach_type": breach_type},
    )

    NotificationService.notify_sla_breach(ticket, breach_type)
    logger.warning(f"SLA breached on ticket {ticket.reference}: {breach_type}")


@receiver(ticket_resolved)
def on_ticket_resolved(sender, ticket, user, **kwargs):
    """Send resolved notification."""
    from escalated.services.notification_service import NotificationService

    NotificationService.notify_ticket_resolved(ticket)
    logger.info(f"Ticket {ticket.reference} resolved by {user}")


@receiver(ticket_closed)
def on_ticket_closed(sender, ticket, user, **kwargs):
    """Log ticket closed."""
    logger.info(f"Ticket {ticket.reference} closed by {user}")


@receiver(ticket_escalated)
def on_ticket_escalated(sender, ticket, user, reason, **kwargs):
    """Log escalation and send notification."""
    from escalated.models import TicketActivity
    from escalated.services.notification_service import NotificationService

    TicketActivity.objects.create(
        ticket=ticket,
        type=TicketActivity.ActivityType.ESCALATED,
        properties={"reason": reason},
    )

    NotificationService.notify_ticket_escalated(ticket, reason)
    logger.warning(f"Ticket {ticket.reference} escalated: {reason}")


@receiver(ticket_updated)
def on_ticket_updated(sender, ticket, user, changes, **kwargs):
    """Log ticket update and fire webhook."""
    from escalated.services.notification_service import NotificationService

    NotificationService._fire_webhook("ticket.updated", {
        "ticket_id": ticket.pk,
        "reference": ticket.reference,
        "changes": {k: v["new"] for k, v in changes.items()},
    })
    logger.info(f"Ticket {ticket.reference} updated: {list(changes.keys())}")


@receiver(ticket_priority_changed)
def on_ticket_priority_changed(sender, ticket, user, old_priority, new_priority, **kwargs):
    """Log priority change and fire webhook."""
    from escalated.services.notification_service import NotificationService

    NotificationService._fire_webhook("ticket.priority_changed", {
        "ticket_id": ticket.pk,
        "reference": ticket.reference,
        "old_priority": old_priority,
        "new_priority": new_priority,
    })
    logger.info(
        f"Ticket {ticket.reference} priority changed: {old_priority} -> {new_priority}"
    )
