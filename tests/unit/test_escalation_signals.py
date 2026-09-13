"""
An escalation rule that changes a ticket's priority, assignee or department
must send the same signals the driver sends for those changes.

EscalationService._execute_actions() set the fields and saved the ticket but
sent only ticket_escalated, so everything listening for
ticket_priority_changed, ticket_assigned or department_changed (activity,
the assigned agent's notification, workflows, webhooks, plugins) never heard
about changes an escalation rule made. ticket_escalated itself was sent before
the ticket was saved.
"""

import pytest

from escalated import signals as esc_signals
from escalated.models import EscalationRule, Ticket
from escalated.services.escalation_service import EscalationService
from tests.factories import DepartmentFactory, EscalationRuleFactory, TicketFactory, UserFactory


@pytest.fixture
def received():
    """Record every send of the four signals, with the ticket as it is stored at that moment."""
    calls = {}
    receivers = []

    def make(name):
        def receiver(sender, **kwargs):
            ticket = kwargs["ticket"]
            stored = Ticket.objects.get(pk=ticket.pk)
            calls.setdefault(name, []).append({"sender": sender, "stored": stored, **kwargs})

        return receiver

    for name in ("ticket_priority_changed", "ticket_assigned", "department_changed", "ticket_escalated"):
        receiver = make(name)
        getattr(esc_signals, name).connect(receiver, weak=False)
        receivers.append((name, receiver))

    yield calls

    for name, receiver in receivers:
        getattr(esc_signals, name).disconnect(receiver)


def _breached_ticket(**fields):
    return TicketFactory(sla_first_response_breached=True, **fields)


@pytest.mark.django_db
def test_rule_changes_send_the_driver_signals(received):
    agent = UserFactory()
    department = DepartmentFactory()
    ticket = _breached_ticket(priority=Ticket.Priority.MEDIUM, assigned_to=None, department=None)
    EscalationRuleFactory(
        trigger_type=EscalationRule.TriggerType.SLA_BREACH,
        actions={"set_priority": "urgent", "assign_to_id": agent.pk, "department_id": department.pk},
    )

    assert EscalationService.evaluate_ticket(ticket) == 1

    [priority] = received.get("ticket_priority_changed", [])
    assert priority["sender"] is Ticket
    assert priority["ticket"].pk == ticket.pk
    assert priority["user"] is None
    assert priority["old_priority"] == "medium"
    assert priority["new_priority"] == "urgent"

    [assigned] = received.get("ticket_assigned", [])
    assert assigned["sender"] is Ticket
    assert assigned["user"] is None
    assert assigned["agent"] == agent

    [moved] = received.get("department_changed", [])
    assert moved["sender"] is Ticket
    assert moved["user"] is None
    assert moved["old_department"] is None
    assert moved["new_department"] == department


@pytest.mark.django_db
def test_receivers_see_the_saved_ticket(received):
    agent = UserFactory()
    department = DepartmentFactory()
    ticket = _breached_ticket(priority=Ticket.Priority.MEDIUM)
    EscalationRuleFactory(
        trigger_type=EscalationRule.TriggerType.SLA_BREACH,
        actions={
            "set_priority": "urgent",
            "escalate": True,
            "assign_to_id": agent.pk,
            "department_id": department.pk,
        },
    )

    EscalationService.evaluate_ticket(ticket)

    for name in ("ticket_priority_changed", "ticket_assigned", "department_changed", "ticket_escalated"):
        [call] = received.get(name, [None]) or [None]
        assert call is not None, f"{name} was not sent"
        stored = call["stored"]
        assert stored.priority == "urgent", name
        assert stored.status == Ticket.Status.ESCALATED, name
        assert stored.assigned_to_id == agent.pk, name
        assert stored.department_id == department.pk, name


@pytest.mark.django_db
def test_unchanged_values_send_nothing(received):
    agent = UserFactory()
    department = DepartmentFactory()
    ticket = _breached_ticket(priority=Ticket.Priority.URGENT, assigned_to=agent, department=department)
    EscalationRuleFactory(
        trigger_type=EscalationRule.TriggerType.SLA_BREACH,
        actions={"set_priority": "urgent", "assign_to_id": agent.pk, "department_id": department.pk},
    )

    assert EscalationService.evaluate_ticket(ticket) == 0

    assert received == {}
