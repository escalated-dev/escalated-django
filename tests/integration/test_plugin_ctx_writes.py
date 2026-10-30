"""ctx writes take only the plugin contract's fields.

domain-model/plugin-contract.md: ``ctx.replies.create``, ``ctx.tickets.create``,
``ctx.tickets.update``, ``ctx.contacts.create`` and ``ctx.tags.create`` take the
contract's fields. They passed the plugin's data straight to
``objects.create(**data)`` / ``setattr``, so a plugin could name a reply's
author and flags, a ticket's requester and assignee, or create a superuser.
Any other key is now an error, never an attribute.
"""

import pytest

from escalated.bridge.context_handler import ContextHandler
from escalated.models import Contact, Reply, Tag, Ticket
from tests.factories import TicketFactory, UserFactory


def handler(user=None):
    h = ContextHandler()
    h.set_current_plugin("acme")
    if user is not None:
        h.set_acting_user(user)
    return h


@pytest.mark.django_db
def test_reply_create_writes_as_the_acting_user_or_a_note():
    agent = UserFactory(username="ctx_writes_agent")
    ticket = TicketFactory()

    reply = handler(agent).handle("ctx.replies.create", {"data": {"ticket_id": ticket.pk, "body": "Synced"}})
    note = handler().handle(
        "ctx.replies.create", {"data": {"ticket_id": ticket.pk, "body": "Inner", "is_internal": True}}
    )

    reply_row = Reply.objects.get(pk=reply["id"])
    note_row = Reply.objects.get(pk=note["id"])
    assert (reply_row.ticket_id, reply_row.is_internal_note, reply_row.type, reply_row.author_id) == (
        ticket.pk,
        False,
        Reply.Type.REPLY,
        agent.pk,
    )
    assert (note_row.is_internal_note, note_row.type, note_row.author_id) == (True, Reply.Type.NOTE, None)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "key,value",
    [
        ("author", 1),
        ("author_id", 1),
        ("is_internal_note", True),
        ("type", "system"),
        ("is_pinned", True),
        ("is_deleted", True),
        ("metadata", {"x": 1}),
        ("id", 999),
    ],
)
def test_reply_create_rejects_fields_outside_the_contract(key, value):
    ticket = TicketFactory()

    with pytest.raises(ValueError, match="does not accept"):
        handler().handle("ctx.replies.create", {"data": {"ticket_id": ticket.pk, "body": "x", key: value}})
    assert not Reply.objects.filter(ticket=ticket).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("data", [{"body": "x"}, {"ticket_id": 999999, "body": "x"}, {"ticket_id": 1, "body": " "}])
def test_reply_create_requires_an_existing_ticket_and_a_body(data):
    with pytest.raises(ValueError):
        handler().handle("ctx.replies.create", {"data": data})


@pytest.mark.django_db
def test_ticket_create_takes_the_contract_fields_and_aliases():
    created = handler().handle(
        "ctx.tickets.create",
        {
            "data": {
                "title": "From Slack",
                "description": "Help",
                "priority": "high",
                "metadata": {"slack_ts": "1.2"},
                "requester_email": "Pat@Example.com",
                "requester_name": "Pat",
            }
        },
    )

    row = Ticket.objects.get(pk=created["id"])
    assert (row.subject, row.description, row.priority, row.channel) == ("From Slack", "Help", "high", "api")
    assert row.metadata == {"slack_ts": "1.2"}
    assert row.requester_object_id is None
    assert row.assigned_to_id is None
    assert Contact.objects.get(pk=row.contact_id).email == "pat@example.com"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "key,value",
    [
        ("requester_object_id", "1"),
        ("requester_content_type", 1),
        ("assigned_to", 1),
        ("assigned_to_id", 1),
        ("reference", "ESC-1"),
        ("guest_token", "x"),
        ("sla_first_response_breached", True),
    ],
)
def test_ticket_create_rejects_fields_outside_the_contract(key, value):
    with pytest.raises(ValueError, match="does not accept"):
        handler().handle("ctx.tickets.create", {"data": {"subject": "S", key: value}})
    assert not Ticket.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "key,value",
    [
        ("assigned_to", 1),
        ("assigned_to_id", 1),
        ("requester_object_id", "1"),
        ("channel", "email"),
        ("requester_email", "a@b.c"),
        ("resolved_at", "2026-01-01T00:00:00Z"),
    ],
)
def test_ticket_update_rejects_fields_outside_the_contract(key, value):
    ticket = TicketFactory(subject="Original")

    with pytest.raises(ValueError, match="does not accept"):
        handler().handle("ctx.tickets.update", {"id": ticket.pk, "data": {"subject": "Changed", key: value}})
    assert Ticket.objects.get(pk=ticket.pk).subject == "Original"


@pytest.mark.django_db
def test_ticket_update_takes_the_contract_fields():
    ticket = TicketFactory(subject="Original", priority=Ticket.Priority.LOW)

    handler().handle(
        "ctx.tickets.update", {"id": ticket.pk, "data": {"title": "Renamed", "body": "New body", "priority": "urgent"}}
    )

    row = Ticket.objects.get(pk=ticket.pk)
    assert (row.subject, row.description, row.priority) == ("Renamed", "New body", "urgent")


@pytest.mark.django_db
def test_contact_and_tag_create_take_their_contract_fields_only():
    with pytest.raises(ValueError, match="does not accept"):
        handler().handle(
            "ctx.contacts.create",
            {"data": {"username": "eve", "email": "eve@example.com", "is_superuser": True, "is_staff": True}},
        )
    with pytest.raises(ValueError, match="does not accept"):
        handler().handle("ctx.tags.create", {"data": {"name": "VIP", "id": 5}})

    tag = handler().handle("ctx.tags.create", {"data": {"name": "VIP", "color": "#ff0000"}})
    row = Tag.objects.get(pk=tag["id"])
    assert (row.name, row.slug, row.color) == ("VIP", "vip", "#ff0000")
