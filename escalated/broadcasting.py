"""
Real-time broadcasting support for Escalated.

Emits events that can be consumed by Django Channels or other real-time
backends.  Broadcasting is opt-in via the ESCALATED_BROADCASTING_ENABLED
setting (defaults to ``False``).

When enabled, signal handlers for ticket lifecycle events will call
``broadcast_event()`` which dispatches to the configured backend.
The default backend writes to the Django cache for polling; when Django
Channels is installed, it sends to a channel layer group.
"""

import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("escalated.broadcasting")


def broadcasting_enabled():
    """Check if broadcasting is enabled."""
    return getattr(settings, "ESCALATED_BROADCASTING_ENABLED", False)


def get_channel_layer():
    """
    Attempt to import and return the Django Channels default channel layer.
    Returns ``None`` if channels is not installed or not configured.
    """
    try:
        from channels.layers import get_channel_layer as _get_layer

        layer = _get_layer()
        return layer
    except (ImportError, Exception):
        return None


def broadcast_event(event_type, channel, payload):
    """
    Broadcast an event to a named channel.

    If Django Channels is available and configured, the event is sent to a
    channel-layer group.  Otherwise it is pushed to a cache-backed list
    that can be polled via ``get_pending_events()``.

    Args:
        event_type: Short string identifying the event (e.g. "ticket.created").
        channel: The channel/group name (e.g. "ticket.42").
        payload: JSON-serializable dict of event data.
    """
    if not broadcasting_enabled():
        return

    event = {
        "type": "escalated.event",
        "event_type": event_type,
        "channel": channel,
        "payload": payload,
    }

    layer = get_channel_layer()
    if layer is not None:
        from asgiref.sync import async_to_sync

        try:
            async_to_sync(layer.group_send)(channel, event)
            logger.debug("Broadcast %s to channel layer group %s", event_type, channel)
            return
        except Exception as exc:
            logger.warning("Channel layer send failed: %s", exc)

    # Fallback: cache-backed event list (for polling or testing)
    cache_key = f"escalated.broadcast.{channel}"
    events = cache.get(cache_key, [])
    events.append(event)
    # Keep a bounded list and 5-minute TTL
    cache.set(cache_key, events[-100:], 300)
    logger.debug("Broadcast %s to cache key %s", event_type, cache_key)


def get_pending_events(channel):
    """
    Retrieve and clear pending events for a channel (cache backend only).

    Useful for testing and for simple polling endpoints.
    """
    cache_key = f"escalated.broadcast.{channel}"
    events = cache.get(cache_key, [])
    cache.delete(cache_key)
    return events


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------


def on_ticket_created(sender, **kwargs):
    ticket = kwargs.get("ticket")
    if ticket is None:
        return
    broadcast_event(
        "ticket.created",
        f"ticket.{ticket.pk}",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "subject": ticket.subject,
            "status": ticket.status,
        },
    )


def on_ticket_updated(sender, **kwargs):
    ticket = kwargs.get("ticket")
    changes = kwargs.get("changes", {})
    if ticket is None:
        return
    broadcast_event(
        "ticket.updated",
        f"ticket.{ticket.pk}",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "changes": changes,
        },
    )


def on_ticket_status_changed(sender, **kwargs):
    ticket = kwargs.get("ticket")
    if ticket is None:
        return
    broadcast_event(
        "ticket.status_changed",
        f"ticket.{ticket.pk}",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "old_status": kwargs.get("old_status"),
            "new_status": kwargs.get("new_status"),
        },
    )


def on_ticket_assigned(sender, **kwargs):
    ticket = kwargs.get("ticket")
    agent = kwargs.get("agent")
    if ticket is None:
        return
    broadcast_event(
        "ticket.assigned",
        f"ticket.{ticket.pk}",
        {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "agent_id": agent.pk if agent else None,
        },
    )


def on_reply_created(sender, **kwargs):
    reply = kwargs.get("reply")
    ticket = kwargs.get("ticket")
    if ticket is None:
        return
    broadcast_event(
        "reply.created",
        f"ticket.{ticket.pk}",
        {
            "ticket_id": ticket.pk,
            "reply_id": reply.pk if reply else None,
            "is_internal": reply.is_internal_note if reply else False,
        },
    )


def connect_signals():
    """
    Connect broadcasting signal handlers.

    Should be called from AppConfig.ready() when broadcasting is enabled.
    """
    from escalated.signals import (
        reply_created,
        ticket_assigned,
        ticket_created,
        ticket_status_changed,
        ticket_updated,
    )

    ticket_created.connect(on_ticket_created)
    ticket_updated.connect(on_ticket_updated)
    ticket_status_changed.connect(on_ticket_status_changed)
    ticket_assigned.connect(on_ticket_assigned)
    reply_created.connect(on_reply_created)


def disconnect_signals():
    """Disconnect broadcasting signal handlers (useful in tests)."""
    from escalated.signals import (
        reply_created,
        ticket_assigned,
        ticket_created,
        ticket_status_changed,
        ticket_updated,
    )

    ticket_created.disconnect(on_ticket_created)
    ticket_updated.disconnect(on_ticket_updated)
    ticket_status_changed.disconnect(on_ticket_status_changed)
    ticket_assigned.disconnect(on_ticket_assigned)
    reply_created.disconnect(on_reply_created)
