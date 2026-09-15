"""
Integration tests for the cloud → site webhook receiver (Synced mode).
"""

import hashlib
import hmac
import json
from importlib import reload

import django
import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client, RequestFactory, override_settings
from django.urls import resolve, reverse

from escalated.models import Ticket, TicketActivity
from escalated.views import cloud_webhook
from tests.factories import TicketFactory

SECRET = "whsec_site"
SETTINGS = {"MODE": "synced", "HOSTED_SIGNING_SECRET": SECRET, "HOSTED_API_KEY": "k"}


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def projected(ticket, **overrides):
    payload = {
        "id": 501,
        "ticket_number": 7,
        "subject": ticket.subject,
        "description": ticket.description,
        "status": "open",
        "priority": "normal",
        "assigned_to": None,
        "external_id": ticket.reference,
        "metadata": {"origin": "synced", "source_site_id": 1},
    }
    payload.update(overrides)
    return payload


def post_event(rf, event, ticket_payload, event_id="evt-1", sign_with=SECRET):
    body = json.dumps(
        {"event": event, "event_id": event_id, "ticket": ticket_payload, "timestamp": "2026-09-15T00:00:00Z"}
    )
    request = rf.post("/support/cloud/webhook/", data=body, content_type="application/json")
    if sign_with is not None:
        digest = hmac.new(sign_with.encode(), body.encode(), hashlib.sha256).hexdigest()
        request.META["HTTP_X_ESCALATED_SIGNATURE"] = f"sha256={digest}"
    response = cloud_webhook.cloud_webhook(request)
    return response, json.loads(response.content)


@pytest.mark.django_db
class TestCloudWebhook:
    def test_503_until_a_signing_secret_is_configured(self, rf):
        ticket = TicketFactory()
        with override_settings(ESCALATED={"MODE": "synced"}):
            response, _ = post_event(rf, "ticket.updated", projected(ticket))
        assert response.status_code == 503

    def test_rejects_a_missing_or_wrong_signature(self, rf):
        ticket = TicketFactory()
        with override_settings(ESCALATED=SETTINGS):
            response, _ = post_event(rf, "ticket.updated", projected(ticket, status="closed"), sign_with=None)
            assert response.status_code == 401
            response, _ = post_event(rf, "ticket.updated", projected(ticket, status="closed"), sign_with="other")
            assert response.status_code == 401
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.OPEN

    def test_applies_a_status_change_with_the_package_vocabulary(self, rf):
        ticket = TicketFactory(status=Ticket.Status.OPEN, priority=Ticket.Priority.MEDIUM)
        with override_settings(ESCALATED=SETTINGS):
            response, body = post_event(rf, "ticket.status_changed", projected(ticket, status="waiting"))
        assert response.status_code == 200
        assert body == {"received": True, "applied": True, "changes": ["status"]}
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.WAITING_ON_CUSTOMER
        activities = TicketActivity.objects.filter(ticket=ticket, type=TicketActivity.ActivityType.STATUS_CHANGED)
        # Both LocalDriver and the existing status signal handler log activity.
        assert activities.exists()
        assert all(activity.causer_object_id is None for activity in activities)

    def test_applies_subject_description_and_priority(self, rf):
        ticket = TicketFactory(priority=Ticket.Priority.MEDIUM)
        with override_settings(ESCALATED=SETTINGS):
            _, body = post_event(
                rf, "ticket.updated", projected(ticket, subject="After", description="New body", priority="urgent")
            )
        assert sorted(body["changes"]) == ["description", "priority", "subject"]
        ticket.refresh_from_db()
        assert (ticket.subject, ticket.description, ticket.priority) == ("After", "New body", Ticket.Priority.URGENT)

    def test_nothing_applied_when_the_projection_matches(self, rf):
        ticket = TicketFactory(priority=Ticket.Priority.MEDIUM)
        with override_settings(ESCALATED=SETTINGS):
            _, body = post_event(rf, "ticket.updated", projected(ticket))
        assert body == {"received": True, "applied": False, "changes": []}

    def test_replayed_event_ids_are_ignored(self, rf):
        ticket = TicketFactory()
        with override_settings(ESCALATED=SETTINGS):
            post_event(rf, "ticket.status_changed", projected(ticket, status="closed"), event_id="evt-dup")
            _, body = post_event(rf, "ticket.status_changed", projected(ticket, status="open"), event_id="evt-dup")
        assert body == {"received": True, "applied": False, "replay": True}
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.CLOSED

    def test_ignores_other_events_missing_and_unknown_references(self, rf):
        ticket = TicketFactory()
        with override_settings(ESCALATED=SETTINGS):
            response, body = post_event(rf, "ticket.created", projected(ticket, status="closed"))
            assert response.status_code == 202 and body["applied"] is False
            response, _ = post_event(
                rf, "ticket.updated", projected(ticket, status="closed", external_id=None), event_id="evt-missing"
            )
            assert response.status_code == 202
            response, _ = post_event(
                rf, "ticket.updated", projected(ticket, status="closed", external_id="ESC-NOPE"), event_id="evt-unknown"
            )
            assert response.status_code == 202
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.OPEN

    def test_never_echoes_back_to_the_cloud(self, rf, monkeypatch):
        ticket = TicketFactory()
        emitted = []

        def boom(*args, **kwargs):
            emitted.append((args, kwargs))
            raise AssertionError("HostedApiClient must not be used by the receiver")

        monkeypatch.setattr("escalated.drivers.api_client.HostedApiClient.emit", boom)
        with override_settings(ESCALATED=SETTINGS):
            response, body = post_event(rf, "ticket.status_changed", projected(ticket, status="resolved"))
        assert response.status_code == 200
        assert body == {"received": True, "applied": True, "changes": ["status"]}
        assert emitted == []
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.RESOLVED

    def test_unknown_vocabulary_is_ignored(self, rf):
        ticket = TicketFactory()
        with override_settings(ESCALATED=SETTINGS):
            response, body = post_event(rf, "ticket.updated", projected(ticket, status="unknown", priority="unknown"))
        assert response.status_code == 200
        assert body == {"received": True, "applied": False, "changes": []}
        ticket.refresh_from_db()
        assert (ticket.status, ticket.priority) == (Ticket.Status.OPEN, Ticket.Priority.MEDIUM)

    def test_snoozed_status_and_normal_priority_use_local_vocabulary(self, rf):
        ticket = TicketFactory(status=Ticket.Status.IN_PROGRESS, priority=Ticket.Priority.HIGH)
        with override_settings(ESCALATED=SETTINGS):
            response, body = post_event(rf, "ticket.updated", projected(ticket, status="snoozed", priority="normal"))
        assert response.status_code == 200
        assert body == {"received": True, "applied": True, "changes": ["priority", "status"]}
        ticket.refresh_from_db()
        assert (ticket.status, ticket.priority) == (Ticket.Status.OPEN, Ticket.Priority.MEDIUM)

    def test_apply_failure_is_acknowledged_and_logged(self, rf, monkeypatch, caplog):
        ticket = TicketFactory()

        def fail(*args, **kwargs):
            raise ValueError("Permanent apply failure")

        monkeypatch.setattr(cloud_webhook.LocalDriver, "transition_status", fail)
        with override_settings(ESCALATED=SETTINGS):
            response, body = post_event(rf, "ticket.status_changed", projected(ticket, status="closed"))
        assert response.status_code == 200
        assert body == {"received": True, "applied": False, "reason": "Permanent apply failure"}
        assert ticket.reference in caplog.text
        assert "Permanent apply failure" in caplog.text
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.OPEN


