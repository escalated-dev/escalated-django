"""Verified guest access: email codes, expiring hashed grants, verification and lookup.

Mirrors escalated-laravel's docs/guest-access.md through the real HTTP routes.
"""

import json
import re
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import Client, override_settings
from django.utils import timezone

from escalated import guest_access
from escalated.models import Attachment, ChatSession, GuestVerification, Ticket
from tests.factories import TicketFactory
from tests.guest_proof import grant, proof

INERTIA = {"HTTP_X_INERTIA": "true"}
EMAIL = "ann@example.com"
VERIFICATION_URLS = [
    "/support/guest/verification",
    "/support/widget/verification",
    "/support/support/api/v1/mobile/guest/verification",
]
LOOKUP_URLS = ["/support/guest/lookup", "/support/widget/lookup", "/support/support/api/v1/mobile/guest/lookup"]


@pytest.fixture(autouse=True)
def clean_cache(widget_on):
    cache.clear()
    yield
    cache.clear()


def post_json(client, url, body, **extra):
    return client.post(url, data=json.dumps(body), content_type="application/json", **extra)


def emailed_code():
    assert mail.outbox, "no verification email was sent"
    return re.search(r"\b(\d{8})\b", mail.outbox[-1].body).group(1)


def request_code(client, url="/support/guest/verification", email=EMAIL, purpose="ticket", ip="10.0.0.1"):
    return post_json(client, url, {"email": email, "purpose": purpose}, REMOTE_ADDR=ip)


def guest_create(client, fields, email=EMAIL):
    body = {"guest_name": "Ann", "guest_email": email, "subject": "Help", "description": "Broken", **fields}
    return post_json(client, "/support/guest/store/", body, **INERTIA)


@pytest.mark.django_db
class TestVerification:
    @pytest.mark.parametrize("url", VERIFICATION_URLS)
    def test_each_surface_emails_an_eight_digit_code(self, url):
        response = request_code(Client(), url=url)
        assert response.status_code == 202, response.content
        data = response.json()
        assert data["expires_in"] == 600
        assert re.fullmatch(r"[0-9a-f-]{36}", data["verification_id"])
        assert mail.outbox[-1].to == [EMAIL]
        code = emailed_code()
        assert code not in response.content.decode()
        stored = GuestVerification.objects.get(pk=data["verification_id"])
        assert code not in stored.code_hash and EMAIL not in stored.email_digest
        assert response["Cache-Control"].startswith("no-store")

    def test_invalid_email_and_purpose_are_rejected(self):
        client = Client()
        assert post_json(client, VERIFICATION_URLS[0], {"email": "nope", "purpose": "ticket"}).status_code == 422
        assert post_json(client, VERIFICATION_URLS[0], {"email": EMAIL, "purpose": "admin"}).status_code == 422

    def test_chat_codes_need_chat_enabled(self):
        from escalated.models import EscalatedSetting

        EscalatedSetting.set("chat_enabled", "0")
        assert request_code(Client(), purpose="chat").status_code == 403

    def test_three_codes_per_mailbox_per_client_per_hour(self):
        client = Client()
        for _ in range(3):
            assert request_code(client, ip="10.0.0.1").status_code == 202
        blocked = request_code(client, ip="10.0.0.1")
        assert blocked.status_code == 429
        assert int(blocked["Retry-After"]) > 0
        # Another client still has its own budget for the same mailbox.
        assert request_code(client, ip="10.0.0.2").status_code == 202

    def test_ten_codes_per_mailbox_per_hour_across_clients(self):
        client = Client()
        with override_settings(ESCALATED={"GUEST_RATE_LIMIT": {"ENABLED": False}}):
            for n in range(10):
                assert request_code(client, ip=f"10.0.1.{n}").status_code == 202
            assert request_code(client, ip="10.0.2.1").status_code == 429


