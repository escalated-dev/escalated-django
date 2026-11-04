"""The agent panel's optional ``inbox`` and ``queue`` props, and the list
filters its rail, views and stat strip link to (shared frontend
docs/agent-panel.md), as escalated-laravel sends them.

Every number here must be what the agent would get by opening the list it
labels, so the tests check counts against the list and against visibility.
"""

import json
import os
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from escalated.models import SavedView, Ticket
from tests.factories import DepartmentFactory, ReplyFactory, TicketFactory, UserFactory

pytestmark = pytest.mark.django_db

BUILT_IN_VIEW_IDS = ["urgent", "sla_at_risk", "waiting_on_me", "waiting_on_customer", "recently_updated"]
MANIFEST = os.path.join(os.path.dirname(__file__), "..", "fixtures", "escalated-pages.json")


@pytest.fixture(autouse=True)
def _no_inbox_cache(settings):
    settings.ESCALATED = {**settings.ESCALATED, "AGENT_INBOX_CACHE_SECONDS": 0}


@pytest.fixture
def other_agent(db, agent_user):
    other = UserFactory(username="other-agent")
    agent_user.escalated_departments.first().agents.add(other)
    return other


def page(client, user, params=None, path=None):
    client.force_login(user)
    response = client.get(path or reverse("escalated:agent_ticket_list"), params or {}, HTTP_X_INERTIA="true")
    assert response.status_code == 200, response.content[:500]
    return response.json()


def show_path(ticket):
    return reverse("escalated:agent_ticket_show", args=[ticket.pk])


def inbox_ticket(**attributes):
    return TicketFactory(**{"priority": "low", "status": "open", **attributes})


def test_sends_inbox_counts_built_in_views_stats_and_the_queue(client, agent_user, other_agent):
    agent = agent_user
    inbox_ticket(assigned_to=agent, priority="urgent")
    inbox_ticket(assigned_to=agent, status="waiting_on_customer")
    inbox_ticket(assigned_to=agent, status="resolved", resolved_at=timezone.now())
    inbox_ticket(assigned_to=agent, status="resolved", resolved_at=timezone.now() - timedelta(days=2))
    inbox_ticket(assigned_to=agent, snoozed_until=timezone.now() + timedelta(days=1))
    inbox_ticket()
    inbox_ticket(status="closed")
    inbox_ticket(assigned_to=other_agent)

    result = page(client, agent)
    assert result["component"] == "Escalated/Agent/TicketIndex"

    inbox = result["props"]["inbox"]
    assert list(inbox) == ["counts", "views", "stats"]
    # Unresolved, unsnoozed tickets in each queue.
    assert inbox["counts"] == {"mine": 2, "unassigned": 1, "all": 4}
    assert [v["id"] for v in inbox["views"]] == BUILT_IN_VIEW_IDS
    assert list(inbox["views"][0]) == ["id", "name", "count", "filters"]
    assert inbox["views"][0] == {
        "id": "urgent",
        "name": "Urgent",
        "count": 1,
        "filters": {"priority": "urgent", "open": 1},
    }
    assert list(inbox["stats"]) == ["open", "urgent", "sla_at_risk", "resolved_today"]
    # The "all" queue: three tickets with status open, one urgent, one resolved today.
    assert inbox["stats"] == {"open": 3, "urgent": 1, "sla_at_risk": 0, "resolved_today": 1}
    assert result["props"]["queue"] == {"key": "all", "title": "All tickets"}

    views = {v["id"]: v for v in inbox["views"]}
    assert views["waiting_on_customer"]["count"] == 1
    assert views["waiting_on_customer"]["filters"] == {"assigned_to": agent.pk, "status": "waiting_on_customer"}
    assert views["waiting_on_me"]["filters"] == {"assigned_to": agent.pk, "status": "waiting_on_agent"}
    assert views["sla_at_risk"]["filters"] == {"sla_at_risk": 1}
    assert views["recently_updated"]["filters"] == {"open": 1, "updated_within_hours": 24, "sort_by": "updated_at"}
    assert views["recently_updated"]["count"] == 4


