"""
Python plugins register callbacks with escalated.hooks.add_action().
escalated.hook_registry documents an action for every ticket signal
(ticket_created, ticket_updated, ticket_status_changed, ...), but nothing
called do_action() for any of them, so a plugin's callback never ran.

SDK (Node.js) plugins are a separate path: handlers.py sends those events to
the plugin bridge itself, and that must still happen exactly once.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.dispatch import Signal
from django.utils import timezone

import escalated.signals as esc_signals
from escalated.hook_registry import HookRegistry
from escalated.hooks import add_action, remove_action
from escalated.models import Ticket
from escalated.services.sla_service import SlaService
from escalated.services.ticket_service import TicketService
from escalated.support.import_context import ImportContext
from tests.factories import DepartmentFactory, TagFactory, TicketFactory, UserFactory

TICKET_DATA = {"subject": "Printer on fire", "description": "Help"}


@pytest.fixture
def listen():
    """Register a recording callback for an action; unregister it afterwards."""
    registered = []

    def _listen(tag, callback=None):
        calls = []
        if callback is None:

            def callback(*args, **kwargs):
                calls.append((args, kwargs))

        add_action(tag, callback)
        registered.append((tag, callback))
        return calls

    yield _listen

    for tag, callback in registered:
        remove_action(tag, callback)


@pytest.mark.django_db
def test_ticket_created_action_runs_once_for_a_new_ticket():
    requester = UserFactory()
    callback = MagicMock()
    add_action("ticket_created", callback)
    try:
        ticket = TicketService().create(requester, dict(TICKET_DATA))
    finally:
        remove_action("ticket_created", callback)

    callback.assert_called_once_with(ticket, requester)


def _create(service, ticket, actor):
    return service.create(actor, dict(TICKET_DATA))


def _remove_tag(service, ticket, actor):
    tag = TagFactory()
    ticket.tags.add(tag)
    service.remove_tags(ticket, actor, [tag.pk])
    return ticket


def _breach_sla(service, ticket, actor):
    ticket.first_response_due_at = timezone.now() - timedelta(hours=1)
    ticket.save(update_fields=["first_response_due_at"])
    assert SlaService.check_breach(ticket)
    return ticket


def _warn_sla(service, ticket, actor):
    ticket.first_response_due_at = timezone.now() + timedelta(minutes=10)
    ticket.save(update_fields=["first_response_due_at"])
    assert SlaService.check_warning(ticket)
    return ticket


def _then(ticket):
    return lambda *_: ticket


# How each signal-backed action is produced in the running application. Each
# returns the ticket the action is about.
EMITTERS = {
    "ticket_created": _create,
    "ticket_updated": lambda s, t, a: s.update(t, a, {"subject": "A new subject"}),
    "ticket_status_changed": lambda s, t, a: s.change_status(t, a, Ticket.Status.IN_PROGRESS),
    "ticket_assigned": lambda s, t, a: s.assign(t, a, UserFactory()),
    "ticket_unassigned": lambda s, t, a: s.unassign(t, a),
    "ticket_priority_changed": lambda s, t, a: s.change_priority(t, a, Ticket.Priority.URGENT),
    "ticket_escalated": lambda s, t, a: s.escalate(t, a),
    "ticket_resolved": lambda s, t, a: s.resolve(t, a),
    "ticket_closed": lambda s, t, a: s.close(t, a),
    "ticket_reopened": lambda s, t, a: s.reopen(t, a),
    "reply_created": lambda s, t, a: s.reply(t, a, {"body": "On it"}) and t,
    "internal_note_added": lambda s, t, a: s.add_note(t, a, "Checked the logs") and t,
    "sla_breached": _breach_sla,
    "sla_warning": _warn_sla,
    "tag_added": lambda s, t, a: s.add_tags(t, a, [TagFactory().pk]) or t,
    "tag_removed": _remove_tag,
    "department_changed": lambda s, t, a: s.change_department(t, a, DepartmentFactory()),
}

SIGNAL_BACKED_ACTIONS = sorted(
    name for name in HookRegistry.get_actions() if isinstance(getattr(esc_signals, name, None), Signal)
)


def test_every_signal_backed_action_has_an_emitter_here():
    assert sorted(EMITTERS) == SIGNAL_BACKED_ACTIONS


@pytest.mark.django_db
@pytest.mark.parametrize("action", SIGNAL_BACKED_ACTIONS)
def test_documented_action_fires_once_with_its_documented_arguments(action, listen):
    parameters = HookRegistry.get_actions()[action]["parameters"]
    actor = UserFactory()
    start_status = Ticket.Status.RESOLVED if action == "ticket_reopened" else Ticket.Status.OPEN
    ticket = TicketFactory(status=start_status, assigned_to=UserFactory())

    calls = listen(action)
    subject = EMITTERS[action](TicketService(), ticket, actor)

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert kwargs == {}
    assert len(args) == len(parameters)
    assert args[parameters.index("ticket")].pk == subject.pk
    if "user" in parameters:
        assert args[parameters.index("user")] == actor


@pytest.mark.django_db
def test_sdk_bridge_still_receives_ticket_created_once(listen):
    listen("ticket_created")
    bridge = MagicMock()
    bridge.is_booted.return_value = True

    with patch("escalated.bridge.plugin_bridge.get_bridge", return_value=bridge):
        TicketService().create(UserFactory(), dict(TICKET_DATA))

    hooks = [call.args[0] for call in bridge.dispatch_action.call_args_list]
    assert hooks.count("ticket.created") == 1


@pytest.mark.django_db
def test_actions_do_not_fire_during_an_import(listen):
    calls = listen("ticket_created")

    with ImportContext.suppress_ctx():
        TicketService().create(UserFactory(), dict(TICKET_DATA))

    assert calls == []


@pytest.mark.django_db
def test_a_failing_plugin_callback_does_not_break_ticket_creation(listen):
    def broken(ticket, user):
        raise RuntimeError("plugin bug")

    listen("ticket_created", broken)
    later = listen("ticket_created")

    ticket = TicketService().create(UserFactory(), dict(TICKET_DATA))

    assert Ticket.objects.filter(pk=ticket.pk).exists()
    assert len(later) == 1
