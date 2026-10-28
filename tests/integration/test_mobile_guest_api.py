"""The mobile guest API under ``<API_PREFIX>/mobile/guest/``.

Canonical contract: escalated-developer-context ``domain-model/mobile-guest-api.md``.
Every request goes through the real URLconf, middleware and views.
"""

import importlib
import json
import re
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import Resolver404, clear_url_caches, resolve
from django.utils import timezone

from escalated import guest_access
from escalated.models import Attachment, Contact, EscalatedSetting, Reply, Ticket
from tests.factories import DepartmentFactory, ReplyFactory, TicketFactory, UserFactory
from tests.guest_proof import grant, proof

MOBILE = "/support/support/api/v1/mobile/guest"
EMAIL = "ann@example.com"


@pytest.fixture(autouse=True)
def _db(db):
    yield


def post_json(client, url, body, **extra):
    return client.post(url, data=json.dumps(body), content_type="application/json", **extra)


def emailed_code():
    assert mail.outbox, "no verification email was sent"
    return re.search(r"\b(\d{8})\b", mail.outbox[-1].body).group(1)


def ticket_body(**fields):
    return {"name": "Ann", "email": EMAIL, "subject": "Help", "description": "Broken", **fields}


def create(client, **fields):
    return post_json(client, f"{MOBILE}/tickets", ticket_body(**proof(EMAIL), **fields))


def assert_private(response):
    assert response["Cache-Control"] == "private, no-store"
    assert response["Referrer-Policy"] == "no-referrer"


class TestCreate:
    def test_create_without_proof_is_422_and_creates_nothing(self):
        response = post_json(Client(), f"{MOBILE}/tickets", ticket_body())
        assert response.status_code == 422
        assert "verification_code" in response.json()["errors"]
        assert "verification_id" in response.json()["errors"]
        assert not Ticket.objects.exists() and not Contact.objects.exists()
        assert_private(response)

    def test_a_wrong_code_creates_nothing(self):
        body = ticket_body(**{**proof(EMAIL), "verification_code": "00000000"})
        response = post_json(Client(), f"{MOBILE}/tickets", body)
        assert response.status_code == 422
        assert "verification_code" in response.json()["errors"]
        assert not Ticket.objects.exists() and not Contact.objects.exists()

    def test_verification_then_create_returns_a_grant_and_the_code_is_spent(self):
        client = Client()
        requested = post_json(client, f"{MOBILE}/verification", {"email": EMAIL, "purpose": "ticket"})
        assert requested.status_code == 202, requested.content
        assert_private(requested)
        verification = {"verification_id": requested.json()["verification_id"], "verification_code": emailed_code()}
        body = ticket_body(email="  Ann@Example.com ", priority="high", **verification)

        response = post_json(client, f"{MOBILE}/tickets", body)
        assert response.status_code == 201, response.content
        assert_private(response)
        payload = response.json()
        assert payload["message"] == "Ticket created."
        data = payload["data"]
        ticket = Ticket.objects.get()
        assert data["id"] == ticket.pk and data["reference"] == ticket.reference
        assert data["guest_access_token"] and data["guest_access_expires_at"]
        assert data["status"] == {"value": "open", "label": "Open"}
        assert data["priority"] == {"value": "high", "label": "High"}
        assert data["channel"] == "web"
        assert data["metadata"] == {}
        assert data["requester"] == {"name": "Ann", "email": EMAIL}
        assert data["replies"] == [] and data["tags"] == [] and data["activities"] == []
        assert data["is_following"] is False and data["followers_count"] == 0
        assert set(data["sla"]) == {
            "first_response_due_at",
            "first_response_at",
            "first_response_breached",
            "resolution_due_at",
            "resolution_breached",
        }
        assert ticket.guest_email == EMAIL and ticket.channel == "web"
        assert guest_access.verified(ticket)
        assert Contact.objects.get().email == EMAIL

        again = post_json(client, f"{MOBILE}/tickets", body)
        assert again.status_code == 422
        assert "verification_code" in again.json()["errors"]
        assert Ticket.objects.count() == 1

    def test_unknown_and_privileged_fields_are_ignored(self):
        response = create(
            Client(), metadata={"vip": True}, external_reference="X-1", status="closed", assigned_to=1, channel="api"
        )
        assert response.status_code == 201, response.content
        ticket = Ticket.objects.get()
        assert ticket.metadata in (None, {}) and ticket.status == "open" and ticket.assigned_to_id is None
        assert ticket.channel == "web"

    def test_default_priority_and_department(self):
        department = DepartmentFactory()
        response = create(Client(), department_id=department.pk)
        assert response.status_code == 201, response.content
        data = response.json()["data"]
        assert data["priority"]["value"] == "medium"
        assert data["department"] == {"id": department.pk, "name": department.name}

    def test_field_validation(self):
        response = create(Client(), name="", priority="whenever", department_id=999999, email="nope")
        assert response.status_code == 422
        assert {"name", "priority", "department_id", "email"} <= set(response.json()["errors"])
        response = post_json(
            Client(), f"{MOBILE}/tickets", ticket_body(verification_id="not-a-uuid", verification_code="1")
        )
        assert "verification_id" in response.json()["errors"]

    def test_disabled_guest_tickets_is_403_before_validation(self):
        EscalatedSetting.set("guest_tickets_enabled", "0")
        response = post_json(Client(), f"{MOBILE}/tickets", {})
        assert response.status_code == 403
        assert response.json() == {"message": "Guest tickets are not enabled."}
        assert_private(response)

    def test_multipart_create_with_attachments(self, tmp_path):
        body = ticket_body(**proof(EMAIL))
        body["attachments"] = [SimpleUploadedFile("a.txt", b"hello", content_type="text/plain")]
        with override_settings(MEDIA_ROOT=str(tmp_path)):
            response = Client().post(f"{MOBILE}/tickets", data=body)
        assert response.status_code == 201, response.content
        ticket = Ticket.objects.get()
        assert Attachment.objects.filter(
            content_type=ContentType.objects.get_for_model(Ticket), object_id=ticket.pk
        ).exists()


