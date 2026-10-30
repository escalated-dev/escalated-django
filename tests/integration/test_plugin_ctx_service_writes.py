"""ctx ticket and reply writes go through the ticket service.

domain-model/plugin-contract.md: ``ctx.tickets.create/update`` and
``ctx.replies.create`` go through the host's ticket service, so a plugin's
ticket or reply gets the same activity log, SLA, canonical events, workflows
and webhooks as one written over the HTTP API. They wrote the models directly,
so none of that ran. A plugin's own write does not re-deliver the event it is
handling back to plugins.
"""

import pytest

from escalated.bridge.context_handler import ContextHandler
from escalated.hooks import add_action, remove_action
from escalated.models import Ticket, TicketActivity
from tests.factories import DepartmentFactory, SlaPolicyFactory, TicketFactory, UserFactory


def handler(user=None):
    h = ContextHandler()
    h.set_current_plugin("acme")
    if user is not None:
        h.set_acting_user(user)
    return h


def activity_types(ticket):
    return list(TicketActivity.objects.filter(ticket=ticket).order_by("pk").values_list("type", flat=True))


@pytest.fixture
def listen():
    registered = []

    def _listen(*names):
        seen = []
        for name in names:

            def callback(payload, _name=name):
                seen.append((_name, payload))

            add_action(name, callback)
            registered.append((name, callback))
        return seen

    def _on(name, callback):
        add_action(name, callback)
        registered.append((name, callback))

    _listen.on = _on
    yield _listen
    for name, callback in registered:
        remove_action(name, callback)


@pytest.mark.django_db
def test_ticket_create_logs_attaches_the_sla_and_announces(listen, django_capture_on_commit_callbacks):
    SlaPolicyFactory(is_default=True, is_active=True)
    seen = listen("ticket.created")

    with django_capture_on_commit_callbacks(execute=True):
        created = handler().handle("ctx.tickets.create", {"data": {"subject": "From a plugin"}})

    ticket = Ticket.objects.get(pk=created["id"])
    assert ticket.sla_policy_id is not None
    assert activity_types(ticket) == [TicketActivity.ActivityType.CREATED]
    assert [name for name, _ in seen] == ["ticket.created"]
    assert seen[0][1]["id"] == ticket.pk


@pytest.mark.django_db
def test_ticket_create_reaches_a_requested_status_as_a_status_change(listen, django_capture_on_commit_callbacks):
    agent = UserFactory(username="ctx_service_status_agent")
    seen = listen("ticket.status_changed")

    with django_capture_on_commit_callbacks(execute=True):
        created = handler(agent).handle(
            "ctx.tickets.create", {"data": {"subject": "Waiting", "status": "waiting_on_customer"}}
        )

    ticket = Ticket.objects.get(pk=created["id"])
    assert ticket.status == Ticket.Status.WAITING_ON_CUSTOMER
    causers = TicketActivity.objects.filter(ticket=ticket, type=TicketActivity.ActivityType.STATUS_CHANGED).values_list(
        "causer_object_id", flat=True
    )
    assert str(agent.pk) in [str(causer) for causer in causers]
    assert [name for name, _ in seen] == ["ticket.status_changed"]


@pytest.mark.django_db
def test_ticket_update_changes_status_priority_and_department_through_the_service(
    listen, django_capture_on_commit_callbacks
):
    agent = UserFactory(username="ctx_service_update_agent")
    department = DepartmentFactory()
    ticket = TicketFactory(status=Ticket.Status.OPEN, priority=Ticket.Priority.LOW)
    seen = listen("ticket.status_changed", "ticket.priority_changed", "ticket.department_changed", "ticket.updated")

    with django_capture_on_commit_callbacks(execute=True):
        handler(agent).handle(
            "ctx.tickets.update",
            {
                "id": ticket.pk,
                "data": {
                    "title": "Renamed",
                    "status": "in_progress",
                    "priority": "urgent",
                    "department_id": department.pk,
                },
            },
        )

    ticket.refresh_from_db()
    assert (ticket.subject, ticket.status, ticket.priority, ticket.department_id) == (
        "Renamed",
        Ticket.Status.IN_PROGRESS,
        Ticket.Priority.URGENT,
        department.pk,
    )
    assert set(activity_types(ticket)) >= {
        TicketActivity.ActivityType.STATUS_CHANGED,
        TicketActivity.ActivityType.PRIORITY_CHANGED,
        TicketActivity.ActivityType.DEPARTMENT_CHANGED,
    }
    assert sorted(name for name, _ in seen) == [
        "ticket.department_changed",
        "ticket.priority_changed",
        "ticket.status_changed",
        "ticket.updated",
    ]


@pytest.mark.django_db
def test_reply_create_logs_and_announces_replies_and_notes(listen, django_capture_on_commit_callbacks):
    agent = UserFactory(username="ctx_service_reply_agent")
    ticket = TicketFactory(status=Ticket.Status.OPEN)
    seen = listen("reply.created", "note.created")

    with django_capture_on_commit_callbacks(execute=True):
        handler(agent).handle("ctx.replies.create", {"data": {"ticket_id": ticket.pk, "body": "Synced"}})
        handler(agent).handle(
            "ctx.replies.create", {"data": {"ticket_id": ticket.pk, "body": "Note", "is_internal": True}}
        )

    assert TicketActivity.ActivityType.REPLY_ADDED in activity_types(ticket)
    assert [name for name, _ in seen] == ["reply.created", "note.created"]
    # An agent's public reply waits on the customer, as over the API.
    ticket.refresh_from_db()
    assert ticket.status == Ticket.Status.WAITING_ON_CUSTOMER


@pytest.mark.django_db
def test_a_plugin_write_does_not_redeliver_the_event_it_is_handling(listen, django_capture_on_commit_callbacks):
    calls = []

    def follow_up(payload):
        calls.append(payload["id"])
        if len(calls) > 5:
            return
        handler().handle("ctx.tickets.create", {"data": {"subject": "Follow-up"}})

    listen.on("ticket.created", follow_up)

    with django_capture_on_commit_callbacks(execute=True):
        handler().handle("ctx.tickets.create", {"data": {"subject": "First"}})

    assert len(calls) == 1
    assert Ticket.objects.count() == 2


@pytest.mark.django_db
def test_other_events_a_plugin_write_raises_are_still_delivered(listen, django_capture_on_commit_callbacks):
    def thank(payload):
        handler().handle("ctx.replies.create", {"data": {"ticket_id": payload["id"], "body": "Thanks"}})

    listen.on("ticket.created", thank)
    seen = listen("reply.created")

    with django_capture_on_commit_callbacks(execute=True):
        handler().handle("ctx.tickets.create", {"data": {"subject": "First"}})

    assert [name for name, _ in seen] == ["reply.created"]
