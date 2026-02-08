import pytest
from datetime import timedelta

from django.utils import timezone

from escalated.models import Ticket, Reply, SlaPolicy, Tag, Department
from tests.factories import (
    UserFactory,
    TicketFactory,
    ReplyFactory,
    SlaPolicyFactory,
    TagFactory,
    DepartmentFactory,
)


@pytest.mark.django_db
class TestTicketModel:
    def test_ticket_generates_reference_on_save(self):
        ticket = TicketFactory()
        assert ticket.reference is not None
        assert ticket.reference.startswith("ESC-")
        assert len(ticket.reference) == 10  # ESC- + 6 chars

    def test_ticket_reference_is_unique(self):
        ticket1 = TicketFactory()
        ticket2 = TicketFactory()
        assert ticket1.reference != ticket2.reference

    def test_ticket_default_status_is_open(self):
        ticket = TicketFactory()
        assert ticket.status == Ticket.Status.OPEN

    def test_ticket_default_priority_is_medium(self):
        ticket = TicketFactory()
        assert ticket.priority == Ticket.Priority.MEDIUM

    def test_ticket_is_open_property(self):
        ticket = TicketFactory(status=Ticket.Status.OPEN)
        assert ticket.is_open is True

        ticket.status = Ticket.Status.IN_PROGRESS
        assert ticket.is_open is True

        ticket.status = Ticket.Status.ESCALATED
        assert ticket.is_open is True

        ticket.status = Ticket.Status.CLOSED
        assert ticket.is_open is False

        ticket.status = Ticket.Status.RESOLVED
        assert ticket.is_open is False

    def test_ticket_is_resolved_property(self):
        ticket = TicketFactory(status=Ticket.Status.RESOLVED)
        assert ticket.is_resolved is True

        ticket.status = Ticket.Status.OPEN
        assert ticket.is_resolved is False

    def test_ticket_is_closed_property(self):
        ticket = TicketFactory(status=Ticket.Status.CLOSED)
        assert ticket.is_closed is True

        ticket.status = Ticket.Status.OPEN
        assert ticket.is_closed is False

    def test_ticket_str_representation(self):
        ticket = TicketFactory(subject="Test Subject")
        assert ticket.subject in str(ticket)
        assert ticket.reference in str(ticket)

    def test_ticket_queryset_open(self):
        open_ticket = TicketFactory(status=Ticket.Status.OPEN)
        in_progress = TicketFactory(status=Ticket.Status.IN_PROGRESS)
        closed_ticket = TicketFactory(status=Ticket.Status.CLOSED)
        resolved_ticket = TicketFactory(status=Ticket.Status.RESOLVED)

        open_tickets = Ticket.objects.open()
        assert open_ticket in open_tickets
        assert in_progress in open_tickets
        assert closed_ticket not in open_tickets
        assert resolved_ticket not in open_tickets

    def test_ticket_queryset_unassigned(self):
        agent = UserFactory(username="test_agent")
        unassigned = TicketFactory(assigned_to=None)
        assigned = TicketFactory(assigned_to=agent)

        result = Ticket.objects.unassigned()
        assert unassigned in result
        assert assigned not in result

    def test_ticket_queryset_assigned_to(self):
        agent = UserFactory(username="assigned_agent")
        ticket = TicketFactory(assigned_to=agent)
        other_ticket = TicketFactory()

        result = Ticket.objects.assigned_to(agent.pk)
        assert ticket in result
        assert other_ticket not in result

    def test_ticket_queryset_search(self):
        ticket = TicketFactory(subject="Payment issue with order")
        other_ticket = TicketFactory(subject="General inquiry")

        result = Ticket.objects.search("Payment")
        assert ticket in result
        assert other_ticket not in result

    def test_ticket_queryset_breached_sla(self):
        breached = TicketFactory(sla_first_response_breached=True)
        normal = TicketFactory()

        result = Ticket.objects.breached_sla()
        assert breached in result
        assert normal not in result

    def test_ticket_sla_remaining_with_no_deadline(self):
        ticket = TicketFactory()
        assert ticket.sla_first_response_remaining is None
        assert ticket.sla_resolution_remaining is None

    def test_ticket_sla_remaining_with_deadline(self):
        now = timezone.now()
        ticket = TicketFactory(
            first_response_due_at=now + timedelta(hours=2),
            resolution_due_at=now + timedelta(hours=8),
        )
        remaining = ticket.sla_first_response_remaining
        assert remaining is not None
        assert remaining.total_seconds() > 0

    def test_ticket_with_requester(self):
        user = UserFactory(username="requester_test")
        ticket = TicketFactory(requester=user)
        assert ticket.requester == user
        assert ticket.requester_object_id == user.pk

    def test_ticket_tags_m2m(self):
        ticket = TicketFactory()
        tag1 = TagFactory(name="Bug", slug="bug")
        tag2 = TagFactory(name="Feature", slug="feature")
        ticket.tags.add(tag1, tag2)

        assert ticket.tags.count() == 2
        assert tag1 in ticket.tags.all()


