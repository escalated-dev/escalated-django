"""
A refusal or a failure inside the panel stays inside the panel.

An Inertia visit that gets an HTML error back has nowhere to put it: the client
opens it in a modal over the screen the user was on. So an Inertia visit to one
of Escalated's routes that ends in 403, 404, 419, 429, 500 or 503 gets the
shared frontend's Escalated/Error page, with the props Rails and Laravel send:
the status and a generic message. Full page loads, JSON clients and the host's
own routes are left alone.
"""

import pytest
from django.test import Client
from django.urls import reverse

from tests.factories import DepartmentFactory, UserFactory

pytestmark = pytest.mark.django_db

SHARE = "escalated.middleware.EscalatedInertiaShareMiddleware"
INERTIA = {"HTTP_X_INERTIA": "true"}


@pytest.fixture(autouse=True)
def wired(settings):
    settings.ROOT_URLCONF = "tests.error_page_urls"
    settings.MIDDLEWARE = [*settings.MIDDLEWARE, SHARE]
    settings.DEBUG = False


@pytest.fixture
def agent(client):
    user = UserFactory(username="error-page-agent")
    DepartmentFactory().agents.add(user)
    client.force_login(user)
    return user


def assert_error_page(response, status, message):
    assert response.status_code == status
    assert response.headers.get("X-Inertia") == "true"
    body = response.json()
    assert body["component"] == "Escalated/Error"
    assert body["props"]["status"] == status
    assert body["props"]["message"] == message
    return body


def test_a_refused_inertia_visit_gets_the_error_page(client, agent):
    response = client.get(reverse("escalated:admin_settings"), **INERTIA)

    assert_error_page(response, 403, "You are not authorized to perform this action.")
    assert b"Admin access required" not in response.content


def test_an_inertia_visit_to_a_missing_ticket_gets_the_error_page(client, agent):
    response = client.get(reverse("escalated:agent_ticket_show", args=[999999]), **INERTIA)

    assert_error_page(response, 404, "The requested resource was not found.")
    assert b"Ticket not found" not in response.content


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (419, "Your session has expired. Refresh the page and try again."),
        (429, "Too many requests. Wait a moment and try again."),
        (500, "Something went wrong on our end."),
        (503, "The service is temporarily unavailable. Try again shortly."),
    ],
)
def test_each_status_the_page_has_wording_for(status, message):
    client = Client(raise_request_exception=False)

    response = client.get(f"/support/probe/{status}/", **INERTIA)

    assert_error_page(response, status, message)
    assert b"upstream detail" not in response.content
    assert b"escalated_secret_table" not in response.content


def test_sends_only_the_status_and_the_message(client, agent):
    props = client.get(reverse("escalated:admin_settings"), **INERTIA).json()["props"]

    assert {"status", "message"} <= set(props)
    assert "home" not in props
    assert "exception" not in props


def test_a_failed_csrf_check_on_an_inertia_post_gets_the_error_page(settings):
    settings.MIDDLEWARE = [
        *settings.MIDDLEWARE[:-1],
        "django.middleware.csrf.CsrfViewMiddleware",
        SHARE,
    ]
    client = Client(enforce_csrf_checks=True)
    user = UserFactory(username="csrf-agent")
    DepartmentFactory().agents.add(user)
    client.force_login(user)

    response = client.post(reverse("escalated:agent_ticket_bulk"), {}, **INERTIA)

    assert_error_page(response, 403, "You are not authorized to perform this action.")


def test_leaves_a_500_to_the_technical_page_while_debug_is_on(settings):
    settings.DEBUG = True
    client = Client(raise_request_exception=False)

    response = client.get("/support/probe/500/", **INERTIA)

    assert response.status_code == 500
    assert response.headers.get("X-Inertia") is None


def test_leaves_a_full_page_load_alone(client, agent):
    response = client.get(reverse("escalated:admin_settings"))

    assert response.status_code == 403
    assert response.headers.get("X-Inertia") is None
    assert b"Escalated/Error" not in response.content


def test_leaves_a_json_request_alone(client, agent):
    response = client.get(reverse("escalated:admin_settings"), HTTP_ACCEPT="application/json")

    assert response.status_code == 403
    assert response.headers.get("X-Inertia") is None
    assert b"Escalated/Error" not in response.content


def test_leaves_a_host_route_alone(client):
    response = client.get("/host/missing/", **INERTIA)

    assert response.status_code == 404
    assert response.content == b"host page"


def test_leaves_an_unmatched_url_alone(client):
    response = client.get("/support/no-such-screen/", **INERTIA)

    assert response.status_code == 404
    assert response.headers.get("X-Inertia") is None


def test_stays_off_while_the_ui_is_disabled(settings, client, agent):
    settings.ESCALATED = {**settings.ESCALATED, "UI_ENABLED": False}

    response = client.get(reverse("escalated:admin_settings"), **INERTIA)

    assert response.status_code == 403
    assert response.headers.get("X-Inertia") is None
