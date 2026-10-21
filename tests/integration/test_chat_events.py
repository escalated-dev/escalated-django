"""Live chat events reach outbound webhooks and workflows (ADR 2026-10-21).

``chat.started``, ``chat.assigned``, ``chat.transferred``, ``chat.message`` and
``chat.ended`` are offered in the webhook form and as workflow triggers, and are
delivered with a payload that never carries the visitor's chat token, the
visitor's email or the message body.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client, override_settings

from escalated.models import ChatSession, WebhookDelivery
from escalated.serializers import WebhookSerializer
from escalated.workflow_models import Workflow, WorkflowLog
from tests.factories import DepartmentFactory, UserFactory, WebhookFactory
from tests.guest_proof import proven

pytestmark = pytest.mark.usefixtures("widget_on")

PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 443))]
INERTIA = {"HTTP_X_INERTIA": "true"}
CHAT_EVENTS = ["chat.started", "chat.assigned", "chat.transferred", "chat.message", "chat.ended"]
VISITOR_EMAIL = "visitor@example.com"
SECRET_MESSAGE = "my order number is 4242"


@pytest.fixture
def deliveries():
    """Every webhook request body sent while the test runs, decoded, in order."""
    sent = []

    def post(url, data=None, **kwargs):
        sent.append({"raw": data, **json.loads(data)})
        return MagicMock(status_code=200, text="OK", ok=True)

    with (
        patch("escalated.outbound_security.socket.getaddrinfo", return_value=PUBLIC_ADDRINFO),
        patch("escalated.services.webhook_dispatcher.requests.post", side_effect=post),
    ):
        yield sent


def _only(sent, event):
    matching = [body for body in sent if body["event"] == event]
    assert len(matching) == 1, [body["event"] for body in sent]
    return matching[0]


def _assert_private(body, token):
    assert VISITOR_EMAIL not in body["raw"]
    assert token not in body["raw"]
    assert SECRET_MESSAGE not in body["raw"]


def _start(client, department=None):
    payload = {"name": "Visitor", "email": VISITOR_EMAIL, "subject": "Help"}
    if department is not None:
        payload["department_id"] = department.pk
    response = client.post(
        "/support/widget/chat/start",
        data=json.dumps(proven(payload, "chat")),
        content_type="application/json",
    )
    assert response.status_code in (200, 201), response.content
    token = response.json()["id"]
    return token, ChatSession.objects.get(customer_session_id=token)


def _agent(username, department):
    agent = UserFactory(username=username)
    department.agents.add(agent)
    return agent


@pytest.mark.django_db
def test_the_webhook_form_offers_the_chat_events():
    assert set(CHAT_EVENTS) <= set(WebhookSerializer.AVAILABLE_EVENTS)


@pytest.mark.django_db
def test_the_workflow_builder_offers_the_chat_triggers():
    with override_settings(ESCALATED={"UI_ENABLED": True}):
        client = Client()
        client.force_login(UserFactory(username="chat_admin", is_staff=True, is_superuser=True))
        response = client.get("/support/admin/workflows/create/", **INERTIA)
    assert response.status_code == 200
    offered = {option["value"] for option in json.loads(response.content)["props"]["trigger_events"]}
    assert set(CHAT_EVENTS) <= offered


@pytest.mark.django_db
def test_chat_events_reach_webhooks_without_the_token_email_or_body(client, deliveries):
    WebhookFactory(events=CHAT_EVENTS, active=True)
    department = DepartmentFactory()
    token, session = _start(client, department)

    started = _only(deliveries, "chat.started")
    assert started["payload"]["chat"] == {
        "session_id": session.pk,
        "ticket_id": session.ticket_id,
        "status": "waiting",
        "agent_id": None,
        "department_id": department.pk,
    }
    _assert_private(started, token)

    agent = _agent("chat_agent", department)
    other = _agent("chat_other", department)
    agent_client = Client()
    agent_client.force_login(agent)

    assert agent_client.post(f"/support/agent/chat/{session.pk}/accept/").status_code == 200
    assigned = _only(deliveries, "chat.assigned")
    assert assigned["payload"]["chat"]["agent_id"] == agent.pk
    assert assigned["payload"]["chat"]["status"] == "active"
    _assert_private(assigned, token)

    response = agent_client.post(
        f"/support/agent/chat/{session.pk}/transfer/",
        data=json.dumps({"agent_id": other.pk}),
        content_type="application/json",
    )
    assert response.status_code == 200
    transferred = _only(deliveries, "chat.transferred")
    assert transferred["payload"]["chat"]["agent_id"] == other.pk
    assert transferred["payload"]["chat"]["from_agent_id"] == agent.pk
    assert transferred["payload"]["chat"]["to_agent_id"] == other.pk
    _assert_private(transferred, token)

    response = client.post(
        f"/support/widget/chat/{token}/messages",
        data=json.dumps({"body": SECRET_MESSAGE}),
        content_type="application/json",
    )
    assert response.status_code in (200, 201), response.content
    message = _only(deliveries, "chat.message")
    assert message["payload"]["chat"]["author_type"] == "visitor"
    assert message["payload"]["chat"]["reply_id"]
    _assert_private(message, token)

    assert client.post(f"/support/widget/chat/{token}/end").status_code == 200
    ended = _only(deliveries, "chat.ended")
    assert ended["payload"]["chat"]["status"] == "ended"
    assert ended["payload"]["chat"]["ended_by"] == "customer"
    _assert_private(ended, token)

    assert list(WebhookDelivery.objects.order_by("pk").values_list("event", flat=True)) == CHAT_EVENTS


@pytest.mark.django_db
def test_an_agent_message_is_sent_as_chat_message(client, deliveries):
    WebhookFactory(events=["chat.message"], active=True)
    department = DepartmentFactory()
    _token, session = _start(client, department)
    agent = _agent("msg_agent", department)
    agent_client = Client()
    agent_client.force_login(agent)
    agent_client.post(f"/support/agent/chat/{session.pk}/accept/")

    response = agent_client.post(
        f"/support/agent/chat/{session.pk}/message/",
        data=json.dumps({"body": "How can I help?"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    message = _only(deliveries, "chat.message")
    assert message["payload"]["chat"]["author_type"] == "agent"
    assert "How can I help?" not in message["raw"]


@pytest.mark.django_db
def test_legacy_chat_subscriptions_receive_the_canonical_events(client, deliveries):
    WebhookFactory(events=["chat.session_started", "chat.session_ended"], active=True)
    token, _session = _start(client)
    client.post(f"/support/widget/chat/{token}/end")

    assert [body["event"] for body in deliveries] == ["chat.started", "chat.ended"]


@pytest.mark.django_db
def test_chat_events_fire_workflows(client):
    for event in CHAT_EVENTS:
        Workflow.objects.create(
            name=event,
            trigger_event=event,
            conditions={"all": []},
            actions=[{"type": "add_tag", "value": event.replace(".", "-")}],
        )
    department = DepartmentFactory()
    token, session = _start(client, department)
    agent = _agent("wf_agent", department)
    other = _agent("wf_other", department)
    agent_client = Client()
    agent_client.force_login(agent)
    agent_client.post(f"/support/agent/chat/{session.pk}/accept/")
    agent_client.post(
        f"/support/agent/chat/{session.pk}/transfer/",
        data=json.dumps({"agent_id": other.pk}),
        content_type="application/json",
    )
    client.post(
        f"/support/widget/chat/{token}/messages",
        data=json.dumps({"body": "hello"}),
        content_type="application/json",
    )
    client.post(f"/support/widget/chat/{token}/end")

    fired = list(WorkflowLog.objects.filter(status="success").values_list("trigger_event", flat=True))
    assert sorted(fired) == sorted(CHAT_EVENTS)
    session.ticket.refresh_from_db()
    assert {tag.name for tag in session.ticket.tags.all()} >= {e.replace(".", "-") for e in CHAT_EVENTS}


@pytest.mark.django_db
def test_a_stored_legacy_chat_trigger_still_fires(client):
    Workflow.objects.create(
        name="legacy",
        trigger_event="chat.session_started",
        conditions={"all": []},
        actions=[{"type": "add_tag", "value": "legacy-chat"}],
    )
    _token, session = _start(client)
    assert list(WorkflowLog.objects.values_list("trigger_event", flat=True)) == ["chat.started"]