@pytest.mark.django_db
class TestGuestPortal:
    def test_create_page_offers_verification_and_lookup(self):
        response = Client().get("/support/guest/create/", **INERTIA)
        props = response.json()["props"]
        assert props["verification_url"] == "/support/guest/verification"
        assert props["lookup_url"] == "/support/guest/lookup"

    def test_ticket_needs_a_code(self):
        response = guest_create(Client(), {})
        assert response.status_code == 200
        assert "verification_code" in response.json()["props"]["errors"]
        assert not Ticket.objects.exists()

    def test_emailed_code_creates_the_ticket_and_a_private_expiring_link(self):
        client = Client()
        verification_id = request_code(client).json()["verification_id"]
        response = guest_create(client, {"verification_id": verification_id, "verification_code": emailed_code()})
        assert response.status_code == 302
        ticket = Ticket.objects.get()
        assert ticket.guest_token is None
        assert ticket.guest_access_hash and len(ticket.guest_access_hash) == 64
        token = response["Location"].split("/support/guest/")[1].rstrip("/")
        assert ticket.guest_access_hash not in token
        assert ticket.guest_access_expires_at - timezone.now() > timedelta(hours=23)

        page = client.get(response["Location"], **INERTIA)
        assert page.status_code == 200
        assert page.json()["props"]["ticket"]["reference"] == ticket.reference
        assert page["Cache-Control"].startswith("no-store")
        assert page["Referrer-Policy"] == "no-referrer"

    def test_a_code_works_once_and_for_its_own_email_and_purpose(self):
        client = Client()
        fields = proof(EMAIL)
        assert guest_create(client, fields).status_code == 302
        assert guest_create(client, fields).status_code == 200
        assert Ticket.objects.count() == 1
        assert guest_create(client, proof("other@example.com")).status_code == 200
        assert guest_create(client, proof(EMAIL, purpose="lookup")).status_code == 200
        assert Ticket.objects.count() == 1

    @override_settings(ESCALATED={"GUEST_RATE_LIMIT": {"ENABLED": False}})
    def test_five_wrong_guesses_burn_the_code(self):
        client = Client()
        fields = proof(EMAIL)
        for _ in range(5):
            guest_create(client, {**fields, "verification_code": "00000000"})
        assert guest_create(client, fields).status_code == 200
        assert not Ticket.objects.exists()
        assert GuestVerification.objects.get().attempts == 5

    def test_codes_expire_after_ten_minutes(self):
        fields = proof(EMAIL)
        GuestVerification.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        assert guest_create(Client(), fields).status_code == 200
        assert not Ticket.objects.exists()

    def test_reply_and_rate_use_the_grant(self):
        ticket = TicketFactory(guest_name="Ann", guest_email=EMAIL, status="open")
        token = grant(ticket)
        client = Client()
        assert client.post(f"/support/guest/{token}/reply/", {"body": "Any news?"}).status_code == 302
        assert ticket.replies.count() == 1
        ticket.status = "resolved"
        ticket.save(update_fields=["status"])
        assert client.post(f"/support/guest/{token}/rate/", {"rating": "5"}).status_code == 302

    def test_legacy_permanent_tokens_no_longer_open_tickets(self):
        ticket = TicketFactory(guest_email=EMAIL, guest_token="a" * 64)
        client = Client()
        assert client.get(f"/support/guest/{ticket.guest_token}/").status_code == 404
        assert client.post(f"/support/guest/{ticket.guest_token}/reply/", {"body": "x"}).status_code == 404
        with override_settings(ESCALATED={"GUEST_ACCESS": {"LEGACY_TOKENS": True}}):
            assert client.get(f"/support/guest/{ticket.guest_token}/", **INERTIA).status_code == 200

    def test_grants_expire(self):
        ticket = TicketFactory(guest_email=EMAIL)
        token = grant(ticket)
        later = time.time() + 25 * 3600
        with (
            patch("escalated.guest_access.time.time", return_value=later),
            patch("escalated.guest_access.timezone.now", return_value=timezone.now() + timedelta(hours=25)),
        ):
            assert Client().get(f"/support/guest/{token}/").status_code == 404

    def test_renewal_rotates_the_grant_and_revokes_the_old_one(self):
        ticket = TicketFactory(guest_email=EMAIL)
        old = grant(ticket)
        new = grant(ticket)
        assert Client().get(f"/support/guest/{old}/").status_code == 404
        assert Client().get(f"/support/guest/{new}/", **INERTIA).status_code == 200

    def test_changing_the_guest_email_revokes_access(self):
        ticket = TicketFactory(guest_email=EMAIL)
        token = grant(ticket)
        ticket.guest_email = "someone-else@example.com"
        ticket.save(update_fields=["guest_email"])
        assert Client().get(f"/support/guest/{token}/").status_code == 404

    def test_internal_notes_are_not_shown(self):
        from tests.factories import ReplyFactory

        ticket = TicketFactory(guest_email=EMAIL)
        ReplyFactory(ticket=ticket, body="public answer", is_internal_note=False)
        ReplyFactory(ticket=ticket, body="secret note", is_internal_note=True)
        page = Client().get(f"/support/guest/{grant(ticket)}/", **INERTIA)
        assert b"public answer" in page.content
        assert b"secret note" not in page.content
        assert b'"metadata"' not in page.content


