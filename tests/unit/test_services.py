import pytest
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from escalated.models import Ticket, SlaPolicy, EscalationRule
from escalated.services.sla_service import SlaService
from escalated.services.escalation_service import EscalationService
from escalated.services.ticket_service import TicketService
from tests.factories import (
    UserFactory,
    TicketFactory,
    SlaPolicyFactory,
    DepartmentFactory,
    EscalationRuleFactory,
)


@pytest.mark.django_db
class TestSlaService:
    def test_apply_sla_deadlines_sets_first_response_due(self):
        policy = SlaPolicyFactory(
            first_response_hours={"medium": 8},
            resolution_hours={"medium": 24},
        )
        ticket = TicketFactory(sla_policy=policy, priority=Ticket.Priority.MEDIUM)

        SlaService.apply_sla_deadlines(ticket)

        assert ticket.first_response_due_at is not None
        assert ticket.resolution_due_at is not None

        # Verify the deadline is approximately 8 hours from now
        expected_first_response = timezone.now() + timedelta(hours=8)
        delta = abs(
            (ticket.first_response_due_at - expected_first_response).total_seconds()
        )
        assert delta < 5  # Within 5 seconds

    def test_apply_sla_deadlines_no_policy(self):
        ticket = TicketFactory(sla_policy=None)
        SlaService.apply_sla_deadlines(ticket)
        assert ticket.first_response_due_at is None
        assert ticket.resolution_due_at is None

    def test_check_breach_detects_first_response_breach(self):
        policy = SlaPolicyFactory()
        ticket = TicketFactory(
            sla_policy=policy,
            first_response_due_at=timezone.now() - timedelta(hours=1),
            first_response_at=None,
            sla_first_response_breached=False,
        )

        breached = SlaService.check_breach(ticket)
        assert breached is True
        ticket.refresh_from_db()
        assert ticket.sla_first_response_breached is True

    def test_check_breach_detects_resolution_breach(self):
        policy = SlaPolicyFactory()
        ticket = TicketFactory(
            sla_policy=policy,
            resolution_due_at=timezone.now() - timedelta(hours=1),
            resolved_at=None,
            sla_resolution_breached=False,
        )

        breached = SlaService.check_breach(ticket)
        assert breached is True
        ticket.refresh_from_db()
        assert ticket.sla_resolution_breached is True

    def test_check_breach_ignores_already_responded(self):
        policy = SlaPolicyFactory()
        ticket = TicketFactory(
            sla_policy=policy,
            first_response_due_at=timezone.now() - timedelta(hours=1),
            first_response_at=timezone.now() - timedelta(hours=2),
            sla_first_response_breached=False,
        )

        breached = SlaService.check_breach(ticket)
        assert breached is False

    def test_check_breach_ignores_closed_tickets(self):
        policy = SlaPolicyFactory()
        ticket = TicketFactory(
            status=Ticket.Status.CLOSED,
            sla_policy=policy,
            first_response_due_at=timezone.now() - timedelta(hours=1),
            sla_first_response_breached=False,
        )

        breached = SlaService.check_breach(ticket)
        assert breached is False

    def test_check_warning_fires_when_approaching_deadline(self):
        policy = SlaPolicyFactory()
        ticket = TicketFactory(
            sla_policy=policy,
            first_response_due_at=timezone.now() + timedelta(minutes=15),
            first_response_at=None,
            sla_first_response_breached=False,
        )

        warned = SlaService.check_warning(ticket, warning_threshold_minutes=30)
        assert warned is True

    def test_check_warning_does_not_fire_when_far_from_deadline(self):
        policy = SlaPolicyFactory()
        ticket = TicketFactory(
            sla_policy=policy,
            first_response_due_at=timezone.now() + timedelta(hours=5),
            first_response_at=None,
            sla_first_response_breached=False,
        )

        warned = SlaService.check_warning(ticket, warning_threshold_minutes=30)
        assert warned is False

    def test_get_default_policy(self):
        SlaPolicyFactory(is_default=False, name="Non-default")
        default = SlaPolicyFactory(is_default=True, name="Default")

        result = SlaService.get_default_policy()
        assert result is not None
        assert result.name == "Default"

    def test_get_default_policy_none_when_no_default(self):
        SlaPolicyFactory(is_default=False)
        result = SlaService.get_default_policy()
        assert result is None

    def test_check_all_tickets(self):
        policy = SlaPolicyFactory()
        # Create a ticket with breached SLA
        TicketFactory(
            sla_policy=policy,
            first_response_due_at=timezone.now() - timedelta(hours=1),
            first_response_at=None,
            sla_first_response_breached=False,
        )
        # Create a ticket that's fine
        TicketFactory(
            sla_policy=policy,
            first_response_due_at=timezone.now() + timedelta(hours=5),
            first_response_at=None,
        )

        breached_count, warned_count = SlaService.check_all_tickets()
        assert breached_count >= 1