@pytest.mark.django_db
class TestReplyModel:
    def test_reply_default_type_is_reply(self):
        reply = ReplyFactory()
        assert reply.type == Reply.Type.REPLY

    def test_reply_internal_note(self):
        reply = ReplyFactory(is_internal_note=True, type=Reply.Type.NOTE)
        assert reply.is_internal_note is True
        assert reply.type == Reply.Type.NOTE

    def test_reply_soft_delete(self):
        reply = ReplyFactory()
        assert reply.is_deleted is False

        reply.soft_delete()
        reply.refresh_from_db()
        assert reply.is_deleted is True

    def test_reply_str_representation(self):
        reply = ReplyFactory()
        assert reply.ticket.reference in str(reply)

    def test_reply_ordering(self):
        ticket = TicketFactory()
        reply1 = ReplyFactory(ticket=ticket)
        reply2 = ReplyFactory(ticket=ticket)

        replies = list(ticket.replies.all())
        assert replies[0].pk == reply1.pk
        assert replies[1].pk == reply2.pk


@pytest.mark.django_db
class TestSlaPolicyModel:
    def test_sla_policy_get_first_response_hours(self):
        policy = SlaPolicyFactory(
            first_response_hours={
                "low": 24,
                "medium": 8,
                "high": 4,
                "urgent": 1,
                "critical": 0.5,
            }
        )
        assert policy.get_first_response_hours("low") == 24
        assert policy.get_first_response_hours("critical") == 0.5
        assert policy.get_first_response_hours("nonexistent") is None

    def test_sla_policy_get_resolution_hours(self):
        policy = SlaPolicyFactory(
            resolution_hours={
                "low": 72,
                "medium": 24,
                "high": 8,
            }
        )
        assert policy.get_resolution_hours("medium") == 24
        assert policy.get_resolution_hours("nonexistent") is None

    def test_sla_policy_str_representation(self):
        policy = SlaPolicyFactory(name="Standard SLA")
        assert str(policy) == "Standard SLA"


@pytest.mark.django_db
class TestTagModel:
    def test_tag_str_representation(self):
        tag = TagFactory(name="Bug")
        assert str(tag) == "Bug"

    def test_tag_default_color(self):
        tag = TagFactory()
        assert tag.color == "#6b7280"


@pytest.mark.django_db
class TestDepartmentModel:
    def test_department_str_representation(self):
        dept = DepartmentFactory(name="Engineering")
        assert str(dept) == "Engineering"

    def test_department_agents_m2m(self):
        dept = DepartmentFactory()
        agent1 = UserFactory(username="agent_1")
        agent2 = UserFactory(username="agent_2")
        dept.agents.add(agent1, agent2)

        assert dept.agents.count() == 2
        assert agent1 in dept.agents.all()