@pytest.mark.parametrize(
    "query,key,title,stats",
    [
        ({"assigned_to": "{me}"}, "mine", "My inbox", [1, 1, 0, 1]),
        ({"assigned": "me"}, "mine", "My inbox", [1, 1, 0, 1]),
        ({"assigned_to": "{me}", "priority": "urgent"}, "mine", "My inbox", [1, 1, 0, 1]),
        ({"unassigned": "1"}, "unassigned", "Unassigned", [2, 1, 0, 1]),
        ({}, "all", "All tickets", [3, 2, 0, 2]),
        ({"priority": "urgent", "open": "1"}, "view:urgent", "Urgent", [2, 2, 0, 0]),
        ({"view": "urgent"}, "view:urgent", "Urgent", [2, 2, 0, 0]),
    ],
    ids=["mine", "mine by alias", "mine with a stat tile on", "unassigned", "all", "view by filters", "view by id"],
)
def test_names_and_scopes_the_queue_from_the_list_query(client, agent_user, query, key, title, stats):
    agent = agent_user
    inbox_ticket(assigned_to=agent, priority="urgent")
    inbox_ticket(assigned_to=agent, status="resolved", resolved_at=timezone.now())
    inbox_ticket()
    inbox_ticket(status="resolved", resolved_at=timezone.now())
    inbox_ticket(priority="urgent")

    params = {k: (str(agent.pk) if v == "{me}" else v) for k, v in query.items()}
    props = page(client, agent, params)["props"]

    assert props["queue"] == {"key": key, "title": title}
    assert props["inbox"]["stats"] == dict(zip(["open", "urgent", "sla_at_risk", "resolved_today"], stats))


def test_lists_own_and_shared_saved_views_but_not_other_agents_private_views(client, agent_user, other_agent):
    mine = SavedView.objects.create(user=agent_user, name="High priority", filters={"priority": "high"}, position=1)
    shared = SavedView.objects.create(
        user=other_agent, name="Waiting", filters={"status": "waiting_on_agent"}, is_shared=True, position=2
    )
    SavedView.objects.create(user=other_agent, name="Private", filters={"priority": "low"}, position=0)

    inbox_ticket(priority="high")
    inbox_ticket(priority="high")
    inbox_ticket(priority="high", status="closed")
    inbox_ticket(status="waiting_on_agent")

    views = page(client, agent_user)["props"]["inbox"]["views"]
    saved = [v for v in views if v["id"] not in BUILT_IN_VIEW_IDS]

    assert saved == [
        {"id": mine.pk, "name": "High priority", "count": 2, "filters": {"priority": "high"}},
        {"id": shared.pk, "name": "Waiting", "count": 1, "filters": {"status": "waiting_on_agent"}},
    ]


@pytest.mark.parametrize("by", ["id", "filters"])
def test_selects_a_saved_view_as_the_queue_and_filters_the_list_with_it(client, agent_user, by):
    view = SavedView.objects.create(user=agent_user, name="High priority", filters={"priority": "high"}, position=1)
    high = inbox_ticket(priority="high")
    inbox_ticket(priority="low")

    params = {"view": str(view.pk)} if by == "id" else {"priority": "high"}
    props = page(client, agent_user, params)["props"]

    assert props["queue"] == {"key": f"view:{view.pk}", "title": "High priority"}
    assert [row["id"] for row in props["tickets"]["data"]] == [high.pk]


def test_does_not_let_an_agent_select_another_agents_private_view(client, agent_user, other_agent):
    private = SavedView.objects.create(user=other_agent, name="Private", filters={"priority": "high"}, position=1)
    inbox_ticket(priority="high")
    inbox_ticket(priority="low")

    props = page(client, agent_user, {"view": str(private.pk)})["props"]

    assert props["queue"] == {"key": "all", "title": "All tickets"}
    assert props["tickets"]["total"] == 2


