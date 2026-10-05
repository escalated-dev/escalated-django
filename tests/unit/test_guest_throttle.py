"""Per-IP rate limit on the unauthenticated guest ticket and reply endpoints.

Mirrors escalated-nestjs#130: 5 guest ticket submissions and 10 guest replies
per client IP per minute by default, counted in separate buckets, with the
reply throttle running before the guest-token lookup so wrong-token requests
count too.
"""

import json
from unittest import mock

import pytest
from django.conf import settings
from django.core.cache import caches
from django.test import override_settings

from escalated.models import Ticket
from tests.factories import TicketFactory

WIDGET_CREATE = "/support/widget/tickets/create/"
GUEST_STORE = "/support/guest/store/"


def _guest_rate_limit(**overrides):
    """override_settings for ESCALATED with a GUEST_RATE_LIMIT dict merged in."""
    return override_settings(ESCALATED={**settings.ESCALATED, "GUEST_RATE_LIMIT": overrides})


def _widget_ticket(client, ip="203.0.113.1"):
    payload = {"name": "Guest", "email": "guest@example.com", "subject": "Help", "description": "It broke"}
    return client.post(WIDGET_CREATE, data=json.dumps(payload), content_type="application/json", REMOTE_ADDR=ip)


def _guest_ticket(client, ip="203.0.113.1"):
    payload = {"name": "Guest", "email": "guest@example.com", "subject": "Help", "description": "It broke"}
    return client.post(GUEST_STORE, data=payload, REMOTE_ADDR=ip)


def _guest_reply(client, token, ip="203.0.113.1"):
    return client.post(f"/support/guest/{token}/reply/", data={"body": "Any news?"}, REMOTE_ADDR=ip)


@pytest.fixture(autouse=True)
def _pinned_clock():
    """The window is a clock-aligned 60s bucket; pin the clock mid-minute so a test never straddles two."""
    with mock.patch("escalated.guest_throttle.time") as clock:
        clock.time.return_value = 1_767_268_815.0  # 2026-01-01 12:00:15 UTC
        yield


@pytest.fixture
def guest_ticket(db):
    return TicketFactory(guest_token="a" * 64, guest_email="guest@example.com", status="open")


@pytest.mark.django_db
class TestGuestTicketThrottle:
    def test_widget_allows_5_tickets_per_minute_and_rejects_the_6th_with_429(self, client):
        statuses = [_widget_ticket(client).status_code for _ in range(6)]

        assert statuses == [200, 200, 200, 200, 200, 429]
        assert Ticket.objects.count() == 5

    def test_guest_form_allows_5_tickets_per_minute_and_rejects_the_6th_with_429(self, client):
        statuses = [_guest_ticket(client).status_code for _ in range(6)]

        assert statuses == [302, 302, 302, 302, 302, 429]
        assert Ticket.objects.count() == 5

    def test_widget_and_guest_form_share_the_ticket_bucket(self, client):
        for _ in range(3):
            _widget_ticket(client)
        statuses = [_guest_ticket(client).status_code for _ in range(3)]

        assert statuses == [302, 302, 429]

    def test_429_carries_retry_after(self, client):
        for _ in range(5):
            _widget_ticket(client)
        response = _widget_ticket(client)

        assert response.status_code == 429
        assert 0 < int(response["Retry-After"]) <= 60

    def test_keys_each_client_ip_separately(self, client):
        for _ in range(5):
            _widget_ticket(client, ip="203.0.113.1")

        assert _widget_ticket(client, ip="203.0.113.2").status_code == 200

    def test_honours_configured_ticket_limit(self, client):
        with _guest_rate_limit(TICKETS_PER_MINUTE=2):
            statuses = [_widget_ticket(client).status_code for _ in range(3)]

        assert statuses == [200, 200, 429]

    def test_disabled_never_429s(self, client):
        with _guest_rate_limit(ENABLED=False):
            statuses = [_widget_ticket(client).status_code for _ in range(20)]

        assert 429 not in statuses


@pytest.mark.django_db
class TestGuestReplyThrottle:
    def test_allows_10_replies_per_minute_and_rejects_the_11th_with_429(self, client, guest_ticket):
        statuses = [_guest_reply(client, guest_ticket.guest_token).status_code for _ in range(11)]

        assert statuses == [302] * 10 + [429]
        assert 0 < int(_guest_reply(client, guest_ticket.guest_token)["Retry-After"]) <= 60

    def test_wrong_token_replies_count_against_the_limit(self, client, guest_ticket):
        with _guest_rate_limit(REPLIES_PER_MINUTE=3):
            statuses = [_guest_reply(client, "wrong-token").status_code for _ in range(3)]
            statuses.append(_guest_reply(client, guest_ticket.guest_token).status_code)

        assert statuses == [404, 404, 404, 429]

    def test_honours_configured_reply_limit(self, client, guest_ticket):
        with _guest_rate_limit(REPLIES_PER_MINUTE=1):
            statuses = [_guest_reply(client, guest_ticket.guest_token).status_code for _ in range(2)]

        assert statuses == [302, 429]

    def test_unset_limits_keep_their_defaults(self, client):
        with _guest_rate_limit(REPLIES_PER_MINUTE=1):
            statuses = [_widget_ticket(client).status_code for _ in range(6)]

        assert statuses == [200, 200, 200, 200, 200, 429]

    def test_tickets_and_replies_are_counted_separately(self, client, guest_ticket):
        for _ in range(5):
            _widget_ticket(client)

        assert _guest_reply(client, guest_ticket.guest_token).status_code == 302

    def test_disabled_never_429s(self, client, guest_ticket):
        with _guest_rate_limit(ENABLED=False):
            statuses = [_guest_reply(client, guest_ticket.guest_token).status_code for _ in range(20)]

        assert 429 not in statuses


THROTTLE_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "default"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "throttle"},
}


@pytest.mark.django_db
class TestGuestThrottleCacheAlias:
    def test_counts_in_the_configured_cache(self, client):
        with override_settings(CACHES=THROTTLE_CACHES), _guest_rate_limit(CACHE="throttle", TICKETS_PER_MINUTE=1):
            assert _widget_ticket(client).status_code == 200
            # Clearing the default cache must not reset a counter kept elsewhere.
            caches["default"].clear()
            assert _widget_ticket(client).status_code == 429
            caches["throttle"].clear()