@pytest.mark.django_db
class TestLookup:
    @pytest.mark.parametrize("url", LOOKUP_URLS)
    def test_lookup_returns_fresh_grants_for_the_proven_email(self, url):
        ticket = TicketFactory(guest_email="Ann@Example.com", subject="Order 42")
        old = grant(ticket)
        response = post_json(Client(), url, {"email": EMAIL, "reference": ticket.reference, **proof(EMAIL, "lookup")})
        assert response.status_code == 200, response.content
        [match] = response.json()["data"]
        assert match["reference"] == ticket.reference and match["subject"] == "Order 42"
        assert match["expires_at"]
        assert Client().get(f"/support/guest/{match['guest_access_token']}/", **INERTIA).status_code == 200
        assert Client().get(f"/support/guest/{old}/").status_code == 404

    def test_lookup_renews_a_pre_upgrade_ticket(self):
        ticket = TicketFactory(guest_email=EMAIL, guest_token="a" * 64)
        response = post_json(
            Client(), LOOKUP_URLS[0], {"email": EMAIL, "reference": ticket.reference, **proof(EMAIL, "lookup")}
        )
        [match] = response.json()["data"]
        ticket.refresh_from_db()
        assert ticket.guest_token is None
        assert Client().get(f"/support/guest/{match['guest_access_token']}/", **INERTIA).status_code == 200

    def test_a_reference_alone_unlocks_nothing(self):
        ticket = TicketFactory(guest_email="owner@example.com")
        response = post_json(
            Client(), LOOKUP_URLS[0], {"email": EMAIL, "reference": ticket.reference, **proof(EMAIL, "lookup")}
        )
        assert response.json() == {"data": []}
        assert post_json(Client(), LOOKUP_URLS[0], {"email": EMAIL, "reference": ticket.reference}).status_code == 422

    def test_a_ticket_code_cannot_be_used_for_lookup(self):
        ticket = TicketFactory(guest_email=EMAIL)
        response = post_json(
            Client(), LOOKUP_URLS[0], {"email": EMAIL, "reference": ticket.reference, **proof(EMAIL, "ticket")}
        )
        assert response.status_code == 422


@pytest.mark.django_db
class TestWidget:
    def test_config_advertises_verification_and_status_lookup(self):
        data = Client().get("/support/widget/config").json()
        assert data["guest_verification_required"] is True
        assert data["status_lookup_enabled"] is True

    def test_ticket_needs_a_code(self):
        body = {"name": "Ann", "email": EMAIL, "subject": "Help", "description": "Broken"}
        response = post_json(Client(), "/support/widget/tickets", body)
        assert response.status_code == 422
        assert "verification_code" in response.json()["errors"]
        assert not Ticket.objects.exists()

    def test_ticket_returns_an_expiring_grant_that_reads_status(self):
        client = Client()
        body = {"name": "Ann", "email": EMAIL, "subject": "Help", "description": "Broken", **proof(EMAIL)}
        response = post_json(client, "/support/widget/tickets", body)
        assert response.status_code == 201, response.content
        data = response.json()
        assert data["expires_at"]
        token = data["guest_access_token"]
        ticket = Ticket.objects.get()
        assert ticket.guest_token is None

        status = client.get(f"/support/widget/tickets/{ticket.reference}", HTTP_AUTHORIZATION=f"Bearer {token}")
        assert status.status_code == 200
        assert status.json()["reference"] == ticket.reference
        assert status.json()["subject"] == "Help"

    def test_status_needs_the_matching_grant(self):
        ticket = TicketFactory(guest_email=EMAIL)
        other = TicketFactory(guest_email=EMAIL)
        token = grant(ticket)
        client = Client()
        url = f"/support/widget/tickets/{ticket.reference}"
        assert client.get(url, {"email": EMAIL}).status_code == 404
        assert client.get(url, HTTP_AUTHORIZATION="Bearer nope").status_code == 404
        assert (
            client.get(f"/support/widget/tickets/{other.reference}", HTTP_AUTHORIZATION=f"Bearer {token}").status_code
            == 404
        )

    def test_chat_needs_a_chat_code(self):
        client = Client()
        body = {"name": "Ann", "email": EMAIL}
        assert post_json(client, "/support/widget/chat/start", body).status_code == 422
        assert post_json(client, "/support/widget/chat/start", {**body, **proof(EMAIL, "ticket")}).status_code == 422
        response = post_json(client, "/support/widget/chat/start", {**body, **proof(EMAIL, "chat")})
        assert response.status_code == 201, response.content
        assert ChatSession.objects.count() == 1


@pytest.mark.django_db
def test_guest_attachment_links_follow_the_grant(tmp_path):
    ticket = TicketFactory(guest_email=EMAIL)
    with override_settings(MEDIA_ROOT=str(tmp_path)):
        Attachment.objects.create(
            content_type=ContentType.objects.get_for_model(ticket),
            object_id=ticket.pk,
            file=ContentFile(b"hello", name="a.txt"),
            original_filename="a.txt",
            mime_type="text/plain",
            size=5,
        )
        page = Client().get(f"/support/guest/{grant(ticket)}/", **INERTIA)
        url = page.json()["props"]["attachments"][0]["url"]
        assert Client().get(url).status_code == 200
        grant(ticket)  # renewal revokes links issued under the old grant
        assert Client().get(url).status_code == 403


@pytest.mark.django_db
def test_purge_removes_expired_codes():
    proof(EMAIL)
    proof(EMAIL)
    GuestVerification.objects.filter(pk=GuestVerification.objects.first().pk).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )
    call_command("purge_expired_data")
    assert GuestVerification.objects.count() == 1


@pytest.mark.django_db
def test_grant_ttl_is_clamped():
    with override_settings(ESCALATED={"GUEST_ACCESS": {"TTL_MINUTES": 1}}):
        assert guest_access.grant_ttl() == timedelta(minutes=5)
    with override_settings(ESCALATED={"GUEST_ACCESS": {"TTL_MINUTES": 10**6}}):
        assert guest_access.grant_ttl() == timedelta(days=7)