@pytest.mark.django_db
class TestEscalationService:
    def test_evaluate_sla_breach_rule(self):
        rule = EscalationRuleFactory(
            trigger_type=EscalationRule.TriggerType.SLA_BREACH,
            conditions={},
            actions={"escalate": True},
        )
        ticket = TicketFactory(
            sla_first_response_breached=True,
            status=Ticket.Status.OPEN,
        )

        actions = EscalationService.evaluate_ticket(ticket)
        assert actions >= 1

        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.ESCALATED

    def test_evaluate_no_response_rule(self):
        rule = EscalationRuleFactory(
            trigger_type=EscalationRule.TriggerType.NO_RESPONSE,
            conditions={"no_response_hours": 1},
            actions={"set_priority": "high"},
        )
        ticket = TicketFactory(
            status=Ticket.Status.OPEN,
            priority=Ticket.Priority.MEDIUM,
        )
        # Make the ticket old enough
        Ticket.objects.filter(pk=ticket.pk).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        ticket.refresh_from_db()

        actions = EscalationService.evaluate_ticket(ticket)
        assert actions >= 1

        ticket.refresh_from_db()
        assert ticket.priority == Ticket.Priority.HIGH

    def test_evaluate_rule_with_status_condition(self):
        rule = EscalationRuleFactory(
            trigger_type=EscalationRule.TriggerType.SLA_BREACH,
            conditions={"status": ["open"]},
            actions={"escalate": True},
        )
        # This ticket is in_progress, not open -- should not match
        ticket = TicketFactory(
            sla_first_response_breached=True,
            status=Ticket.Status.IN_PROGRESS,
        )

        actions = EscalationService.evaluate_ticket(ticket)
        assert actions == 0

    def test_evaluate_rule_inactive_is_skipped(self):
        rule = EscalationRuleFactory(
            trigger_type=EscalationRule.TriggerType.SLA_BREACH,
            conditions={},
            actions={"escalate": True},
            is_active=False,
        )
        ticket = TicketFactory(
            sla_first_response_breached=True,
            status=Ticket.Status.OPEN,
        )

        actions = EscalationService.evaluate_ticket(ticket)
        assert actions == 0

    def test_evaluate_assigns_to_agent(self):
        agent = UserFactory(username="escalation_agent")
        rule = EscalationRuleFactory(
            trigger_type=EscalationRule.TriggerType.SLA_BREACH,
            conditions={},
            actions={"assign_to_id": agent.pk},
        )
        ticket = TicketFactory(
            sla_first_response_breached=True,
            status=Ticket.Status.OPEN,
        )

        EscalationService.evaluate_ticket(ticket)
        ticket.refresh_from_db()
        assert ticket.assigned_to == agent

    def test_evaluate_all(self):
        rule = EscalationRuleFactory(
            trigger_type=EscalationRule.TriggerType.SLA_BREACH,
            conditions={},
            actions={"escalate": True},
        )
        TicketFactory(
            sla_first_response_breached=True,
            status=Ticket.Status.OPEN,
        )
        TicketFactory(
            sla_first_response_breached=False,
            status=Ticket.Status.OPEN,
        )

        actions_taken = EscalationService.evaluate_all()
        assert actions_taken >= 1


@pytest.mark.django_db
class TestTicketService:
    def test_create_ticket(self):
        user = UserFactory(username="ticket_svc_user")
        service = TicketService()

        ticket = service.create(user, {
            "subject": "Test ticket",
            "description": "Test description",
        })

        assert ticket.pk is not None
        assert ticket.subject == "Test ticket"
        assert ticket.reference.startswith("ESC-")
        assert ticket.status == Ticket.Status.OPEN

    def test_create_ticket_with_custom_priority(self):
        user = UserFactory(username="priority_user")
        service = TicketService()

        ticket = service.create(user, {
            "subject": "Urgent issue",
            "description": "Needs attention",
            "priority": "urgent",
        })

        assert ticket.priority == Ticket.Priority.URGENT

    def test_update_ticket(self):
        user = UserFactory(username="update_user")
        ticket = TicketFactory(requester=user, subject="Original")
        service = TicketService()

        service.update(ticket, user, {"subject": "Updated Subject"})
        ticket.refresh_from_db()
        assert ticket.subject == "Updated Subject"

    def test_change_status(self):
        user = UserFactory(username="status_user")
        ticket = TicketFactory(requester=user, status=Ticket.Status.OPEN)
        service = TicketService()

        service.change_status(ticket, user, Ticket.Status.IN_PROGRESS)
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.IN_PROGRESS

    def test_resolve_sets_resolved_at(self):
        user = UserFactory(username="resolve_user")
        ticket = TicketFactory(requester=user)
        service = TicketService()

        service.resolve(ticket, user)
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.RESOLVED
        assert ticket.resolved_at is not None

    def test_close_sets_closed_at(self):
        user = UserFactory(username="close_user")
        ticket = TicketFactory(requester=user)
        service = TicketService()

        service.close(ticket, user)
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.CLOSED
        assert ticket.closed_at is not None

    def test_reopen_clears_timestamps(self):
        user = UserFactory(username="reopen_user")
        ticket = TicketFactory(
            requester=user,
            status=Ticket.Status.RESOLVED,
            resolved_at=timezone.now(),
        )
        service = TicketService()

        service.reopen(ticket, user)
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.REOPENED
        assert ticket.resolved_at is None

    def test_reply_creates_reply(self):
        user = UserFactory(username="reply_user")
        ticket = TicketFactory(requester=user)
        service = TicketService()

        reply = service.reply(ticket, user, {"body": "Thank you!"})
        assert reply.pk is not None
        assert reply.body == "Thank you!"
        assert reply.ticket == ticket

    def test_add_note_creates_internal_note(self):
        user = UserFactory(username="note_user")
        ticket = TicketFactory()
        service = TicketService()

        reply = service.add_note(ticket, user, "Internal note body")
        assert reply.is_internal_note is True
        assert reply.type == "note"
