"""
Tests for the WorkflowEngine signal wire-up in
escalated/workflow_handlers.py.
"""
from unittest.mock import MagicMock, patch

import pytest

from escalated import signals as esc_signals
from escalated.models import Ticket


@pytest.mark.django_db
class TestWorkflowSubscriber:
    @pytest.fixture
    def ticket(self, request):
        from tests.factories import TicketFactory

        return TicketFactory()

    @patch("escalated.services.workflow_engine.WorkflowEngine")
    def test_ticket_created_signal_fires_workflow_engine(self, engine_cls, ticket):
        engine = MagicMock()
        engine_cls.return_value = engine

        esc_signals.ticket_created.send(sender=Ticket, ticket=ticket, user=None)

        engine.process_event.assert_called_once()
        assert engine.process_event.call_args[0][0] == "ticket.created"
        assert engine.process_event.call_args[0][1] is ticket

    @patch("escalated.services.workflow_engine.WorkflowEngine")
    def test_status_changed_maps_to_ticket_status_changed(self, engine_cls, ticket):
        engine = MagicMock()
        engine_cls.return_value = engine

        esc_signals.ticket_status_changed.send(
            sender=Ticket,
            ticket=ticket,
            user=None,
            old_status="open",
            new_status="resolved",
        )

        # Find our mapping among all subscribers that fired
        calls = [c for c in engine.process_event.call_args_list]
        assert any(c.args[0] == "ticket.status_changed" for c in calls)

    @patch("escalated.services.workflow_engine.WorkflowEngine")
    def test_reply_created_maps_to_ticket_replied(self, engine_cls, ticket):
        """Call our handler directly so we don't trigger other subscribers
        that would try to JSON-serialize a MagicMock reply."""
        engine = MagicMock()
        engine_cls.return_value = engine
        reply = MagicMock()

        from escalated.workflow_handlers import _workflow_reply_created

        _workflow_reply_created(sender=type(reply), reply=reply, ticket=ticket)

        engine.process_event.assert_called_once()
        assert engine.process_event.call_args[0][0] == "ticket.replied"

    @patch("escalated.services.workflow_engine.WorkflowEngine")
    def test_missing_ticket_is_noop(self, engine_cls, ticket):
        """When ticket is None our workflow handler should skip the engine.

        (Other unrelated handlers for the same signal may still fire but
        they don't touch our mocked WorkflowEngine.)
        """
        engine = MagicMock()
        engine_cls.return_value = engine

        # Call our handler directly to isolate from other subscribers
        from escalated.workflow_handlers import _workflow_reply_created

        _workflow_reply_created(sender=object, reply=None, ticket=None)

        engine.process_event.assert_not_called()

    @patch("escalated.services.workflow_engine.WorkflowEngine")
    def test_engine_error_is_swallowed(self, engine_cls, ticket):
        engine = MagicMock()
        engine.process_event.side_effect = RuntimeError("boom")
        engine_cls.return_value = engine

        # Should not raise; the signal chain continues.
        esc_signals.ticket_created.send(sender=Ticket, ticket=ticket, user=None)
