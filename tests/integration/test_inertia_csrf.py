"""CSRF for the shared frontend's POSTs on a Django host.

The shared pages send their CSRF token two ways:

* Inertia visits (``router.post``) send ``X-XSRF-TOKEN``, read from an
  ``XSRF-TOKEN`` cookie (axios and Inertia 3's client do this by default).
* Components that call ``fetch`` (chat bar, reply composer, saved views, ...)
  send ``X-CSRF-TOKEN``, read from a ``<meta name="csrf-token">`` tag.

Django's ``CsrfViewMiddleware`` reads only ``X-CSRFToken`` and the
``csrftoken`` cookie by default, so on a default host both kinds of POST are
refused. ``escalated.middleware.EscalatedCsrfMiddleware`` accepts both headers
and sets the ``XSRF-TOKEN`` cookie, while still refusing a missing or wrong
token. These tests drive the real middleware stack with
``Client(enforce_csrf_checks=True)``.
"""

import json

import pytest
from django.test import Client, override_settings

from escalated.models import Ticket
from tests.factories import TicketFactory, UserFactory

DEFAULT_STACK = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "inertia.middleware.InertiaMiddleware",
]
WITH_ESCALATED = [
    *DEFAULT_STACK[:3],
    "escalated.middleware.EscalatedCsrfMiddleware",
    *DEFAULT_STACK[3:],
]


def _signed_in_page(username):
    """An agent's browser after loading an Escalated page."""
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(username=username, is_staff=True, is_superuser=True))
    ticket = TicketFactory()
    page = client.get(f"/support/agent/tickets/{ticket.pk}/", HTTP_X_INERTIA="true")
    assert page.status_code == 200, page.content[:500]
    return client, ticket


def _meta_token(client):
    """What a ``{% csrf_token %}`` meta tag would hold: a token for this session."""
    from django.conf import settings

    return client.cookies[settings.CSRF_COOKIE_NAME].value


def _inertia_post(client, ticket):
    """``router.post`` from an Inertia page: X-XSRF-TOKEN from the XSRF-TOKEN cookie, if any."""
    headers = {"HTTP_X_INERTIA": "true", "HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
    cookie = client.cookies.get("XSRF-TOKEN")
    if cookie is not None:
        headers["HTTP_X_XSRF_TOKEN"] = cookie.value
    return client.post(
        f"/support/agent/tickets/{ticket.pk}/status/",
        data=json.dumps({"status": "in_progress"}),
        content_type="application/json",
        **headers,
    )


def _fetch_post(client, token):
    """A component's ``fetch``: X-CSRF-TOKEN from the csrf-token meta tag."""
    return client.post(
        "/support/agent/chat/status/",
        data=json.dumps({"status": "online"}),
        content_type="application/json",
        HTTP_ACCEPT="application/json",
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        HTTP_X_CSRF_TOKEN=token,
    )


def _refused_by_csrf(response):
    return response.status_code == 403 and b"CSRF" in response.content


@pytest.mark.django_db
@override_settings(MIDDLEWARE=DEFAULT_STACK)
def test_a_default_django_host_refuses_both_kinds_of_post():
    client, ticket = _signed_in_page("csrf_default")

    assert "XSRF-TOKEN" not in client.cookies
    assert _refused_by_csrf(_inertia_post(client, ticket))
    assert _refused_by_csrf(_fetch_post(client, _meta_token(client)))


@pytest.mark.django_db
@override_settings(MIDDLEWARE=WITH_ESCALATED)
def test_inertia_posts_pass_with_the_escalated_middleware():
    client, ticket = _signed_in_page("csrf_inertia")

    assert client.cookies["XSRF-TOKEN"]["httponly"] == ""
    response = _inertia_post(client, ticket)
    assert response.status_code == 302, response.content[:300]
    ticket.refresh_from_db()
    assert ticket.status == Ticket.Status.IN_PROGRESS


@pytest.mark.django_db
@override_settings(MIDDLEWARE=WITH_ESCALATED)
def test_fetch_posts_pass_with_the_escalated_middleware():
    client, _ticket = _signed_in_page("csrf_fetch")

    response = _fetch_post(client, _meta_token(client))
    assert response.status_code == 200, response.content[:300]
    assert response.json() == {"status": "online"}


@pytest.mark.django_db
@override_settings(MIDDLEWARE=WITH_ESCALATED)
def test_a_missing_or_wrong_token_is_still_refused():
    client, ticket = _signed_in_page("csrf_wrong")

    client.cookies.pop("XSRF-TOKEN")
    assert _refused_by_csrf(_inertia_post(client, ticket))
    assert _refused_by_csrf(_fetch_post(client, ""))
    assert _refused_by_csrf(_fetch_post(client, "x" * 64))
    ticket.refresh_from_db()
    assert ticket.status != Ticket.Status.IN_PROGRESS


@pytest.mark.django_db
@override_settings(MIDDLEWARE=WITH_ESCALATED)
def test_the_native_django_header_still_wins():
    client, _ticket = _signed_in_page("csrf_native")

    response = client.post(
        "/support/agent/chat/status/",
        data=json.dumps({"status": "away"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=_meta_token(client),
        HTTP_X_CSRF_TOKEN="x" * 64,
    )
    assert response.status_code == 200, response.content[:300]


@pytest.mark.django_db
@override_settings(
    MIDDLEWARE=WITH_ESCALATED,
    CSRF_COOKIE_NAME="XSRF-TOKEN",
    CSRF_HEADER_NAME="HTTP_X_XSRF_TOKEN",
)
def test_a_host_configured_the_inertia_django_way_accepts_both():
    client, ticket = _signed_in_page("csrf_inertia_django")

    assert _inertia_post(client, ticket).status_code == 302
    assert _fetch_post(client, _meta_token(client)).status_code == 200


@pytest.mark.django_db
@override_settings(CSRF_COOKIE_NAME="XSRF-TOKEN", CSRF_HEADER_NAME="HTTP_X_XSRF_TOKEN", MIDDLEWARE=DEFAULT_STACK)
def test_the_inertia_django_settings_alone_leave_fetch_posts_refused():
    client, ticket = _signed_in_page("csrf_settings_only")

    assert _inertia_post(client, ticket).status_code == 302
    assert _refused_by_csrf(_fetch_post(client, _meta_token(client)))
