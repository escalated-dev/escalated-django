"""
Deliver the canonical events to plugins' actions.

domain-model/plugin-contract.md: every host delivers the canonical events of
ADR 2026-10-21 (escalated/event_names.py) to active plugins' actions, under
exactly those names, after the change is committed. Legacy names are never
delivered to SDK plugins.

Python plugins receive them through ``escalated.hooks`` (only active plugins
are loaded, so only they have callbacks): ``add_action("ticket.created",
lambda payload: ...)``. SDK plugins receive them through the runtime bridge.
The payload is a dict with the subject flat at the top and again under its
own key (``ticket``, or ``reply`` and ``ticket``), snake_case and JSON-safe.

Delivery runs on commit. A plugin that raises is logged and never undoes or
interrupts the change. Nothing is delivered while an import is running.

The Python hook names documented in escalated.hook_registry
(``ticket_created`` and so on) still fire for Python plugins from
escalated.handlers.
"""

import logging
import threading

from django.db import transaction
from django.dispatch import receiver

from escalated import signals
from escalated.event_names import CANONICAL_EVENTS, LEGACY_EVENT_NAMES
from escalated.support.import_context import ImportContext

logger = logging.getLogger("escalated")

LIFECYCLE_ACTIONS = ("plugin.activated", "plugin.deactivated", "plugin.uninstalling")

# How many plugin actions may nest (see guard).
MAX_DEPTH = 3

_running = threading.local()


def _stack():
    return list(getattr(_running, "stack", None) or ())


def guard(name, deliver, origin=None):
    """
    Re-entrancy guard, after the workflow engine's.

    Plugin ctx writes go through the ticket service, so they raise canonical
    events while the plugin that wrote is still handling its action. While an
    action is being delivered to plugins, the same action (raised by a
    plugin's own write, or ctx.emit) is not delivered again, and nesting stops
    at MAX_DEPTH, so a ticket.created handler that opens a ticket does not
    trigger itself. Webhooks and workflows still see every event.

    ``origin`` is the chain of actions being delivered when the event was
    raised: delivery waits for the commit, which may come after the action
    that raised it has returned. Returns whether ``deliver`` ran.
    """
    previous = getattr(_running, "stack", None)
    chain = list(origin) if origin is not None else _stack()
    if name in chain or len(chain) >= MAX_DEPTH:
        logger.debug("Plugin action %s skipped: raised while %s run", name, chain)
        return False
    _running.stack = [*chain, name]
    try:
        deliver()
    finally:
        _running.stack = previous
    return True


def is_reserved_hook(hook):
    """Whether a plugin-emitted hook would impersonate a host event."""
    return hook in LIFECYCLE_ACTIONS or hook in CANONICAL_EVENTS or hook in LEGACY_EVENT_NAMES


def _id(obj):
    """Primary key as a JSON value. Host user models may use UUID keys."""
    pk = getattr(obj, "pk", obj)
    if pk is None or isinstance(pk, int):
        return pk
    return str(pk)


def _iso(value):
    return value.isoformat() if value is not None else None


def plugin_ticket(ticket):
    return {
        "id": ticket.pk,
        "reference": ticket.reference,
        "subject": ticket.subject,
        "title": ticket.subject,
        "description": ticket.description,
        "status": ticket.status,
        "priority": ticket.priority,
        "channel": ticket.channel,
        "ticket_type": ticket.ticket_type,
        "department_id": ticket.department_id,
        "assigned_to": _id(ticket.assigned_to_id),
        "requester_id": ticket.requester_object_id,
        "contact_id": ticket.contact_id,
        "metadata": ticket.metadata,
        "created_at": _iso(ticket.created_at),
        "updated_at": _iso(ticket.updated_at),
    }


def plugin_reply(reply):
    return {
        "id": reply.pk,
        "ticket_id": reply.ticket_id,
        "body": reply.body,
        "type": reply.type,
        "is_internal": bool(reply.is_internal_note),
        "author_id": _id(reply.author_id),
        "created_at": _iso(reply.created_at),
        "updated_at": _iso(reply.updated_at),
    }


