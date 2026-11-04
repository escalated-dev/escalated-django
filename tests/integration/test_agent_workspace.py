"""
What the agent ticket page needs beyond the ticket itself: the agents it can
be reassigned to, the requester's other tickets, and snoozing from the agent
panel (until now only the admin panel could snooze). Mirrors
escalated-laravel's tests/Feature/Agent/AgentWorkspaceTest.php.
"""

import json
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from escalated import access
from escalated.models import Ticket
from escalated.route_list import escalated_routes
from tests.factories import DepartmentFactory, TicketFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def department_visibility(settings):
    settings.ESCALATED = {**settings.ESCALATED, "VISIBILITY": "department"}


def agent(name="Ada Agent", username="ada", department=None):
    first, last = name.split(" ")
    user = UserFactory(username=username, first_name=first, last_name=last)
    (department or DepartmentFactory()).agents.add(user)
    return user


def show_props(client, user, ticket):
    client.force_login(user)
    response = client.get(reverse("escalated:agent_ticket_show", args=[ticket.pk]), HTTP_X_INERTIA="true")
    assert response.status_code == 200, response.content[:500]
    return response.json()["props"]


def created(ticket, when):
    Ticket.unrestricted.filter(pk=ticket.pk).update(created_at=when)
    return ticket


def snooze(client, user, ticket, until):
    client.force_login(user)
    return client.post(
        reverse("escalated:agent_ticket_snooze", args=[ticket.pk]),
        json.dumps({"snoozed_until": until}),
        content_type="application/json",
    )


# --- Reassigning ------------------------------------------------------------


def test_sends_the_agents_and_admins_a_ticket_can_be_assigned_to_by_id_and_name(client):
    ada = agent()
    admin = UserFactory(username="al", first_name="Al", last_name="Admin", is_staff=True, is_superuser=True)
    UserFactory(username="cass", first_name="Cass", last_name="Customer")
    ticket = TicketFactory()

    agents = show_props(client, ada, ticket)["agents"]

    assert agents == [{"id": ada.pk, "name": "Ada Agent"}, {"id": admin.pk, "name": "Al Admin"}]


def test_leaves_out_agents_who_cannot_see_the_ticket_under_department_visibility(client, department_visibility):
    department = DepartmentFactory()
    ada = agent(department=department)
    agent("Otto Other", "otto")
    ticket = TicketFactory(department=department)

    names = [row["name"] for row in show_props(client, ada, ticket)["agents"]]

    assert "Ada Agent" in names
    assert "Otto Other" not in names


# --- The requester's other tickets ------------------------------------------


def test_sends_the_requesters_other_tickets_newest_first_at_most_five(client):
    ada = agent()
    customer = UserFactory(username="cass")
    now = timezone.now()
    older = [
        created(TicketFactory(requester=customer, subject=f"Earlier {i}"), now - timedelta(days=10 - i))
        for i in range(1, 7)
    ]
    TicketFactory(requester=UserFactory(username="someone"), subject="Someone else")
    ticket = TicketFactory(requester=customer)

    recent = show_props(client, ada, ticket)["ticket"]["requester_tickets"]

    assert [row["subject"] for row in recent] == ["Earlier 6", "Earlier 5", "Earlier 4", "Earlier 3", "Earlier 2"]
    assert list(recent[0]) == ["id", "reference", "subject", "status", "created_at", "updated_at"]
    assert recent[0]["reference"] == older[5].reference
    assert recent[0]["status"] == "open"
    assert recent[0]["created_at"] == (now - timedelta(days=4)).isoformat()


def test_matches_a_guest_requesters_other_tickets_by_email(client):
    ada = agent()
    TicketFactory(guest_email="guest@example.com", guest_name="Gus", subject="Earlier guest ticket")
    TicketFactory(guest_email="other@example.com", subject="Another guest")
    ticket = TicketFactory(guest_email="guest@example.com", guest_name="Gus")

    recent = show_props(client, ada, ticket)["ticket"]["requester_tickets"]

    assert [row["subject"] for row in recent] == ["Earlier guest ticket"]


