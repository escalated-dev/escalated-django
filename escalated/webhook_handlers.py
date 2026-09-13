"""
Deliver admin-configured webhooks when ticket events happen.

WebhookDispatcher.dispatch() sends an event to every active Webhook subscribed
to it and records a WebhookDelivery for each attempt. Until this module it had
no caller outside the manual "retry delivery" view, so a webhook saved on the
admin Webhooks page never received anything.

There is one receiver for every event WebhookSerializer.AVAILABLE_EVENTS
offers. Delivery runs inside the signal, as NotificationService._fire_webhook
does for ESCALATED["WEBHOOK_URL"]. A dispatcher error is logged and swallowed,
so an unreachable endpoint never undoes or interrupts the change that raised
the event. Nothing is sent while an import is running.

Payloads carry ids and plain values only: WebhookDispatcher.send() serialises
them with json.dumps and stores them in WebhookDelivery.payload.
"""

import logging

from django.dispatch import receiver

from escalated.signals import (
    department_changed,
    internal_note_added,
    reply_created,
    sla_breached,
    sla_warning,
    tag_added,
    tag_removed,
    ticket_assigned,
    ticket_closed,
    ticket_created,
    ticket_escalated,
    ticket_priority_changed,
    ticket_reopened,
    ticket_resolved,
    ticket_status_changed,
    ticket_unassigned,
    ticket_updated,
)
from escalated.support.import_context import ImportContext

logger = logging.getLogger("escalated")


def _id(obj):
    """Primary key as a JSON value. Host user models may use UUID keys."""
    pk = getattr(obj, "pk", None)
    if pk is None or isinstance(pk, int):
        return pk
    return str(pk)


def _ticket(ticket, user=None, **extra):
    return {
        "ticket_id": ticket.pk,
        "reference": ticket.reference,
        "user_id": _id(user),
        **extra,
    }


def _dispatch(event, payload):
    if ImportContext.is_importing():
        return
    try:
        from escalated.services.webhook_dispatcher import WebhookDispatcher

        WebhookDispatcher().dispatch(event, payload)
    except Exception as exc:
        logger.warning("Webhook dispatch for %s failed: %s", event, exc)


@receiver(ticket_created)
def _webhook_ticket_created(sender, ticket, user=None, **kwargs):
    _dispatch(
        "ticket.created",
        _ticket(ticket, user, subject=ticket.subject, status=ticket.status, priority=ticket.priority),
    )


@receiver(ticket_updated)
def _webhook_ticket_updated(sender, ticket, user=None, changes=None, **kwargs):
    new_values = {field: change["new"] for field, change in (changes or {}).items()}
    _dispatch("ticket.updated", _ticket(ticket, user, changes=new_values))


@receiver(ticket_status_changed)
def _webhook_status_changed(sender, ticket, user=None, old_status=None, new_status=None, **kwargs):
    _dispatch("ticket.status_changed", _ticket(ticket, user, old_status=old_status, new_status=new_status))


@receiver(ticket_resolved)
def _webhook_ticket_resolved(sender, ticket, user=None, **kwargs):
    _dispatch("ticket.resolved", _ticket(ticket, user))


@receiver(ticket_closed)
def _webhook_ticket_closed(sender, ticket, user=None, **kwargs):
    _dispatch("ticket.closed", _ticket(ticket, user))


@receiver(ticket_reopened)
def _webhook_ticket_reopened(sender, ticket, user=None, **kwargs):
    _dispatch("ticket.reopened", _ticket(ticket, user))


@receiver(ticket_assigned)
def _webhook_ticket_assigned(sender, ticket, user=None, agent=None, **kwargs):
    _dispatch("ticket.assigned", _ticket(ticket, user, agent_id=_id(agent)))


@receiver(ticket_unassigned)
def _webhook_ticket_unassigned(sender, ticket, user=None, previous_agent=None, **kwargs):
    _dispatch("ticket.unassigned", _ticket(ticket, user, previous_agent_id=_id(previous_agent)))


@receiver(ticket_escalated)
def _webhook_ticket_escalated(sender, ticket, user=None, reason=None, **kwargs):
    _dispatch("ticket.escalated", _ticket(ticket, user, reason=reason))


@receiver(ticket_priority_changed)
def _webhook_priority_changed(sender, ticket, user=None, old_priority=None, new_priority=None, **kwargs):
    _dispatch(
        "ticket.priority_changed",
        _ticket(ticket, user, old_priority=old_priority, new_priority=new_priority),
    )


@receiver(department_changed)
def _webhook_department_changed(sender, ticket, user=None, old_department=None, new_department=None, **kwargs):
    _dispatch(
        "ticket.department_changed",
        _ticket(ticket, user, old_department_id=_id(old_department), new_department_id=_id(new_department)),
    )


@receiver(reply_created)
def _webhook_reply_created(sender, reply, ticket, user=None, **kwargs):
    _dispatch("reply.created", _ticket(ticket, user, reply_id=reply.pk, is_internal=reply.is_internal_note))


@receiver(internal_note_added)
def _webhook_internal_note_added(sender, reply, ticket, user=None, **kwargs):
    _dispatch("internal_note.added", _ticket(ticket, user, reply_id=reply.pk))


@receiver(sla_breached)
def _webhook_sla_breached(sender, ticket, breach_type=None, **kwargs):
    _dispatch("sla.breached", _ticket(ticket, breach_type=breach_type))


@receiver(sla_warning)
def _webhook_sla_warning(sender, ticket, warning_type=None, remaining=None, **kwargs):
    remaining_seconds = int(remaining.total_seconds()) if remaining is not None else None
    _dispatch("sla.warning", _ticket(ticket, warning_type=warning_type, remaining_seconds=remaining_seconds))


@receiver(tag_added)
def _webhook_tag_added(sender, tag, ticket, user=None, **kwargs):
    _dispatch("tag.added", _ticket(ticket, user, tag_id=tag.pk, tag_name=tag.name))


@receiver(tag_removed)
def _webhook_tag_removed(sender, tag, ticket, user=None, **kwargs):
    _dispatch("tag.removed", _ticket(ticket, user, tag_id=tag.pk, tag_name=tag.name))
