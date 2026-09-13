"""
Admin-configured webhooks (the Webhook model and the admin Webhooks pages)
must receive the events the admin form offers.

WebhookDispatcher existed, but nothing connected it to the ticket signals: its
only caller was the manual "retry delivery" view. A webhook subscribed to
ticket.created never received a delivery.
"""

import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from escalated.models import Ticket, WebhookDelivery
from escalated.serializers import WebhookSerializer
from escalated.services.sla_service import SlaService
from escalated.services.ticket_service import TicketService
from escalated.services.webhook_dispatcher import WebhookDispatcher
from tests.factories import DepartmentFactory, TagFactory, TicketFactory, UserFactory, WebhookFactory

PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 443))]

# Every event the admin Webhooks form offers, and the signal that carries it.
OFFERED_EVENT_SIGNALS = {
    "ticket.created": "ticket_created",
    "ticket.updated": "ticket_updated",
    "ticket.status_changed": "ticket_status_changed",
    "ticket.resolved": "ticket_resolved",
    "ticket.closed": "ticket_closed",
    "ticket.reopened": "ticket_reopened",
    "ticket.assigned": "ticket_assigned",
    "ticket.unassigned": "ticket_unassigned",
    "ticket.escalated": "ticket_escalated",
    "ticket.priority_changed": "ticket_priority_changed",
    "ticket.department_changed": "department_changed",
    "reply.created": "reply_created",
    "internal_note.added": "internal_note_added",
    "sla.breached": "sla_breached",
    "sla.warning": "sla_warning",
    "tag.added": "tag_added",
    "tag.removed": "tag_removed",
}


def test_every_offered_event_is_covered_here():
    assert sorted(OFFERED_EVENT_SIGNALS) == sorted(WebhookSerializer.AVAILABLE_EVENTS)


@pytest.mark.django_db
def test_creating_a_ticket_delivers_to_a_subscribed_webhook():
    webhook = WebhookFactory(events=["ticket.created"], active=True)
    requester = UserFactory()

    with (
        patch("escalated.outbound_security.socket.getaddrinfo", return_value=PUBLIC_ADDRINFO),
        patch("escalated.services.webhook_dispatcher.requests.post") as post,
    ):
        post.return_value = MagicMock(status_code=200, text="OK", ok=True)
        ticket = TicketService().create(requester, {"subject": "Printer on fire", "description": "Help"})

    deliveries = WebhookDelivery.objects.filter(webhook=webhook)
    assert deliveries.count() == 1
    delivery = deliveries.get()
    assert delivery.event == "ticket.created"
    assert delivery.payload["ticket_id"] == ticket.pk
    assert delivery.payload["reference"] == ticket.reference
    assert post.call_count == 1


@pytest.mark.django_db
def test_unsubscribed_and_inactive_webhooks_get_nothing():
    WebhookFactory(events=["ticket.closed"], active=True)
    WebhookFactory(events=["ticket.created"], active=False)

    with patch("escalated.services.webhook_dispatcher.requests.post") as post:
        TicketService().create(UserFactory(), {"subject": "Printer on fire", "description": "Help"})

    post.assert_not_called()
    assert WebhookDelivery.objects.count() == 0


def _create(service, ticket, actor):
    return service.create(actor, {"subject": "Printer on fire", "description": "Help"})


def _remove_tag(service, ticket, actor):
    tag = TagFactory()
    ticket.tags.add(tag)
    service.remove_tags(ticket, actor, [tag.pk])


def _breach_sla(service, ticket, actor):
    ticket.first_response_due_at = timezone.now() - timedelta(hours=1)
    ticket.save(update_fields=["first_response_due_at"])
    assert SlaService.check_breach(ticket)


def _warn_sla(service, ticket, actor):
    ticket.first_response_due_at = timezone.now() + timedelta(minutes=10)
    ticket.save(update_fields=["first_response_due_at"])
    assert SlaService.check_warning(ticket)


# How each offered event is produced in the running application.
EMITTERS = {
    "ticket.created": _create,
    "ticket.updated": lambda s, t, a: s.update(t, a, {"subject": "A new subject"}),
    "ticket.status_changed": lambda s, t, a: s.change_status(t, a, Ticket.Status.IN_PROGRESS),
    "ticket.resolved": lambda s, t, a: s.resolve(t, a),
    "ticket.closed": lambda s, t, a: s.close(t, a),
    "ticket.reopened": lambda s, t, a: s.reopen(t, a),
    "ticket.assigned": lambda s, t, a: s.assign(t, a, UserFactory()),
    "ticket.unassigned": lambda s, t, a: s.unassign(t, a),
    "ticket.escalated": lambda s, t, a: s.escalate(t, a),
    "ticket.priority_changed": lambda s, t, a: s.change_priority(t, a, Ticket.Priority.URGENT),
    "ticket.department_changed": lambda s, t, a: s.change_department(t, a, DepartmentFactory()),
    "reply.created": lambda s, t, a: s.reply(t, a, {"body": "On it"}),
    "internal_note.added": lambda s, t, a: s.add_note(t, a, "Checked the logs"),
    "sla.breached": _breach_sla,
    "sla.warning": _warn_sla,
    "tag.added": lambda s, t, a: s.add_tags(t, a, [TagFactory().pk]),
    "tag.removed": _remove_tag,
}


def test_every_offered_event_has_an_emitter_here():
    assert sorted(EMITTERS) == sorted(WebhookSerializer.AVAILABLE_EVENTS)


@pytest.mark.django_db
@pytest.mark.parametrize("event", WebhookSerializer.AVAILABLE_EVENTS)
def test_offered_event_reaches_the_dispatcher(event):
    actor = UserFactory()
    start_status = Ticket.Status.RESOLVED if event == "ticket.reopened" else Ticket.Status.OPEN
    ticket = TicketFactory(status=start_status, assigned_to=UserFactory())

    with patch.object(WebhookDispatcher, "dispatch") as dispatch:
        EMITTERS[event](TicketService(), ticket, actor)

    dispatched = [call.args[0] for call in dispatch.call_args_list]
    assert event in dispatched

    payload = next(call.args[1] for call in dispatch.call_args_list if call.args[0] == event)
    # WebhookDispatcher.send() json.dumps the payload and stores it in a JSONField.
    json.dumps(payload)
    if event.startswith(("ticket.", "reply.", "internal_note.", "sla.", "tag.")):
        assert payload["ticket_id"] is not None


def test_offered_events_have_a_webhook_receiver_after_setup_alone():
    """Receivers must be connected by django.setup(), not by importing the URL conf."""
    script = """
import json
import os

import django

django.setup()

import escalated.signals as signals

found = {}
for name in json.loads(os.environ["ESCALATED_SIGNAL_NAMES"]):
    live = getattr(signals, name)._live_receivers(object)
    receivers = list(live[0]) + list(live[1]) if isinstance(live, tuple) else list(live)
    found[name] = sorted({receiver.__module__ for receiver in receivers})
print(json.dumps(found))
"""

    repo_root = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "tests.settings",
        "PYTHONPATH": os.pathsep.join(filter(None, [str(repo_root), os.environ.get("PYTHONPATH")])),
        "ESCALATED_SIGNAL_NAMES": json.dumps(sorted(set(OFFERED_EVENT_SIGNALS.values()))),
    }
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    found = json.loads(result.stdout.strip().splitlines()[-1])

    missing = sorted(name for name, modules in found.items() if "escalated.webhook_handlers" not in modules)
    assert missing == []