def test_only_lists_requester_tickets_the_agent_may_see(client, department_visibility):
    department = DepartmentFactory()
    ada = agent(department=department)
    customer = UserFactory(username="cass")
    TicketFactory(requester=customer, department=department, subject="Visible")
    TicketFactory(requester=customer, department=DepartmentFactory(), subject="Hidden")
    ticket = TicketFactory(requester=customer, department=department)

    recent = show_props(client, ada, ticket)["ticket"]["requester_tickets"]

    assert [row["subject"] for row in recent] == ["Visible"]


def test_sends_an_empty_list_for_a_ticket_with_no_known_requester(client):
    ada = agent()
    TicketFactory()
    ticket = TicketFactory()

    assert show_props(client, ada, ticket)["ticket"]["requester_tickets"] == []


# --- Snoozing from the agent panel ------------------------------------------


def test_lets_an_agent_snooze_a_ticket(client):
    ada = agent()
    ticket = TicketFactory(status="open")
    until = (timezone.now() + timedelta(days=1)).replace(second=0, microsecond=0)

    response = snooze(client, ada, ticket, until.isoformat())

    assert response.status_code == 302
    assert response.url == reverse("escalated:agent_ticket_show", args=[ticket.pk])
    ticket.refresh_from_db()
    assert ticket.snoozed_until == until
    assert ticket.snoozed_by_id == ada.pk


@pytest.mark.parametrize("value", [None, "", "not a date", "PAST"])
def test_rejects_a_missing_invalid_or_past_snooze_time(client, value):
    ada = agent()
    ticket = TicketFactory()
    if value == "PAST":
        value = (timezone.now() - timedelta(hours=1)).isoformat()

    response = snooze(client, ada, ticket, value)

    assert response.status_code == 422
    assert "snoozed_until" in response.json()["errors"]
    ticket.refresh_from_db()
    assert ticket.snoozed_until is None


def test_lets_an_agent_unsnooze_a_ticket(client):
    ada = agent()
    ticket = TicketFactory(status="in_progress")
    snooze(client, ada, ticket, (timezone.now() + timedelta(days=1)).isoformat())

    response = client.post(reverse("escalated:agent_ticket_unsnooze", args=[ticket.pk]))

    assert response.status_code == 302
    ticket.refresh_from_db()
    assert ticket.snoozed_until is None
    assert ticket.status == "in_progress"


def test_does_not_let_a_customer_snooze_through_the_agent_panel(client):
    customer = UserFactory(username="cass")
    ticket = TicketFactory(requester=customer)

    response = snooze(client, customer, ticket, (timezone.now() + timedelta(days=1)).isoformat())

    assert response.status_code == 403
    ticket.refresh_from_db()
    assert ticket.snoozed_until is None


def test_does_not_let_an_agent_snooze_a_ticket_outside_their_departments(client, department_visibility):
    ada = agent()
    ticket = TicketFactory(department=DepartmentFactory())

    response = snooze(client, ada, ticket, (timezone.now() + timedelta(days=1)).isoformat())

    assert response.status_code == 404
    assert Ticket.unrestricted.get(pk=ticket.pk).snoozed_until is None


def test_maps_the_agent_snooze_routes_to_the_ticket_edit_permission():
    assert access.mapped_permissions("agent_ticket_snooze") == ["ticket.edit"]
    assert access.mapped_permissions("agent_ticket_unsnooze") == ["ticket.edit"]


def test_needs_ticket_edit_to_snooze_when_roles_and_permissions_are_on(client, settings):
    call_command("seed_permissions", verbosity=0)
    settings.ESCALATED = {**settings.ESCALATED, "ACCESS": {"roles_permissions": True}}
    ada = agent()
    ticket = TicketFactory()

    response = snooze(client, ada, ticket, (timezone.now() + timedelta(days=1)).isoformat())

    assert response.status_code == 403
    ticket.refresh_from_db()
    assert ticket.snoozed_until is None


def test_serves_the_agent_snooze_route_names_to_the_frontend():
    routes = escalated_routes()

    assert routes["escalated.agent.tickets.snooze"]["methods"] == ["POST"]
    assert routes["escalated.agent.tickets.unsnooze"]["methods"] == ["POST"]
