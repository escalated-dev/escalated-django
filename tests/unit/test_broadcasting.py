from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from escalated import signals as esc_signals
from escalated.broadcasting import (
    broadcast_event,
    broadcasting_enabled,
    connect_signals,
    disconnect_signals,
    get_pending_events,
    on_reply_created,
    on_ticket_assigned,
    on_ticket_created,
    on_ticket_status_changed,
    on_ticket_updated,
)
from escalated.models import Reply, Ticket
from escalated.services.ticket_service import TicketService
from tests.factories import ReplyFactory, TicketFactory, UserFactory


class TestBroadcastingEnabled:
    def test_disabled_by_default(self, settings):
        if hasattr(settings, "ESCALATED_BROADCASTING_ENABLED"):
            del settings.ESCALATED_BROADCASTING_ENABLED
        assert broadcasting_enabled() is False

    def test_enabled_when_set(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = True
        assert broadcasting_enabled() is True

    def test_disabled_when_false(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = False
        assert broadcasting_enabled() is False


class TestBroadcastEvent:
    def setup_method(self):
        cache.clear()

    def test_no_op_when_disabled(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = False
        broadcast_event("test.event", "test_channel", {"key": "value"})
        events = get_pending_events("test_channel")
        assert len(events) == 0

    def test_caches_event_when_enabled(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = True
        broadcast_event("test.event", "test_channel", {"key": "value"})
        events = get_pending_events("test_channel")
        assert len(events) == 1
        assert events[0]["event_type"] == "test.event"
        assert events[0]["payload"] == {"key": "value"}

    def test_get_pending_clears_events(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = True
        broadcast_event("test.event", "channel1", {"key": "val"})
        events = get_pending_events("channel1")
        assert len(events) == 1

        # Second call should be empty
        events2 = get_pending_events("channel1")
        assert len(events2) == 0

    def test_multiple_events_on_same_channel(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = True
        broadcast_event("e1", "ch", {"a": 1})
        broadcast_event("e2", "ch", {"b": 2})
        events = get_pending_events("ch")
        assert len(events) == 2
        assert events[0]["event_type"] == "e1"
        assert events[1]["event_type"] == "e2"

    def test_different_channels_isolated(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = True
        broadcast_event("e1", "ch1", {"a": 1})
        broadcast_event("e2", "ch2", {"b": 2})
        assert len(get_pending_events("ch1")) == 1
        assert len(get_pending_events("ch2")) == 1

    def test_bounded_list(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = True
        for i in range(150):
            broadcast_event(f"e{i}", "bounded", {"i": i})
        events = get_pending_events("bounded")
        assert len(events) == 100  # Bounded to 100


@pytest.mark.django_db
class TestSignalHandlers:
    def setup_method(self):
        cache.clear()

    def test_on_ticket_created(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = True
        ticket = TicketFactory()
        on_ticket_created(sender=None, ticket=ticket)

        events = get_pending_events(f"ticket.{ticket.pk}")
        assert len(events) == 1
        assert events[0]["event_type"] == "ticket.created"
        assert events[0]["payload"]["ticket_id"] == ticket.pk

    def test_on_ticket_updated(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = True
        ticket = TicketFactory()
        on_ticket_updated(sender=None, ticket=ticket, changes={"subject": "New"})

        events = get_pending_events(f"ticket.{ticket.pk}")
        assert len(events) == 1
        assert events[0]["event_type"] == "ticket.updated"
        assert events[0]["payload"]["changes"] == {"subject": "New"}

    def test_on_ticket_status_changed(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = True
        ticket = TicketFactory()
        on_ticket_status_changed(sender=None, ticket=ticket, old_status="open", new_status="closed")

        events = get_pending_events(f"ticket.{ticket.pk}")
        assert len(events) == 1
        assert events[0]["payload"]["old_status"] == "open"
        assert events[0]["payload"]["new_status"] == "closed"

    def test_on_ticket_assigned(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = True
        ticket = TicketFactory()
        agent = UserFactory()
        on_ticket_assigned(sender=None, ticket=ticket, agent=agent)

        events = get_pending_events(f"ticket.{ticket.pk}")
        assert len(events) == 1
        assert events[0]["payload"]["agent_id"] == agent.pk

    def test_on_reply_created(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = True
        ticket = TicketFactory()
        reply = ReplyFactory(ticket=ticket, is_internal_note=False)
        on_reply_created(sender=None, reply=reply, ticket=ticket)

        events = get_pending_events(f"ticket.{ticket.pk}")
        assert len(events) == 1
        assert events[0]["event_type"] == "reply.created"
        assert events[0]["payload"]["reply_id"] == reply.pk

    def test_handler_ignores_none_ticket(self, settings):
        settings.ESCALATED_BROADCASTING_ENABLED = True
        # Should not raise
        on_ticket_created(sender=None, ticket=None)
        on_ticket_updated(sender=None, ticket=None)
        on_ticket_status_changed(sender=None, ticket=None)
        on_ticket_assigned(sender=None, ticket=None)
        on_reply_created(sender=None, reply=None, ticket=None)


def _broadcast_types(broadcast):
    return [call.args[0] for call in broadcast.call_args_list]


@pytest.mark.django_db
class TestConnectedAtStartup:
    """AppConfig.ready() connects the handlers. Nothing here calls connect_signals()."""

    @override_settings(ESCALATED_BROADCASTING_ENABLED=True)
    def test_creating_a_ticket_broadcasts_when_enabled(self):
        with patch("escalated.broadcasting.broadcast_event") as broadcast:
            ticket = TicketService().create(UserFactory(), {"subject": "Printer on fire", "description": "Help"})

        assert _broadcast_types(broadcast) == ["ticket.created"]
        assert broadcast.call_args.args[1] == f"ticket.{ticket.pk}"

    @override_settings(ESCALATED_BROADCASTING_ENABLED=False)
    def test_creating_a_ticket_broadcasts_nothing_when_disabled(self):
        cache.clear()
        with patch("escalated.broadcasting.broadcast_event") as broadcast:
            ticket = TicketService().create(UserFactory(), {"subject": "Printer on fire", "description": "Help"})

        broadcast.assert_not_called()
        assert get_pending_events(f"ticket.{ticket.pk}") == []

    @override_settings(ESCALATED_BROADCASTING_ENABLED=True)
    @pytest.mark.parametrize(
        "signal_name, event_type",
        [
            ("ticket_created", "ticket.created"),
            ("ticket_updated", "ticket.updated"),
            ("ticket_status_changed", "ticket.status_changed"),
            ("ticket_assigned", "ticket.assigned"),
            ("reply_created", "reply.created"),
        ],
    )
    def test_each_signal_reaches_its_handler(self, signal_name, event_type):
        ticket = TicketFactory()
        kwargs = {
            "ticket_created": {"sender": Ticket, "ticket": ticket, "user": None},
            "ticket_updated": {
                "sender": Ticket,
                "ticket": ticket,
                "user": None,
                "changes": {"subject": {"old": "a", "new": "b"}},
            },
            "ticket_status_changed": {
                "sender": Ticket,
                "ticket": ticket,
                "user": None,
                "old_status": "open",
                "new_status": "in_progress",
            },
            "ticket_assigned": {"sender": Ticket, "ticket": ticket, "user": None, "agent": UserFactory()},
            "reply_created": {"sender": Reply, "reply": ReplyFactory(ticket=ticket), "ticket": ticket, "user": None},
        }[signal_name]

        with patch("escalated.broadcasting.broadcast_event") as broadcast:
            getattr(esc_signals, signal_name).send(**kwargs)

        assert _broadcast_types(broadcast) == [event_type]


@pytest.fixture
def reconnect_broadcasting():
    """disconnect_signals() would otherwise leave the startup handlers unhooked for later tests."""
    yield
    connect_signals()


@pytest.mark.django_db
@pytest.mark.usefixtures("reconnect_broadcasting")
class TestConnectDisconnect:
    def test_connect_and_disconnect(self):
        # Should not raise
        connect_signals()
        disconnect_signals()

    @override_settings(ESCALATED_BROADCASTING_ENABLED=True)
    def test_connect_idempotent(self):
        # Hosts that followed the old advice and call connect_signals() themselves
        # must not get every event twice now that ready() connects them too.
        connect_signals()
        connect_signals()

        ticket = TicketFactory()
        with patch("escalated.broadcasting.broadcast_event") as broadcast:
            esc_signals.ticket_created.send(sender=Ticket, ticket=ticket, user=None)

        assert _broadcast_types(broadcast) == ["ticket.created"]

    @override_settings(ESCALATED_BROADCASTING_ENABLED=True)
    def test_disconnect_stops_broadcasts(self):
        disconnect_signals()

        ticket = TicketFactory()
        with patch("escalated.broadcasting.broadcast_event") as broadcast:
            esc_signals.ticket_created.send(sender=Ticket, ticket=ticket, user=None)

        broadcast.assert_not_called()