def test_gives_every_built_in_view_the_count_its_own_list_shows(client, agent_user):
    agent = agent_user
    inbox_ticket(assigned_to=agent, priority="urgent")
    inbox_ticket(priority="urgent", status="closed")
    inbox_ticket(assigned_to=agent, status="waiting_on_agent")
    inbox_ticket(assigned_to=agent, status="waiting_on_customer")
    inbox_ticket(sla_first_response_breached=True)
    inbox_ticket(resolution_due_at=timezone.now() + timedelta(minutes=30))
    stale = inbox_ticket()
    Ticket.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(days=3))

    views = page(client, agent)["props"]["inbox"]["views"]

    for view in views:
        total = page(client, agent, {k: str(v) for k, v in view["filters"].items()})["props"]["tickets"]["total"]
        assert view["count"] == total, f"view {view['id']} counts {view['count']} but its list shows {total}"

    assert {v["id"]: v["count"] for v in views} == {
        "urgent": 1,
        "sla_at_risk": 2,
        "waiting_on_me": 1,
        "waiting_on_customer": 1,
        "recently_updated": 5,
    }


def test_counts_only_tickets_the_agent_may_see(client, settings, agent_user):
    settings.ESCALATED = {**settings.ESCALATED, "VISIBILITY": "department"}
    support = agent_user.escalated_departments.first()
    billing = DepartmentFactory()

    inbox_ticket(department=support, assigned_to=agent_user, priority="urgent")
    inbox_ticket(department=support)
    inbox_ticket(department=billing)
    inbox_ticket(department=billing, priority="urgent")
    inbox_ticket(department=billing, status="resolved", resolved_at=timezone.now())

    inbox = page(client, agent_user)["props"]["inbox"]

    assert inbox["counts"] == {"mine": 1, "unassigned": 1, "all": 2}
    assert inbox["stats"] == {"open": 2, "urgent": 1, "sla_at_risk": 0, "resolved_today": 0}
    assert next(v for v in inbox["views"] if v["id"] == "urgent")["count"] == 1


def test_filters_the_list_to_tickets_whose_sla_is_breached_or_due_within_the_hour(client, agent_user):
    now = timezone.now()
    breached = inbox_ticket(sla_resolution_breached=True)
    response_due = inbox_ticket(first_response_due_at=now + timedelta(minutes=20))
    resolution_due = inbox_ticket(resolution_due_at=now + timedelta(minutes=50))
    inbox_ticket(first_response_due_at=now + timedelta(minutes=20), first_response_at=now - timedelta(minutes=1))
    inbox_ticket(resolution_due_at=now + timedelta(hours=3))
    inbox_ticket(sla_resolution_breached=True, status="resolved", resolved_at=now)
    inbox_ticket()

    props = page(client, agent_user, {"sla_at_risk": "1"})["props"]

    assert sorted(row["id"] for row in props["tickets"]["data"]) == sorted(
        [breached.pk, response_due.pk, resolution_due.pk]
    )
    assert props["inbox"]["stats"]["sla_at_risk"] == 3


def test_filters_the_list_to_tickets_resolved_today(client, agent_user):
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    today = inbox_ticket(status="resolved", resolved_at=start + timedelta(minutes=1))
    inbox_ticket(status="resolved", resolved_at=start - timedelta(days=1))
    inbox_ticket()

    props = page(client, agent_user, {"status": "resolved", "resolved_today": "1"})["props"]

    assert [row["id"] for row in props["tickets"]["data"]] == [today.pk]


def test_filters_the_list_to_tickets_updated_within_the_given_hours(client, agent_user):
    fresh = inbox_ticket()
    stale = inbox_ticket()
    Ticket.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(days=2))

    props = page(client, agent_user, {"updated_within_hours": "24"})["props"]

    assert [row["id"] for row in props["tickets"]["data"]] == [fresh.pk]


def test_filters_the_list_to_unresolved_tickets_with_open(client, agent_user):
    still_open = inbox_ticket()
    inbox_ticket(status="resolved", resolved_at=timezone.now())
    inbox_ticket(status="closed")

    props = page(client, agent_user, {"open": "1"})["props"]

    assert [row["id"] for row in props["tickets"]["data"]] == [still_open.pk]


def test_filters_the_list_to_the_agent_with_assigned_to_me(client, agent_user, other_agent):
    mine = inbox_ticket(assigned_to=agent_user)
    inbox_ticket(assigned_to=other_agent)
    inbox_ticket()

    props = page(client, agent_user, {"assigned_to": "me"})["props"]

    assert [row["id"] for row in props["tickets"]["data"]] == [mine.pk]