class TestShow:
    def test_the_mobile_grant_opens_mobile_browser_and_widget_routes(self):
        client = Client()
        token = create(client).json()["data"]["guest_access_token"]
        ticket = Ticket.objects.get()

        response = client.get(f"{MOBILE}/tickets/{token}")
        assert response.status_code == 200, response.content
        assert_private(response)
        data = response.json()["data"]
        assert data["reference"] == ticket.reference
        assert data["guest_access_token"] == token
        assert client.get(f"/support/guest/{token}/", HTTP_X_INERTIA="true").status_code == 200
        EscalatedSetting.set("widget_enabled", "1")
        widget = client.get(f"/support/widget/tickets/{ticket.reference}", HTTP_AUTHORIZATION=f"Bearer {token}")
        assert widget.status_code == 200

    def test_a_widget_or_lookup_grant_opens_the_mobile_route(self):
        ticket = TicketFactory(guest_email=EMAIL, guest_name="Ann")
        response = post_json(
            Client(),
            f"{MOBILE}/lookup",
            {"email": EMAIL, "reference": ticket.reference, **proof(EMAIL, "lookup")},
        )
        assert response.status_code == 200, response.content
        assert_private(response)
        [match] = response.json()["data"]
        assert Client().get(f"{MOBILE}/tickets/{match['guest_access_token']}").status_code == 200

    def test_public_replies_newest_first_without_internal_notes(self):
        ticket = TicketFactory(guest_email=EMAIL, guest_name="Ann")
        agent = UserFactory(first_name="Sam", last_name="Agent", email="sam@corp.example")
        ReplyFactory(ticket=ticket, author=agent, body="first answer")
        ReplyFactory(ticket=ticket, author=None, body="guest says")
        ReplyFactory(ticket=ticket, author=agent, body="secret note", is_internal_note=True)
        ReplyFactory(ticket=ticket, author=agent, body="deleted", is_deleted=True)
        Reply.objects.filter(body="guest says").update(created_at=timezone.now() + timedelta(minutes=1))
        ticket.assigned_to = agent
        ticket.metadata = {"crm": "secret"}
        ticket.save()

        response = Client().get(f"{MOBILE}/tickets/{grant(ticket)}")
        assert response.status_code == 200
        content = response.content.decode()
        assert "secret note" not in content and "deleted" not in content
        assert "sam@corp.example" not in content and "crm" not in content
        data = response.json()["data"]
        assert [r["body"] for r in data["replies"]] == ["guest says", "first answer"]
        assert data["replies"][0]["author"] == {"id": 0, "name": "Ann", "email": EMAIL}
        assert data["replies"][1]["author"] == {"id": 0, "name": "Sam Agent", "email": ""}
        assert all(r["is_internal_note"] is False for r in data["replies"])
        assert data["assignee"] == {"id": 0, "name": "Sam Agent", "email": ""}
        assert data["metadata"] == {}

    def test_reply_attachment_urls_carry_the_guest_capability(self, tmp_path):
        from django.core.files.base import ContentFile

        ticket = TicketFactory(guest_email=EMAIL)
        reply = ReplyFactory(ticket=ticket, author=None, body="see file")
        with override_settings(MEDIA_ROOT=str(tmp_path)):
            Attachment.objects.create(
                content_type=ContentType.objects.get_for_model(reply),
                object_id=reply.pk,
                file=ContentFile(b"hello", name="a.txt"),
                original_filename="a.txt",
                mime_type="text/plain",
                size=5,
            )
            data = Client().get(f"{MOBILE}/tickets/{grant(ticket)}").json()["data"]
            [attachment] = data["replies"][0]["attachments"]
            assert attachment["filename"] == "a.txt" and attachment["mime_type"] == "text/plain"
            assert attachment["size"] == 5
            assert Client().get(attachment["url"]).status_code == 200

    def test_bad_expired_and_chat_grants_are_404(self):
        ticket = TicketFactory(guest_email=EMAIL)
        token = grant(ticket)
        client = Client()
        for bad in ("nope", "x" * 5000, token + "x"):
            response = client.get(f"{MOBILE}/tickets/{bad}")
            assert response.status_code == 404
            assert_private(response)

        from django.core import signing

        claims = signing.loads(token, salt=guest_access.GRANT_SALT)
        chat = signing.dumps({**claims, "p": "chat"}, salt=guest_access.GRANT_SALT, compress=True)
        assert client.get(f"{MOBILE}/tickets/{chat}").status_code == 404
        assert post_json(client, f"{MOBILE}/tickets/{chat}/replies", {"email": EMAIL, "body": "hi"}).status_code == 404

        later = time.time() + 25 * 3600
        with (
            patch("escalated.guest_access.time.time", return_value=later),
            patch("escalated.guest_access.timezone.now", return_value=timezone.now() + timedelta(hours=25)),
        ):
            assert client.get(f"{MOBILE}/tickets/{token}").status_code == 404
            expired = post_json(client, f"{MOBILE}/tickets/{token}/replies", {"email": EMAIL, "body": "hi"})
            assert expired.status_code == 404