@pytest.mark.parametrize("raw", [b"{", b"\xff", b"[]", b"null", b'{"event":"ticket.updated","ticket":[]}'])
def test_signed_invalid_payload_is_ignored(rf, raw):
    request = rf.post("/support/cloud/webhook/", data=raw, content_type="application/json")
    digest = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    request.META["HTTP_X_ESCALATED_SIGNATURE"] = f"sha256={digest}"
    with override_settings(ESCALATED=SETTINGS):
        response = cloud_webhook.cloud_webhook(request)
    assert response.status_code == 202
    assert json.loads(response.content)["applied"] is False


def test_non_ascii_signature_is_rejected(rf):
    request = rf.post("/support/cloud/webhook/", data=b"{}", content_type="application/json")
    request.META["HTTP_X_ESCALATED_SIGNATURE"] = "sha256=é"
    with override_settings(ESCALATED=SETTINGS):
        response = cloud_webhook.cloud_webhook(request)
    assert response.status_code == 401


def test_signature_verifies_the_raw_body(rf):
    request = rf.post("/support/cloud/webhook/", data=b'{ "event": "ticket.updated" }', content_type="application/json")
    digest = hmac.new(SECRET.encode(), b'{"event":"ticket.updated"}', hashlib.sha256).hexdigest()
    request.META["HTTP_X_ESCALATED_SIGNATURE"] = f"sha256={digest}"
    with override_settings(ESCALATED=SETTINGS):
        response = cloud_webhook.cloud_webhook(request)
    assert response.status_code == 401


def test_public_route_is_post_only_and_csrf_exempt():
    url = reverse("escalated:cloud_webhook")
    assert url == "/support/cloud/webhook/"
    client = Client(enforce_csrf_checks=True)
    middleware = [*settings.MIDDLEWARE, "django.middleware.csrf.CsrfViewMiddleware"]
    if django.VERSION >= (5, 1):
        middleware.append("django.contrib.auth.middleware.LoginRequiredMiddleware")
    with override_settings(ESCALATED=SETTINGS, MIDDLEWARE=middleware):
        assert client.get(url).status_code == 405
        # An unsigned anonymous POST reaches signature verification without a CSRF token.
        assert client.post(url, data=b"{}", content_type="application/json").status_code == 401


def test_route_is_registered_with_ui_disabled():
    from escalated import urls

    try:
        with override_settings(ESCALATED={**SETTINGS, "UI_ENABLED": False}):
            reload(urls)
            match = resolve("/cloud/webhook/", urlconf=tuple(urls.urlpatterns))
            assert match.url_name == "cloud_webhook"
            assert match.func is cloud_webhook.cloud_webhook
    finally:
        reload(urls)
