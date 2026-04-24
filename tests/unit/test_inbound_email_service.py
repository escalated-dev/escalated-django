"""
Tests for InboundEmailService._find_existing_ticket resolution order.

Verifies that the MessageIdUtil wire-up resolves canonical
Message-IDs out of In-Reply-To / References and verifies signed
Reply-To addresses on the recipient.
"""

from __future__ import annotations

import pytest

from escalated.mail.inbound_message import InboundMessage
from escalated.mail.message_id_util import build_reply_to
from escalated.models import Ticket
from escalated.services.inbound_email_service import InboundEmailService
from tests.factories import TicketFactory


def _message(**overrides) -> InboundMessage:
    defaults: dict = {
        "from_email": "customer@example.com",
        "from_name": "Customer",
        "to_email": "support@example.com",
        "subject": "hello",
        "body_text": "body",
        "body_html": None,
    }
    return InboundMessage(**{**defaults, **overrides})


@pytest.mark.django_db
class TestFindExistingTicket:
    def test_in_reply_to_canonical_message_id(self):
        ticket: Ticket = TicketFactory()
        message = _message(in_reply_to=f"<ticket-{ticket.pk}@support.example.com>")

        found = InboundEmailService._find_existing_ticket(message)
        assert found == ticket

    def test_references_canonical_message_id(self):
        ticket: Ticket = TicketFactory()
        message = _message(references=f"<unrelated@mail.com> <ticket-{ticket.pk}@support.example.com>")

        found = InboundEmailService._find_existing_ticket(message)
        assert found == ticket

    def test_signed_reply_to_when_secret_configured(self, settings):
        settings.ESCALATED = {
            "EMAIL_DOMAIN": "support.example.com",
            "EMAIL_INBOUND_SECRET": "test-secret",
        }
        ticket: Ticket = TicketFactory()
        to = build_reply_to(ticket.pk, "test-secret", "support.example.com")
        message = _message(to_email=to)

        found = InboundEmailService._find_existing_ticket(message)
        assert found == ticket

    def test_forged_reply_to_is_rejected(self, settings):
        settings.ESCALATED = {
            "EMAIL_DOMAIN": "support.example.com",
            "EMAIL_INBOUND_SECRET": "real-secret",
        }
        ticket: Ticket = TicketFactory()
        # Signed with a DIFFERENT secret.
        forged = build_reply_to(ticket.pk, "wrong-secret", "support.example.com")
        message = _message(to_email=forged)

        found = InboundEmailService._find_existing_ticket(message)
        assert found is None

    def test_signed_reply_to_ignored_when_secret_blank(self, settings):
        settings.ESCALATED = {
            "EMAIL_DOMAIN": "support.example.com",
            "EMAIL_INBOUND_SECRET": "",
        }
        ticket: Ticket = TicketFactory()
        to = build_reply_to(ticket.pk, "test-secret", "support.example.com")
        message = _message(to_email=to)

        found = InboundEmailService._find_existing_ticket(message)
        assert found is None

    def test_subject_reference_tag(self):
        ticket: Ticket = TicketFactory()
        # Subject referencing whatever reference the factory generated.
        message = _message(subject=f"RE: [{ticket.reference}] foo")

        found = InboundEmailService._find_existing_ticket(message)
        assert found == ticket

    def test_nothing_matches_returns_none(self):
        message = _message(subject="New issue")

        found = InboundEmailService._find_existing_ticket(message)
        assert found is None