class TestReply:
    def test_a_differently_cased_matching_email_replies(self):
        ticket = TicketFactory(guest_email=EMAIL, status=Ticket.Status.WAITING_ON_CUSTOMER)
        response = post_json(
            Client(), f"{MOBILE}/tickets/{grant(ticket)}/replies", {"email": " ANN@example.COM", "body": "Thanks"}
        )
        assert response.status_code == 201, response.content
        assert response.json() == {"message": "Reply sent."}
        assert_private(response)
        reply = Reply.objects.get(ticket=ticket)
        assert reply.body == "Thanks" and reply.author_id is None and reply.is_internal_note is False
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.OPEN  # the normal reply handling ran

    def test_a_mismatched_email_is_403(self):
        ticket = TicketFactory(guest_email=EMAIL)
        response = post_json(
            Client(), f"{MOBILE}/tickets/{grant(ticket)}/replies", {"email": "eve@example.com", "body": "hi"}
        )
        assert response.status_code == 403
        assert response.json() == {"message": "The provided email does not match this ticket."}
        assert not Reply.objects.exists()

    def test_a_closed_ticket_is_422(self):
        ticket = TicketFactory(guest_email=EMAIL, status=Ticket.Status.CLOSED)
        response = post_json(Client(), f"{MOBILE}/tickets/{grant(ticket)}/replies", {"email": EMAIL, "body": "hi"})
        assert response.status_code == 422
        assert response.json() == {"message": "This ticket is closed."}

    def test_validation(self):
        ticket = TicketFactory(guest_email=EMAIL)
        response = post_json(Client(), f"{MOBILE}/tickets/{grant(ticket)}/replies", {"email": "", "body": ""})
        assert response.status_code == 422
        assert {"email", "body"} <= set(response.json()["errors"])

    def test_multipart_reply_with_attachment(self, tmp_path):
        ticket = TicketFactory(guest_email=EMAIL)
        upload = SimpleUploadedFile("b.txt", b"hello", content_type="text/plain")
        with override_settings(MEDIA_ROOT=str(tmp_path)):
            response = Client().post(
                f"{MOBILE}/tickets/{grant(ticket)}/replies",
                data={"email": EMAIL, "body": "file", "attachments": [upload]},
            )
        assert response.status_code == 201, response.content
        reply = Reply.objects.get()
        assert reply.attachments.count() == 1


