"""
@mentions, as escalated-laravel's MentionService, MentionNotification and
AgentSearchController: agents mentioned in an agent's reply or internal note
get a ``mention`` notification (feed and email), and the composer's mention
picker searches agents at ``admin/agents/search/``.
"""

import pytest
from django.urls import reverse

from escalated.mention_models import Mention
from escalated.models import AgentNotification
from tests.factories import ReplyFactory, TicketFactory, UserFactory

pytestmark = pytest.mark.django_db

JSON = {"HTTP_ACCEPT": "application/json"}


@pytest.fixture
def agent(agent_user):
    agent_user.first_name, agent_user.last_name = "Agent", "Smith"
    agent_user.save()
    return agent_user


@pytest.fixture
def alice(agent_user):
    user = UserFactory(username="alice", first_name="Alice", last_name="Jones", email="alice@example.com")
    agent_user.escalated_departments.first().agents.add(user)
    return user


@pytest.fixture
def bob(agent_user):
    user = UserFactory(username="bob", first_name="Bob", last_name="Smith", email="bob@example.com")
    agent_user.escalated_departments.first().agents.add(user)
    return user


@pytest.fixture
def customer(db):
    return UserFactory(username="customer", first_name="Carl", last_name="Customer")


def feed(client, user):
    client.force_login(user)
    response = client.get(reverse("escalated:agent_notifications"), **JSON)
    assert response.status_code == 200
    return response.json()["data"]


def test_agents_mentioned_in_a_note_are_notified(client, agent, alice, bob, customer):
    ticket = TicketFactory(requester=customer)
    reply = ReplyFactory(ticket=ticket, author=agent, is_internal_note=True, body="Ping @alice and @{Bob Smith}")

    assert set(Mention.objects.filter(reply=reply).values_list("user_id", flat=True)) == {alice.pk, bob.pk}
    items = feed(client, alice)
    assert [(i["type"], i["title"]) for i in items] == [("mention", f"Agent Smith mentioned you on {ticket.reference}")]
    assert items[0]["ticket"]["id"] == ticket.pk
    assert [i["type"] for i in feed(client, bob)] == ["mention"]


def test_a_mention_in_an_agent_reply_matches_name_or_email_ignoring_case(client, agent, alice, bob, customer):
    ticket = TicketFactory(requester=customer)
    ReplyFactory(ticket=ticket, author=agent, body="cc @ALICE and @{bob smith}")
    assert [i["type"] for i in feed(client, alice)] == ["mention"]
    assert [i["type"] for i in feed(client, bob)] == ["mention"]


def test_the_mentioned_agent_gets_an_email(agent, alice, customer, mailoutbox, settings):
    settings.ESCALATED = {**settings.ESCALATED, "NOTIFICATION_CHANNELS": ["email"]}
    ticket = TicketFactory(requester=customer)
    ReplyFactory(ticket=ticket, author=agent, is_internal_note=True, body="@alice please look")
    assert [m.to for m in mailoutbox] == [["alice@example.com"]]
    assert ticket.reference in mailoutbox[0].subject


def test_nobody_is_notified_of_their_own_mention_customers_or_unknown_names(client, agent, alice, customer):
    ticket = TicketFactory(requester=customer)
    ReplyFactory(ticket=ticket, author=agent, is_internal_note=True, body="@{Agent Smith} @nobody @customer")
    ReplyFactory(ticket=ticket, author=customer, body="Hi @alice")
    assert AgentNotification.objects.count() == 0
    assert Mention.objects.count() == 0


def test_the_mention_picker_lists_agents_by_name_or_email(client, admin_user, agent, alice, bob, customer):
    client.force_login(admin_user)
    url = reverse("escalated:admin_agents_search")
    response = client.get(url, {"q": "bob"}, **JSON)
    assert response.status_code == 200
    assert response.json() == [{"id": bob.pk, "name": "Bob Smith", "email": "bob@example.com"}]
    assert client.get(url, {"q": "carl"}, **JSON).json() == []
    assert client.get(url, {"q": ""}, **JSON).json() == []


def test_the_mention_picker_is_an_admin_route_as_in_laravel(client, agent):
    client.force_login(agent)
    response = client.get(reverse("escalated:admin_agents_search"), {"q": "a"}, **JSON)
    assert response.status_code == 403


def test_the_mention_picker_has_the_laravel_route_name():
    from escalated.route_list import escalated_routes

    assert escalated_routes()["escalated.admin.agents.search"]["uri"].endswith("admin/agents/search/")
