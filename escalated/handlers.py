import logging

from django.dispatch import receiver
from django.utils import timezone

from escalated.signals import (
    reply_created,
    sla_breached,
    ticket_assigned,
    ticket_closed,
    ticket_created,
    ticket_escalated,
    ticket_priority_changed,
    ticket_resolved,
    ticket_status_changed,
    ticket_updated,
)
from escalated.support.import_context import ImportContext

logger = logging.getLogger("escalated")


def _bridge_dispatch(hook: str, event: dict) -> None:
    """
    Fire-and-forget dispatch to the SDK plugin bridge.

    Silently no-ops when the bridge has not booted (Node.js not installed,
    SDK_ENABLED not set, etc.).
    """
    try:
        from escalated.bridge.plugin_bridge import get_bridge

        bridge = get_bridge()
        if bridge.is_booted():
            bridge.dispatch_action(hook, event)
    except Exception as exc:
        logger.debug("SDK bridge dispatch for '%s' failed: %s", hook, exc)


@receiver(ticket_created)
def on_ticket_created(sender, ticket, user, **kwargs):
    """Attach default SLA policy and send notification when a ticket is created."""
    if ImportContext.is_importing():
        return

    from escalated.models import SlaPolicy, TicketActivity
    from escalated.services.notification_service import NotificationService
    from escalated.services.sla_service import SlaService

    # Attach default SLA policy if none set
    if not ticket.sla_policy:
        default_policy = SlaPolicy.objects.filter(is_default=True, is_active=True).first()
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

    # Dual dispatch to SDK plugin bridge
    _bridge_dispatch(
        "ticket.created",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "subject": ticket.subject,
            "status": ticket.status,
            "priority": ticket.priority,
            "user_id": getattr(user, "pk", None),
        },
    )


@receiver(reply_created)
def on_reply_created(sender, reply, ticket, user, **kwargs):
    """Record first response time and send notification when a reply is added."""
    if ImportContext.is_importing():
        return

    from escalated.models import TicketActivity
    from escalated.services.notification_service import NotificationService

    # Record first response if this is the first agent reply
    if not ticket.first_response_at and ticket.assigned_to and user == ticket.assigned_to:
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

    # Dual dispatch to SDK plugin bridge
    _bridge_dispatch(
        "reply.created",
        {
            "reply_id": reply.pk,
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "is_internal": reply.is_internal_note,
            "user_id": getattr(user, "pk", None),
        },
    )


@receiver(ticket_status_changed)
def on_status_changed(sender, ticket, user, old_status, new_status, **kwargs):
    """Log status change activity and send notification."""
    if ImportContext.is_importing():
        return

    from escalated.models import TicketActivity
    from escalated.services.notification_service import NotificationService

    TicketActivity.objects.create(
        ticket=ticket,
        type=TicketActivity.ActivityType.STATUS_CHANGED,
        properties={"old_status": old_status, "new_status": new_status},
    )

    NotificationService.notify_status_changed(ticket, old_status, new_status)
    logger.info(f"Ticket {ticket.reference} status changed: {old_status} -> {new_status}")

    # Dual dispatch to SDK plugin bridge
    _bridge_dispatch(
        "ticket.status_changed",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "old_status": old_status,
            "new_status": new_status,
            "user_id": getattr(user, "pk", None),
        },
    )


@receiver(ticket_assigned)
def on_ticket_assigned(sender, ticket, user, agent, **kwargs):
    """Log assignment activity and notify the assigned agent."""
    if ImportContext.is_importing():
        return

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

    # Dual dispatch to SDK plugin bridge
    _bridge_dispatch(
        "ticket.assigned",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "agent_id": agent.pk,
            "user_id": getattr(user, "pk", None),
        },
    )


@receiver(sla_breached)
def on_sla_breached(sender, ticket, breach_type, **kwargs):
    """Log SLA breach and send notification."""
    if ImportContext.is_importing():
        return

    from escalated.models import TicketActivity
    from escalated.services.notification_service import NotificationService

    TicketActivity.objects.create(
        ticket=ticket,
        type=TicketActivity.ActivityType.SLA_BREACHED,
        properties={"breach_type": breach_type},
    )

    NotificationService.notify_sla_breach(ticket, breach_type)
    logger.warning(f"SLA breached on ticket {ticket.reference}: {breach_type}")

    # Dual dispatch to SDK plugin bridge
    _bridge_dispatch(
        "sla.breached",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "breach_type": breach_type,
        },
    )


@receiver(ticket_resolved)
def on_ticket_resolved(sender, ticket, user, **kwargs):
    """Send resolved notification."""
    if ImportContext.is_importing():
        return

    from escalated.services.notification_service import NotificationService

    NotificationService.notify_ticket_resolved(ticket)
    logger.info(f"Ticket {ticket.reference} resolved by {user}")

    # Dual dispatch to SDK plugin bridge
    _bridge_dispatch(
        "ticket.resolved",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "user_id": getattr(user, "pk", None),
        },
    )


@receiver(ticket_closed)
def on_ticket_closed(sender, ticket, user, **kwargs):
    """Log ticket closed."""
    if ImportContext.is_importing():
        return

    logger.info(f"Ticket {ticket.reference} closed by {user}")

    # Dual dispatch to SDK plugin bridge
    _bridge_dispatch(
        "ticket.closed",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "user_id": getattr(user, "pk", None),
        },
    )


@receiver(ticket_escalated)
def on_ticket_escalated(sender, ticket, user, reason, **kwargs):
    """Log escalation and send notification."""
    if ImportContext.is_importing():
        return

    from escalated.models import TicketActivity
    from escalated.services.notification_service import NotificationService

    TicketActivity.objects.create(
        ticket=ticket,
        type=TicketActivity.ActivityType.ESCALATED,
        properties={"reason": reason},
    )

    NotificationService.notify_ticket_escalated(ticket, reason)
    logger.warning(f"Ticket {ticket.reference} escalated: {reason}")

    # Dual dispatch to SDK plugin bridge
    _bridge_dispatch(
        "ticket.escalated",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "reason": reason,
            "user_id": getattr(user, "pk", None),
        },
    )


@receiver(ticket_updated)
def on_ticket_updated(sender, ticket, user, changes, **kwargs):
    """Log ticket update and fire webhook."""
    if ImportContext.is_importing():
        return

    from escalated.services.notification_service import NotificationService

    NotificationService._fire_webhook(
        "ticket.updated",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "changes": {k: v["new"] for k, v in changes.items()},
        },
    )
    logger.info(f"Ticket {ticket.reference} updated: {list(changes.keys())}")

    # Dual dispatch to SDK plugin bridge
    _bridge_dispatch(
        "ticket.updated",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "changes": {k: v["new"] for k, v in changes.items()},
            "user_id": getattr(user, "pk", None),
        },
    )


@receiver(ticket_priority_changed)
def on_ticket_priority_changed(sender, ticket, user, old_priority, new_priority, **kwargs):
    """Log priority change and fire webhook."""
    if ImportContext.is_importing():
        return

    from escalated.services.notification_service import NotificationService

    NotificationService._fire_webhook(
        "ticket.priority_changed",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "old_priority": old_priority,
            "new_priority": new_priority,
        },
    )
    logger.info(f"Ticket {ticket.reference} priority changed: {old_priority} -> {new_priority}")

    # Dual dispatch to SDK plugin bridge
    _bridge_dispatch(
        "ticket.priority_changed",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "old_priority": old_priority,
            "new_priority": new_priority,
            "user_id": getattr(user, "pk", None),
        },
    )