class TestRateLimits:
    def test_guest_submission_limit_answers_429_with_retry_after(self):
        client = Client()
        with override_settings(ESCALATED={"API_ENABLED": True, "GUEST_RATE_LIMIT": {"TICKETS_PER_MINUTE": 1}}):
            assert post_json(client, f"{MOBILE}/tickets", ticket_body()).status_code == 422
            blocked = post_json(client, f"{MOBILE}/tickets", ticket_body())
        assert blocked.status_code == 429
        assert int(blocked["Retry-After"]) > 0
        assert_private(blocked)

    def test_submission_budget_is_shared_with_the_widget(self):
        EscalatedSetting.set("widget_enabled", "1")
        client = Client()
        with override_settings(ESCALATED={"API_ENABLED": True, "GUEST_RATE_LIMIT": {"TICKETS_PER_MINUTE": 1}}):
            post_json(client, "/support/widget/tickets", ticket_body())
            assert post_json(client, f"{MOBILE}/tickets", ticket_body()).status_code == 429

    def test_every_route_counts_against_the_request_budget(self):
        ticket = TicketFactory(guest_email=EMAIL)
        token = grant(ticket)
        client = Client()
        with override_settings(ESCALATED={"API_ENABLED": True, "GUEST_RATE_LIMIT": {"REQUESTS_PER_MINUTE": 2}}):
            assert client.get(f"{MOBILE}/tickets/{token}").status_code == 200
            assert client.get(f"{MOBILE}/tickets/{token}").status_code == 200
            blocked = client.get(f"{MOBILE}/tickets/{token}")
        assert blocked.status_code == 429 and int(blocked["Retry-After"]) > 0

    def test_reply_limit_is_shared_with_lookup(self):
        ticket = TicketFactory(guest_email=EMAIL)
        token = grant(ticket)
        client = Client()
        with override_settings(ESCALATED={"API_ENABLED": True, "GUEST_RATE_LIMIT": {"REPLIES_PER_MINUTE": 1}}):
            post_json(client, f"{MOBILE}/lookup", {"email": EMAIL, "reference": ticket.reference})
            blocked = post_json(client, f"{MOBILE}/tickets/{token}/replies", {"email": EMAIL, "body": "hi"})
        assert blocked.status_code == 429

    def test_the_api_limiter_covers_the_mobile_guest_routes(self):
        from django.core.cache import cache

        stack = [
            "django.middleware.common.CommonMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "escalated.api_middleware.AuthenticateApiToken",
            "escalated.api_middleware.ApiRateLimit",
        ]
        ticket = TicketFactory(guest_email=EMAIL)
        token = grant(ticket)
        with override_settings(MIDDLEWARE=stack):
            # Guest routes carry no API token: the token middleware lets them through.
            assert Client().get(f"{MOBILE}/tickets/{token}").status_code == 200
            cache.set("escalated_api:127.0.0.1", 60, 60)
            blocked = Client().get(f"{MOBILE}/tickets/{token}")
        assert blocked.status_code == 429
        assert blocked.json()["message"] == "Too many requests."
        assert blocked["Retry-After"]


def _reload_urls():
    import escalated.urls
    import tests.urls

    importlib.reload(escalated.urls)
    importlib.reload(tests.urls)
    clear_url_caches()


def test_routes_do_not_exist_while_the_api_is_disabled():
    try:
        with override_settings(ESCALATED={"API_ENABLED": False}):
            _reload_urls()
            for suffix in ("verification", "lookup", "tickets", "tickets/abc", "tickets/abc/replies"):
                with pytest.raises(Resolver404):
                    resolve(f"{MOBILE}/{suffix}")
    finally:
        _reload_urls()
    assert resolve(f"{MOBILE}/tickets").url_name == "mobile_guest_tickets"
