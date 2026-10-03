import uuid

import pytest

from escalated.mail.inbound_message import InboundMessage
from escalated.mail.message_id_util import build_reply_to
from escalated.models import Reply, Ticket
from escalated.services.inbound_email_service import InboundEmailService
from tests.factories import DepartmentFactory, TicketFactory, UserFactory

SECRET = "test-secret"
DOMAIN = "support.example.com"


@pytest.fixture
def escalated_settings(settings):
    settings.ESCALATED = {
        "NOTIFICATION_CHANNELS": [],
        "WEBHOOK_URL": None,
        "EMAIL_DOMAIN": DOMAIN,
        "EMAIL_INBOUND_SECRET": "",
    }
    return settings


@pytest.fixture
def with_secret(escalated_settings):
    escalated_settings.ESCALATED = {**escalated_settings.ESCALATED, "EMAIL_INBOUND_SECRET": SECRET}
    return escalated_settings


@pytest.fixture
def requester(db):
    return UserFactory(username="owner", email="owner@example.com")


def message(**overrides):
    attrs = {
        "from_email": "owner@example.com",
        "from_name": "Owner",
        "to_email": f"support@{DOMAIN}",
        "subject": "Question",
        "body_text": "Hello",
        "body_html": None,
        "message_id": f"<{uuid.uuid4().hex}@mail.example.net>",
    }
    attrs.update(overrides)
    return InboundMessage(**attrs)


def process(msg):
    return InboundEmailService.process(msg, adapter_name="mailgun")


@pytest.mark.django_db
class TestWithoutInboundSecret:
    def test_requester_reply_by_subject_reference_is_accepted(self, escalated_settings, requester):
        ticket = TicketFactory(requester=requester)

        inbound = process(message(from_email="Owner@Example.com", subject=f"RE: [{ticket.reference}] Question"))

        assert inbound.ticket_id == ticket.pk
        assert inbound.reply is not None
        assert inbound.reply.author == requester

    def test_guest_reply_threads_through_canonical_in_reply_to(self, escalated_settings):
        ticket = TicketFactory(guest_email="guest@example.com", guest_token="t" * 32)

        inbound = process(message(from_email="guest@example.com", in_reply_to=f"<ticket-{ticket.pk}@{DOMAIN}>"))

        assert inbound.ticket_id == ticket.pk
        assert inbound.reply is not None
        assert inbound.reply.author is None

    def test_stranger_quoting_subject_reference_gets_a_new_ticket(self, escalated_settings, requester):
        ticket = TicketFactory(requester=requester)

        inbound = process(message(from_email="stranger@example.net", subject=f"RE: [{ticket.reference}] Your order"))

        assert inbound.status == "processed"
        assert inbound.ticket_id != ticket.pk
        assert inbound.reply_id is None
        assert Reply.objects.filter(ticket=ticket).count() == 0
        assert Ticket.objects.get(pk=inbound.ticket_id).guest_email == "stranger@example.net"

    def test_stranger_threading_onto_closed_ticket_does_not_reopen_it(self, escalated_settings, requester):
        ticket = TicketFactory(requester=requester, status=Ticket.Status.CLOSED)

        inbound = process(
            message(
                from_email="stranger@example.net",
                subject=f"RE: [{ticket.reference}] Closed",
                in_reply_to=f"<ticket-{ticket.pk}@{DOMAIN}>",
            )
        )

        ticket.refresh_from_db()
        assert inbound.ticket_id != ticket.pk
        assert ticket.status == Ticket.Status.CLOSED
        assert Reply.objects.filter(ticket=ticket).count() == 0

    def test_requester_reply_reopens_closed_ticket(self, escalated_settings, requester):
        ticket = TicketFactory(requester=requester, status=Ticket.Status.CLOSED)

        inbound = process(message(subject=f"RE: [{ticket.reference}] Closed"))

        ticket.refresh_from_db()
        assert inbound.ticket_id == ticket.pk
        assert ticket.status == Ticket.Status.REOPENED


@pytest.mark.django_db
class TestWithInboundSecret:
    def test_spoofed_agent_from_is_not_posted_as_the_agent(self, with_secret, requester):
        agent = UserFactory(username="agent", email="agent@example.com")
        DepartmentFactory().agents.add(agent)
        ticket = TicketFactory(requester=requester)

        inbound = process(
            message(
                from_email="agent@example.com",
                to_email=build_reply_to(ticket.pk, SECRET, DOMAIN),
                subject=f"RE: [{ticket.reference}] Update",
                in_reply_to=f"<ticket-{ticket.pk}@{DOMAIN}>",
            )
        )

        assert inbound.ticket_id != ticket.pk
        assert Reply.objects.filter(ticket=ticket).count() == 0
        assert Reply.objects.filter(author=agent).count() == 0

    def test_signed_reply_to_is_required(self, with_secret, requester):
        ticket = TicketFactory(requester=requester)

        inbound = process(
            message(subject=f"RE: [{ticket.reference}] Question", in_reply_to=f"<ticket-{ticket.pk}@{DOMAIN}>")
        )

        assert inbound.ticket_id != ticket.pk
        assert Reply.objects.filter(ticket=ticket).count() == 0

    def test_forged_signature_is_rejected(self, with_secret, requester):
        ticket = TicketFactory(requester=requester)

        inbound = process(message(to_email=f"reply+{ticket.pk}.deadbeef@{DOMAIN}"))

        assert inbound.ticket_id != ticket.pk
        assert Reply.objects.filter(ticket=ticket).count() == 0

    def test_signed_requester_reply_is_accepted_and_reopens(self, with_secret, requester):
        ticket = TicketFactory(requester=requester, status=Ticket.Status.RESOLVED)

        inbound = process(message(from_email="Owner@Example.com", to_email=build_reply_to(ticket.pk, SECRET, DOMAIN)))

        ticket.refresh_from_db()
        assert inbound.ticket_id == ticket.pk
        assert inbound.reply.author == requester
        assert ticket.status == Ticket.Status.REOPENED
