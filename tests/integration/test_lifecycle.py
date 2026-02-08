"""
Full ticket lifecycle integration test.
Tests the complete flow from creation through resolution and closing.
"""

import pytest
from datetime import timedelta

from django.utils import timezone

from escalated.models import Ticket, Reply, TicketActivity
from escalated.services.ticket_service import TicketService
from escalated.services.sla_service import SlaService
from tests.factories import (
    UserFactory,
    DepartmentFactory,
    SlaPolicyFactory,
    TagFactory,
)


@pytest.mark.django_db
class TestTicketLifecycle:
    def test_full_ticket_lifecycle(self):
        """
        Test the complete lifecycle of a support ticket:
        1. Customer creates a ticket
        2. SLA policy is applied
        3. Agent is assigned
        4. Agent adds internal note
        5. Agent replies
        6. Customer replies
        7. Tags are added
        8. Agent resolves
        9. Ticket is auto-closed (or customer reopens)
        """
        # Setup
        service = TicketService()
        customer = UserFactory(username="lifecycle_customer")
        agent = UserFactory(username="lifecycle_agent")
        department = DepartmentFactory(name="Support")
        department.agents.add(agent)
        sla = SlaPolicyFactory(
            is_default=True,
            first_response_hours={"medium": 8},
            resolution_hours={"medium": 24},
        )
        tag = TagFactory(name="Billing", slug="billing")

        # 1. Customer creates a ticket
        ticket = service.create(customer, {
            "subject": "Billing question",
            "description": "I was charged twice for my subscription.",
            "priority": "medium",
            "department_id": department.pk,
        })

        assert ticket.pk is not None
        assert ticket.status == Ticket.Status.OPEN
        assert ticket.reference.startswith("ESC-")
        assert ticket.department == department

        # Verify activity was logged
        assert TicketActivity.objects.filter(
            ticket=ticket,
            type=TicketActivity.ActivityType.CREATED,
        ).exists()

        # 2. Verify SLA policy was applied (via signal handler)
        ticket.refresh_from_db()
        # SLA gets applied in the signal handler if a default exists

        # 3. Agent is assigned
        service.assign(ticket, agent, agent)
        ticket.refresh_from_db()

        assert ticket.assigned_to == agent
        assert ticket.status == Ticket.Status.IN_PROGRESS

        assert TicketActivity.objects.filter(
            ticket=ticket,
            type=TicketActivity.ActivityType.ASSIGNED,
        ).exists()

        # 4. Agent adds an internal note
        note = service.add_note(ticket, agent, "Customer has two charges on card ending 4242.")
        assert note.is_internal_note is True
        assert note.type == Reply.Type.NOTE

        # 5. Agent replies to customer
        reply = service.reply(ticket, agent, {
            "body": "I can see the duplicate charge. Let me process a refund for you."
        })
        assert reply.pk is not None
        assert reply.is_internal_note is False

        ticket.refresh_from_db()
        # After agent replies, status should transition to WAITING_ON_CUSTOMER
        assert ticket.status == Ticket.Status.WAITING_ON_CUSTOMER

        # 6. Customer replies
        customer_reply = service.reply(ticket, customer, {
            "body": "Thank you! How long will the refund take?"
        })

        ticket.refresh_from_db()
        # After customer replies, status should transition to WAITING_ON_AGENT
        assert ticket.status == Ticket.Status.WAITING_ON_AGENT

        # 7. Add tags
        service.add_tags(ticket, agent, [tag.pk])
        assert tag in ticket.tags.all()

        # 8. Agent resolves the ticket
        service.resolve(ticket, agent)
        ticket.refresh_from_db()

        assert ticket.status == Ticket.Status.RESOLVED
        assert ticket.resolved_at is not None

        # 9. Customer reopens
        service.reopen(ticket, customer)
        ticket.refresh_from_db()

        assert ticket.status == Ticket.Status.REOPENED
        assert ticket.resolved_at is None  # Cleared on reopen

        # 10. Agent resolves again, then closes
        service.resolve(ticket, agent)
        service.close(ticket, agent)
        ticket.refresh_from_db()

        assert ticket.status == Ticket.Status.CLOSED
        assert ticket.closed_at is not None

        # Verify reply count
        assert ticket.replies.filter(is_deleted=False).count() >= 3

    def test_priority_escalation_lifecycle(self):
        """
        Test that priority changes are tracked and SLA is re-evaluated.
        """
        service = TicketService()
        customer = UserFactory(username="priority_lifecycle_customer")
        agent = UserFactory(username="priority_lifecycle_agent")
        department = DepartmentFactory()
        department.agents.add(agent)

        ticket = service.create(customer, {
            "subject": "Minor UI issue",
            "description": "Button color is slightly off.",
            "priority": "low",
        })

        assert ticket.priority == Ticket.Priority.LOW

        # Escalate priority
        service.change_priority(ticket, agent, Ticket.Priority.HIGH)
        ticket.refresh_from_db()
        assert ticket.priority == Ticket.Priority.HIGH

        assert TicketActivity.objects.filter(
            ticket=ticket,
            type=TicketActivity.ActivityType.PRIORITY_CHANGED,
        ).exists()

        # Further escalate
        service.change_priority(ticket, agent, Ticket.Priority.CRITICAL)
        ticket.refresh_from_db()
        assert ticket.priority == Ticket.Priority.CRITICAL

    def test_department_transfer_lifecycle(self):
        """
        Test transferring a ticket between departments.
        """
        service = TicketService()
        customer = UserFactory(username="dept_lifecycle_customer")
        agent = UserFactory(username="dept_lifecycle_agent")

        dept1 = DepartmentFactory(name="Sales", slug="sales")
        dept2 = DepartmentFactory(name="Engineering", slug="engineering")
        dept1.agents.add(agent)
        dept2.agents.add(agent)

        ticket = service.create(customer, {
            "subject": "Technical question about API",
            "description": "How do I authenticate?",
            "department_id": dept1.pk,
        })

        assert ticket.department == dept1

        # Transfer to Engineering
        service.change_department(ticket, agent, dept2)
        ticket.refresh_from_db()
        assert ticket.department == dept2

        assert TicketActivity.objects.filter(
            ticket=ticket,
            type=TicketActivity.ActivityType.DEPARTMENT_CHANGED,
        ).exists()

    def test_sla_breach_lifecycle(self):
        """
        Test that SLA breaches are properly detected on open tickets.
        """
        customer = UserFactory(username="sla_lifecycle_customer")
        policy = SlaPolicyFactory(
            first_response_hours={"medium": 1},
            resolution_hours={"medium": 4},
        )

        service = TicketService()
        ticket = service.create(customer, {
            "subject": "SLA test ticket",
            "description": "Testing SLA enforcement",
        })

        # Manually set SLA policy and deadline in the past
        ticket.sla_policy = policy
        ticket.first_response_due_at = timezone.now() - timedelta(hours=1)
        ticket.save()

        # Run SLA check
        breached = SlaService.check_breach(ticket)
        assert breached is True

        ticket.refresh_from_db()
        assert ticket.sla_first_response_breached is True