def _with_ticket(ticket, **extra):
    flat = plugin_ticket(ticket)
    return {**flat, "ticket": flat, **extra}


def _reply_payload(reply, ticket):
    flat = plugin_reply(reply)
    return {**flat, "reply": flat, "ticket": plugin_ticket(ticket)}


def _chat(session, ticket=None, **extra):
    """Never the visitor's token, email or a message body."""
    ticket = ticket or session.ticket
    return {
        "session": {
            "session_id": session.pk,
            "ticket_id": ticket.pk,
            "status": session.status,
            "agent_id": _id(session.agent_id),
            "department_id": ticket.department_id,
            **extra,
        }
    }


def deliver(name, build):
    """Build the payload and deliver ``name`` to plugins once the change commits."""
    if ImportContext.is_importing():
        return
    origin = _stack()

    def run():
        try:
            payload = build()
        except Exception as exc:
            logger.warning("Could not build the plugin payload for %s: %s", name, exc)
            return

        guard(name, lambda: _deliver_now(name, payload), origin)

    transaction.on_commit(run)


def _deliver_now(name, payload):
    try:
        from escalated.hooks import do_action

        do_action(name, payload)
    except Exception as exc:
        logger.error("Plugin action %s failed: %s", name, exc)

    try:
        from escalated.bridge.plugin_bridge import get_bridge

        bridge = get_bridge()
        if bridge.is_booted():
            bridge.dispatch_action(name, payload)
    except Exception as exc:
        logger.warning("SDK plugin action %s failed: %s", name, exc)


@receiver(signals.ticket_created, dispatch_uid="escalated.plugin_event.ticket_created")
def _ticket_created(sender, ticket, **kwargs):
    deliver("ticket.created", lambda: _with_ticket(ticket))


@receiver(signals.ticket_updated, dispatch_uid="escalated.plugin_event.ticket_updated")
def _ticket_updated(sender, ticket, changes=None, **kwargs):
    new_values = {field: change.get("new") for field, change in (changes or {}).items() if isinstance(change, dict)}
    deliver("ticket.updated", lambda: _with_ticket(ticket, changes=new_values))


@receiver(signals.ticket_status_changed, dispatch_uid="escalated.plugin_event.ticket_status_changed")
def _status_changed(sender, ticket, old_status=None, new_status=None, **kwargs):
    deliver("ticket.status_changed", lambda: _with_ticket(ticket, old_status=old_status, new_status=new_status))


@receiver(signals.ticket_resolved, dispatch_uid="escalated.plugin_event.ticket_resolved")
def _resolved(sender, ticket, **kwargs):
    deliver("ticket.resolved", lambda: _with_ticket(ticket))


@receiver(signals.ticket_closed, dispatch_uid="escalated.plugin_event.ticket_closed")
def _closed(sender, ticket, **kwargs):
    deliver("ticket.closed", lambda: _with_ticket(ticket))


@receiver(signals.ticket_reopened, dispatch_uid="escalated.plugin_event.ticket_reopened")
def _reopened(sender, ticket, **kwargs):
    deliver("ticket.reopened", lambda: _with_ticket(ticket))


@receiver(signals.ticket_assigned, dispatch_uid="escalated.plugin_event.ticket_assigned")
def _assigned(sender, ticket, agent=None, **kwargs):
    deliver("ticket.assigned", lambda: _with_ticket(ticket, agent_id=_id(agent)))


@receiver(signals.ticket_unassigned, dispatch_uid="escalated.plugin_event.ticket_unassigned")
def _unassigned(sender, ticket, previous_agent=None, **kwargs):
    deliver("ticket.unassigned", lambda: _with_ticket(ticket, previous_agent_id=_id(previous_agent)))


@receiver(signals.ticket_escalated, dispatch_uid="escalated.plugin_event.ticket_escalated")
def _escalated(sender, ticket, reason=None, **kwargs):
    deliver("ticket.escalated", lambda: _with_ticket(ticket, reason=reason))


