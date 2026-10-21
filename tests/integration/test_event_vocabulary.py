"""The shared event vocabulary (escalated-developer-context ADR 2026-10-21).

Webhooks and workflow triggers are emitted under the canonical names only.
Names stored by earlier releases (a webhook's ``events``, a workflow's
``trigger_event``) are still read, as aliases of the canonical name.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client, override_settings

from escalated import signals as esc_signals
from escalated.event_names import CANONICAL_EVENTS, LEGACY_EVENT_NAMES, canonical_event
from escalated.models import Reply, Webhook, WebhookDelivery
from escalated.serializers import WebhookSerializer
from escalated.services.ticket_service import TicketService
from escalated.services.webhook_dispatcher import WebhookDispatcher
from escalated.workflow_models import Workflow
from tests.factories import TagFactory, TicketFactory, UserFactory, WebhookFactory

PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 443))]
INERTIA = {"HTTP_X_INERTIA": "true"}

ADR_LEGACY = {
    "ticket.replied": "reply.created",
    "internal_note.added": "note.created",
    "internal_note.created": "note.created",
    "tag.added": "ticket.tag_added",
    "ticket.tagged": "ticket.tag_added",
    "tag.removed": "ticket.tag_removed",
    "ticket.untagged": "ticket.tag_removed",
    "chat.session_started": "chat.started",
    "chat.session_ended": "chat.ended",
}


@pytest.fixture
def admin_client(db):
    with override_settings(ESCALATED={"UI_ENABLED": True}):
        client = Client()
        client.force_login(UserFactory(username="vocab_admin", is_staff=True, is_superuser=True))
        yield client


def test_legacy_aliases_are_the_adr_table():
    assert LEGACY_EVENT_NAMES == ADR_LEGACY
    for legacy, canonical in ADR_LEGACY.items():
        assert canonical_event(legacy) == canonical
        assert canonical in CANONICAL_EVENTS


def test_webhook_form_offers_only_canonical_names():
    offered = set(WebhookSerializer.AVAILABLE_EVENTS)
    assert {"note.created", "ticket.tag_added", "ticket.tag_removed", "reply.created"} <= offered
    assert not offered & set(LEGACY_EVENT_NAMES)
    assert offered <= set(CANONICAL_EVENTS)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "emit, event",
    [
        (lambda s, t, a: s.add_note(t, a, "Checked the logs"), "note.created"),
        (lambda s, t, a: s.add_tags(t, a, [TagFactory().pk]), "ticket.tag_added"),
    ],
)
def test_events_are_dispatched_under_canonical_names(emit, event):
    ticket = TicketFactory()
    with patch.object(WebhookDispatcher, "dispatch") as dispatch:
        emit(TicketService(), ticket, UserFactory())
    dispatched = [call.args[0] for call in dispatch.call_args_list]
    assert event in dispatched
    assert not set(dispatched) & set(LEGACY_EVENT_NAMES)


@pytest.mark.django_db
def test_tag_removed_is_dispatched_as_ticket_tag_removed():
    ticket = TicketFactory()
    tag = TagFactory()
    ticket.tags.add(tag)
    with patch.object(WebhookDispatcher, "dispatch") as dispatch:
        TicketService().remove_tags(ticket, UserFactory(), [tag.pk])
    assert "ticket.tag_removed" in [call.args[0] for call in dispatch.call_args_list]


@pytest.mark.parametrize("legacy, canonical", list(ADR_LEGACY.items()))
def test_a_webhook_stored_under_a_legacy_name_is_subscribed_to_the_canonical_one(legacy, canonical):
    webhook = Webhook(url="https://example.com/hook", events=[legacy])
    assert webhook.subscribed_to(canonical)
    assert webhook.subscribed_events() == [canonical]


@pytest.mark.django_db
def test_a_legacy_webhook_subscription_still_receives_the_event():
    webhook = WebhookFactory(events=["internal_note.added"], active=True)
    with (
        patch("escalated.outbound_security.socket.getaddrinfo", return_value=PUBLIC_ADDRINFO),
        patch("escalated.services.webhook_dispatcher.requests.post") as post,
    ):
        post.return_value = MagicMock(status_code=200, text="OK", ok=True)
        TicketService().add_note(TicketFactory(), UserFactory(), "Checked the logs")

    delivery = WebhookDelivery.objects.get(webhook=webhook)
    assert delivery.event == "note.created"


@pytest.mark.django_db
def test_the_webhook_edit_page_shows_legacy_subscriptions_under_canonical_names(admin_client):
    webhook = WebhookFactory(events=["tag.added", "ticket.tag_added", "internal_note.added"])
    response = admin_client.get(f"/support/admin/webhooks/{webhook.pk}/edit/", **INERTIA)
    assert response.status_code == 200
    props = json.loads(response.content)["props"]
    assert props["webhook"]["events"] == ["ticket.tag_added", "note.created"]


@pytest.mark.django_db
def test_saving_a_webhook_stores_canonical_names(admin_client):
    with patch("escalated.outbound_security.socket.getaddrinfo", return_value=PUBLIC_ADDRINFO):
        admin_client.post(
            "/support/admin/webhooks/create/",
            data=json.dumps({"url": "https://example.com/hook", "events": ["tag.removed", "reply.created"]}),
            content_type="application/json",
            **INERTIA,
        )
    assert Webhook.objects.get().events == ["ticket.tag_removed", "reply.created"]


@pytest.mark.django_db
def test_a_workflow_saved_with_the_legacy_reply_trigger_is_stored_canonically(admin_client):
    body = {
        "name": "Bump on reply",
        "trigger_event": "ticket.replied",
        "conditions": {"all": []},
        "actions": [{"type": "change_priority", "value": "urgent"}],
        "is_active": True,
    }
    admin_client.post("/support/admin/workflows/", data=json.dumps(body), content_type="application/json", **INERTIA)
    assert Workflow.objects.get().trigger_event == "reply.created"


@pytest.mark.django_db
def test_a_stored_legacy_reply_workflow_still_fires_and_is_shown_canonically(admin_client):
    workflow = Workflow.objects.create(
        name="Legacy",
        trigger_event="ticket.replied",
        conditions={"all": []},
        actions=[{"type": "change_priority", "value": "urgent"}],
    )
    response = admin_client.get(f"/support/admin/workflows/{workflow.pk}/", **INERTIA)
    props = json.loads(response.content)["props"]
    assert props["workflow"]["trigger_event"] == "reply.created"
    assert props["workflow"]["trigger"] == "reply.created"

    ticket = TicketFactory(priority="low")
    reply = Reply.objects.create(ticket=ticket, body="thanks")
    esc_signals.reply_created.send(sender=Reply, reply=reply, ticket=ticket, user=None)
    ticket.refresh_from_db()
    assert ticket.priority == "urgent"
