import pytest
from django.core import mail

from escalated.mail.threading import (
    get_branding_context,
    get_email_domain,
    get_threading_headers,
    make_message_id,
    make_reply_message_id,
)
from escalated.models import EscalatedSetting
from escalated.services.notification_service import NotificationService
from tests.factories import ReplyFactory, TicketFactory, UserFactory


@pytest.mark.django_db
class TestEmailDomain:
    def test_default_domain_from_settings(self):
        domain = get_email_domain()
        # Falls back to DEFAULT_FROM_EMAIL or "escalated.dev"
        assert domain

    def test_custom_domain_from_setting(self):
        EscalatedSetting.set("email_domain", "custom.example.com")
        assert get_email_domain() == "custom.example.com"


@pytest.mark.django_db
class TestMessageId:
    def test_make_message_id_format(self):
        ticket = TicketFactory()
        msg_id = make_message_id(ticket)
        assert msg_id.startswith("<ticket-")
        assert ticket.reference in msg_id
        assert msg_id.endswith(">")

    def test_make_reply_message_id_format(self):
        ticket = TicketFactory()
        reply = ReplyFactory(ticket=ticket)
        msg_id = make_reply_message_id(ticket, reply)
        assert f"reply-{reply.pk}" in msg_id
        assert msg_id.startswith("<ticket-")
        assert msg_id.endswith(">")

    def test_message_ids_are_unique(self):
        ticket = TicketFactory()
        reply1 = ReplyFactory(ticket=ticket)
        reply2 = ReplyFactory(ticket=ticket)
        assert make_reply_message_id(ticket, reply1) != make_reply_message_id(ticket, reply2)


@pytest.mark.django_db
class TestThreadingHeaders:
    def test_new_ticket_headers(self):
        ticket = TicketFactory()
        headers = get_threading_headers(ticket, reply=None)
        assert "Message-ID" in headers
        assert "In-Reply-To" not in headers
        assert "References" not in headers

    def test_reply_headers(self):
        ticket = TicketFactory()
        reply = ReplyFactory(ticket=ticket)
        headers = get_threading_headers(ticket, reply=reply)

        assert "Message-ID" in headers
        assert "In-Reply-To" in headers
        assert "References" in headers

        # In-Reply-To and References should point to the ticket's message ID
        ticket_msg_id = make_message_id(ticket)
        assert headers["In-Reply-To"] == ticket_msg_id
        assert headers["References"] == ticket_msg_id

    def test_reply_message_id_differs_from_ticket(self):
        ticket = TicketFactory()
        reply = ReplyFactory(ticket=ticket)
        headers = get_threading_headers(ticket, reply=reply)
        ticket_headers = get_threading_headers(ticket, reply=None)
        assert headers["Message-ID"] != ticket_headers["Message-ID"]


@pytest.mark.django_db
class TestBrandingContext:
    def test_default_branding(self):
        ctx = get_branding_context()
        assert ctx["email_accent_color"] == "#4f46e5"
        assert ctx["email_footer_text"]  # Has a default
        assert ctx["email_logo_url"] == ""

    def test_custom_branding(self):
        EscalatedSetting.set("email_logo_url", "https://example.com/logo.png")
        EscalatedSetting.set("email_accent_color", "#ff0000")
        EscalatedSetting.set("email_footer_text", "Custom footer")

        ctx = get_branding_context()
        assert ctx["email_logo_url"] == "https://example.com/logo.png"
        assert ctx["email_accent_color"] == "#ff0000"
        assert ctx["email_footer_text"] == "Custom footer"


@pytest.mark.django_db
class TestNotificationServiceThreading:
    def test_ticket_created_has_message_id(self, settings):
        settings.ESCALATED = {"NOTIFICATION_CHANNELS": ["email"], "WEBHOOK_URL": None}
        user = UserFactory()
        ticket = TicketFactory(requester=user)

        NotificationService.notify_ticket_created(ticket)

        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert "Message-ID" in msg.extra_headers
        assert ticket.reference in msg.extra_headers["Message-ID"]

    def test_reply_has_threading_headers(self, settings):
        settings.ESCALATED = {"NOTIFICATION_CHANNELS": ["email"], "WEBHOOK_URL": None}
        user = UserFactory()
        ticket = TicketFactory(requester=user)
        agent = UserFactory(username="agent_threading")
        ticket.assigned_to = agent
        ticket.save()

        reply = ReplyFactory(ticket=ticket, author=agent)

        NotificationService.notify_reply_added(ticket, reply)

        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert "In-Reply-To" in msg.extra_headers
        assert "References" in msg.extra_headers
        assert ticket.reference in msg.extra_headers["In-Reply-To"]