@receiver(signals.ticket_priority_changed, dispatch_uid="escalated.plugin_event.ticket_priority_changed")
def _priority_changed(sender, ticket, old_priority=None, new_priority=None, **kwargs):
    deliver(
        "ticket.priority_changed",
        lambda: _with_ticket(ticket, old_priority=old_priority, new_priority=new_priority),
    )


@receiver(signals.department_changed, dispatch_uid="escalated.plugin_event.department_changed")
def _department_changed(sender, ticket, old_department=None, new_department=None, **kwargs):
    deliver(
        "ticket.department_changed",
        lambda: _with_ticket(ticket, old_department_id=_id(old_department), new_department_id=_id(new_department)),
    )


@receiver(signals.reply_created, dispatch_uid="escalated.plugin_event.reply_created")
def _reply_created(sender, reply, ticket, **kwargs):
    deliver("reply.created", lambda: _reply_payload(reply, ticket))


@receiver(signals.internal_note_added, dispatch_uid="escalated.plugin_event.internal_note_added")
def _note_created(sender, reply, ticket, **kwargs):
    deliver("note.created", lambda: _reply_payload(reply, ticket))


@receiver(signals.sla_breached, dispatch_uid="escalated.plugin_event.sla_breached")
def _sla_breached(sender, ticket, breach_type=None, **kwargs):
    deliver("sla.breached", lambda: _with_ticket(ticket, type=breach_type))


@receiver(signals.sla_warning, dispatch_uid="escalated.plugin_event.sla_warning")
def _sla_warning(sender, ticket, warning_type=None, remaining=None, **kwargs):
    minutes = int(remaining.total_seconds() // 60) if remaining is not None else None
    deliver("sla.warning", lambda: _with_ticket(ticket, type=warning_type, minutes_remaining=minutes))


def _tag(tag):
    return {"id": tag.pk, "name": tag.name, "slug": getattr(tag, "slug", None)}


@receiver(signals.tag_added, dispatch_uid="escalated.plugin_event.tag_added")
def _tag_added(sender, tag, ticket, **kwargs):
    deliver("ticket.tag_added", lambda: _with_ticket(ticket, tag=_tag(tag)))


@receiver(signals.tag_removed, dispatch_uid="escalated.plugin_event.tag_removed")
def _tag_removed(sender, tag, ticket, **kwargs):
    deliver("ticket.tag_removed", lambda: _with_ticket(ticket, tag=_tag(tag)))


@receiver(signals.chat_started, dispatch_uid="escalated.plugin_event.chat_started")
def _chat_started(sender, session, ticket=None, **kwargs):
    deliver("chat.started", lambda: _chat(session, ticket))


@receiver(signals.chat_assigned, dispatch_uid="escalated.plugin_event.chat_assigned")
def _chat_assigned(sender, session, ticket=None, **kwargs):
    deliver("chat.assigned", lambda: _chat(session, ticket))


@receiver(signals.chat_transferred, dispatch_uid="escalated.plugin_event.chat_transferred")
def _chat_transferred(sender, session, ticket=None, from_agent=None, to_agent=None, to_department=None, **kwargs):
    deliver(
        "chat.transferred",
        lambda: _chat(
            session,
            ticket,
            from_agent_id=_id(from_agent),
            to_agent_id=_id(to_agent),
            to_department_id=_id(to_department),
        ),
    )


@receiver(signals.chat_message_sent, dispatch_uid="escalated.plugin_event.chat_message")
def _chat_message(sender, session, ticket=None, message=None, sender_type="customer", **kwargs):
    author_type = "agent" if sender_type == "agent" else "visitor"
    deliver("chat.message", lambda: _chat(session, ticket, reply_id=_id(message), author_type=author_type))


@receiver(signals.chat_ended, dispatch_uid="escalated.plugin_event.chat_ended")
def _chat_ended(sender, session, ticket=None, ended_by=None, **kwargs):
    deliver("chat.ended", lambda: _chat(session, ticket, ended_by="agent" if ended_by is not None else "customer"))