@pytest.mark.parametrize(
    "query",
    [
        {"sla_at_risk": "soon"},
        {"resolved_today": "maybe"},
        {"open": "perhaps"},
        {"updated_within_hours": "0"},
        {"updated_within_hours": "a day"},
        {"updated_within_hours": "9000"},
    ],
)
def test_rejects_malformed_values_for_the_new_filters(client, agent_user, query):
    client.force_login(agent_user)
    response = client.get(reverse("escalated:agent_ticket_list"), query, HTTP_X_INERTIA="true")

    assert response.status_code == 422
    assert list(response.json()["errors"]) == list(query)


def test_previews_the_latest_customer_visible_message_never_an_internal_note(client, agent_user):
    ticket = inbox_ticket()
    visible = ReplyFactory(ticket=ticket, author=agent_user, body="Customer-visible answer")
    note = ReplyFactory(ticket=ticket, author=agent_user, body="Secret internal note", is_internal_note=True)
    type(visible).objects.filter(pk=visible.pk).update(created_at=timezone.now() - timedelta(minutes=5))
    type(note).objects.filter(pk=note.pk).update(created_at=timezone.now())

    row = page(client, agent_user)["props"]["tickets"]["data"][0]

    assert row["latest_reply"]["body"] == "Customer-visible answer"
    assert row["last_reply_author"] is not None
    # Escalated tracks no per-agent read state or customer presence, so it sends neither.
    assert "is_unread" not in row
    assert "requester_online" not in row


def test_sends_inbox_and_the_queue_the_agent_last_opened_on_the_ticket_page(client, agent_user):
    ticket = inbox_ticket(assigned_to=agent_user)
    inbox_ticket()

    result = page(client, agent_user, path=show_path(ticket))
    assert result["component"] == "Escalated/Agent/TicketShow"
    assert result["props"]["queue"] == {"key": "all", "title": "All tickets"}
    assert result["props"]["inbox"]["counts"] == {"mine": 1, "unassigned": 1, "all": 2}
    assert list(result["props"]["inbox"]) == ["counts", "views", "stats"]

    page(client, agent_user, {"assigned_to": str(agent_user.pk)})

    props = page(client, agent_user, path=show_path(ticket))["props"]
    assert props["queue"] == {"key": "mine", "title": "My inbox"}
    assert props["inbox"]["stats"] == {"open": 1, "urgent": 0, "sla_at_risk": 0, "resolved_today": 0}


def test_caches_the_inbox_per_agent_for_the_configured_seconds(client, settings, agent_user, other_agent):
    settings.ESCALATED = {**settings.ESCALATED, "AGENT_INBOX_CACHE_SECONDS": 30}

    inbox_ticket(assigned_to=agent_user)
    assert page(client, agent_user)["props"]["inbox"]["counts"]["mine"] == 1

    inbox_ticket(assigned_to=agent_user)
    inbox_ticket(assigned_to=other_agent)

    assert page(client, agent_user)["props"]["inbox"]["counts"]["mine"] == 1
    assert page(client, other_agent)["props"]["inbox"]["counts"]["mine"] == 1

    later = time.time() + 31
    with patch("django.core.cache.backends.locmem.time.time", return_value=later):
        assert page(client, agent_user)["props"]["inbox"]["counts"]["mine"] == 2


def test_sends_no_inbox_in_cloud_mode(client, settings, agent_user):
    ticket = inbox_ticket()
    settings.ESCALATED = {**settings.ESCALATED, "MODE": "cloud"}

    props = page(client, agent_user, path=show_path(ticket))["props"]

    assert "inbox" not in props
    assert props["queue"] == {"key": "all", "title": "All tickets"}


@pytest.mark.parametrize("component", ["Escalated/Agent/TicketIndex", "Escalated/Agent/TicketShow"])
def test_sends_the_agent_pages_every_prop_they_declare(client, agent_user, component):
    ticket = inbox_ticket()
    path = None if component.endswith("Index") else show_path(ticket)

    result = page(client, agent_user, path=path)

    with open(MANIFEST, encoding="utf-8") as handle:
        declared = json.load(handle)["props"][component]["props"]
    assert result["component"] == component
    assert [prop for prop in declared if prop not in result["props"]] == []
    assert {"inbox", "queue"} <= set(declared)
