"""
The agent panel's data (ADR 2026-11-05-agent-panel-data): the agent's own
status, knowledge-base search, per-agent unread markers, customer presence
and the notifications feed, through the real URLs.
"""

import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from escalated.models import AgentNotification, AgentProfile, ChatSession, CustomerPresence, Ticket, TicketRead
from escalated.services import agent_panel
from escalated.signals import chat_transferred, sla_breached, sla_warning
from escalated.support.import_context import ImportContext
from tests.factories import (
    AgentProfileFactory,
    ArticleCategoryFactory,
    ArticleFactory,
    ContactFactory,
    DepartmentFactory,
    ReplyFactory,
    TicketFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

JSON = {"HTTP_ACCEPT": "application/json"}


@pytest.fixture(autouse=True)
def _no_inbox_cache(settings):
    settings.ESCALATED = {**settings.ESCALATED, "AGENT_INBOX_CACHE_SECONDS": 0}


@pytest.fixture
def shared_props(settings):
    """The host installs Escalated's middleware that shares the `escalated` prop."""
    settings.MIDDLEWARE = [*settings.MIDDLEWARE, "escalated.middleware.EscalatedInertiaShareMiddleware"]


@pytest.fixture
def agent(agent_user):
    return agent_user


@pytest.fixture
def other(agent_user):
    other = UserFactory(username="otheragent")
    agent_user.escalated_departments.first().agents.add(other)
    return other


@pytest.fixture
def customer(db):
    return UserFactory(username="customer")


def page(client, user, path):
    client.force_login(user)
    response = client.get(path, HTTP_X_INERTIA="true")
    assert response.status_code == 200, response.content[:500]
    return response.json()


def rows(client, user):
    data = page(client, user, reverse("escalated:agent_ticket_list"))["props"]["tickets"]["data"]
    return {row["reference"]: row for row in data}


def open_ticket(client, user, ticket):
    return page(client, user, reverse("escalated:agent_ticket_show", args=[ticket.pk]))


def post_json(client, url, body=None, method="post"):
    return getattr(client, method)(url, data=json.dumps(body or {}), content_type="application/json", **JSON)


# ---- 3. The agent's own status ----------------------------------------------


@pytest.mark.parametrize("method", ["put", "post"])
def test_an_agent_sets_their_own_status(client, agent, method):
    client.force_login(agent)
    response = post_json(client, reverse("escalated:agent_status"), {"status": "away"}, method)
    assert response.status_code == 200
    assert response.json() == {"agent_status": "away"}
    assert AgentProfile.objects.get(user=agent).chat_status == "away"


def test_a_light_agent_sets_their_status(client, agent):
    AgentProfileFactory(user=agent, agent_type="light")
    client.force_login(agent)
    post_json(client, reverse("escalated:agent_status"), {"status": "online"})
    assert AgentProfile.objects.get(user=agent).is_chat_online()


def test_a_status_outside_the_allowed_values_is_rejected(client, agent):
    client.force_login(agent)
    response = post_json(client, reverse("escalated:agent_status"), {"status": "busy"})
    assert response.status_code == 422
    assert not AgentProfile.objects.filter(user=agent).exists()


def test_status_is_refused_to_a_non_agent(client, customer):
    client.force_login(customer)
    assert post_json(client, reverse("escalated:agent_status"), {"status": "online"}).status_code == 403


def test_an_inertia_visit_goes_back(client, agent):
    client.force_login(agent)
    response = client.post(
        reverse("escalated:agent_status"),
        data=json.dumps({"status": "away"}),
        content_type="application/json",
        HTTP_X_INERTIA="true",
        HTTP_REFERER="/support/agent/tickets/",
    )
    assert response.status_code == 302
    assert response["Location"] == "/support/agent/tickets/"


def test_the_admin_chat_status_route_stays_an_alias(client, agent):
    client.force_login(agent)
    response = post_json(client, reverse("escalated:agent_chat_status"), {"status": "online"})
    assert response.json() == {"status": "online", "agent_status": "online"}
    assert agent_panel.agent_status(agent) == "online"


def test_agents_share_their_status_and_customers_do_not(client, agent, customer, shared_props):
    shared = page(client, agent, reverse("escalated:agent_ticket_list"))["props"]["escalated"]
    assert shared["agent_status"] == "offline"
    assert shared["agent_statuses"] == ["online", "away", "offline"]

    shared = page(client, customer, reverse("escalated:customer_ticket_list"))["props"]["escalated"]
    assert "agent_status" not in shared
    assert "agent_statuses" not in shared
    assert "notifications" not in shared


# ---- 5. Knowledge-base search ------------------------------------------------


def article(**attributes):
    return ArticleFactory(**{"status": "published", "category": None, "body": "<p>Body</p>", **attributes})


def kb_search(client, agent, query):
    client.force_login(agent)
    return client.get(reverse("escalated:agent_kb_search") + "?" + query, **JSON)


def test_kb_search_returns_published_articles_with_the_contract_fields(client, agent):
    category = ArticleCategoryFactory(name="Billing")
    found = article(
        title="Resetting your password",
        slug="resetting-your-password",
        category=category,
        body="<p>Open <strong>Settings</strong> and choose Reset.</p>",
    )
    response = kb_search(client, agent, "q=password")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {
                "id": found.pk,
                "title": "Resetting your password",
                "excerpt": "Open Settings and choose Reset.",
                "url": "http://testserver/support/kb/resetting-your-password/",
                "category": {"id": category.pk, "name": "Billing"},
                "updated_at": found.updated_at.isoformat(),
            }
        ]
    }


def test_kb_search_never_returns_drafts(client, agent):
    article(title="Draft about refunds", status="draft")
    article(title="Refunds explained")
    assert [row["title"] for row in kb_search(client, agent, "q=refunds").json()["data"]] == ["Refunds explained"]


def test_kb_search_ranks_title_matches_first_then_the_most_recently_updated(client, agent):
    from escalated.models import Article

    body_only = article(title="Getting started", body="How invoices work")
    older = article(title="Invoices (old)")
    newer = article(title="Invoices (new)")
    now = timezone.now()
    Article.objects.filter(pk=body_only.pk).update(updated_at=now - timedelta(hours=1))
    Article.objects.filter(pk=older.pk).update(updated_at=now - timedelta(days=3))
    Article.objects.filter(pk=newer.pk).update(updated_at=now - timedelta(days=2))

    ids = [row["id"] for row in kb_search(client, agent, "q=invoices").json()["data"]]
    assert ids == [newer.pk, older.pk, body_only.pk]


def test_kb_search_ignores_case(client, agent):
    found = article(title="Resetting your Password")
    assert [row["id"] for row in kb_search(client, agent, "q=PASSWORD").json()["data"]] == [found.pk]


@pytest.mark.parametrize("q", ["%25%25", "__", "0%25", "a_b"])
def test_kb_search_takes_like_wildcards_literally(client, agent, q):
    article(title="Plain title", body="Nothing special")
    literal = article(title="Codes: 100%% off, a_b and x__y", body="x")
    assert [row["id"] for row in kb_search(client, agent, f"q={q}").json()["data"]] == [literal.pk]


def test_kb_search_caps_the_number_of_results(client, agent):
    for i in range(25):
        article(title=f"Shipping guide {i}")
    assert len(kb_search(client, agent, "q=shipping").json()["data"]) == 10
    assert len(kb_search(client, agent, "q=shipping&limit=20").json()["data"]) == 20
    assert kb_search(client, agent, "q=shipping&limit=21").status_code == 422


@pytest.mark.parametrize("query", ["q=", "q=a", "q=" + "a" * 201, ""])
def test_kb_search_validates_the_query(client, agent, query):
    assert kb_search(client, agent, query).status_code == 422


def test_kb_search_answers_404_while_the_knowledge_base_is_off(client, agent):
    from escalated.models import EscalatedSetting

    EscalatedSetting.set("knowledge_base_enabled", "0")
    assert kb_search(client, agent, "q=password").status_code == 404


def test_kb_search_is_for_agents_only(client, customer):
    assert kb_search(client, customer, "q=password").status_code == 403


# ---- 1. Unread tickets --------------------------------------------------------


def test_a_new_ticket_is_unread_until_the_agent_opens_it(client, agent, customer):
    ticket = TicketFactory(requester=customer)
    assert rows(client, agent)[ticket.reference]["is_unread"] is True

    assert open_ticket(client, agent, ticket)["props"]["ticket"]["is_unread"] is False
    assert rows(client, agent)[ticket.reference]["is_unread"] is False


def test_read_markers_are_per_agent(client, agent, other, customer):
    ticket = TicketFactory(requester=customer)
    open_ticket(client, agent, ticket)
    assert rows(client, agent)[ticket.reference]["is_unread"] is False
    assert rows(client, other)[ticket.reference]["is_unread"] is True


@pytest.mark.parametrize("who", ["requester", "guest"])
def test_a_customer_reply_makes_a_read_ticket_unread_again(client, agent, customer, who):
    ticket = TicketFactory(requester=customer)
    open_ticket(client, agent, ticket)
    later = timezone.now() + timedelta(minutes=1)
    with patch("django.utils.timezone.now", return_value=later):
        ReplyFactory(ticket=ticket, author=customer if who == "requester" else None)
    assert rows(client, agent)[ticket.reference]["is_unread"] is True


def test_agent_replies_notes_and_system_replies_do_not_make_a_ticket_unread(client, agent, other, customer):
    ticket = TicketFactory(requester=customer)
    open_ticket(client, agent, ticket)
    later = timezone.now() + timedelta(minutes=1)
    with patch("django.utils.timezone.now", return_value=later):
        ReplyFactory(ticket=ticket, author=agent)
        ReplyFactory(ticket=ticket, author=other)
        ReplyFactory(ticket=ticket, author=customer, is_internal_note=True)
        ReplyFactory(ticket=ticket, author=None, metadata={"workflow_id": 1})
        ReplyFactory(ticket=ticket, author=None, type="system")
    assert rows(client, agent)[ticket.reference]["is_unread"] is False


def test_imported_tickets_start_read(client, agent, customer):
    ticket = ImportContext.suppress(lambda: TicketFactory(requester=customer))
    assert rows(client, agent)[ticket.reference]["is_unread"] is False


def test_tickets_are_marked_read_and_unread_through_the_agent_routes(client, agent, customer):
    ticket = TicketFactory(requester=customer)
    client.force_login(agent)

    response = post_json(client, reverse("escalated:agent_ticket_read", args=[ticket.pk]))
    assert response.json() == {"is_unread": False}
    assert rows(client, agent)[ticket.reference]["is_unread"] is False

    response = post_json(client, reverse("escalated:agent_ticket_unread", args=[ticket.pk]))
    assert response.json() == {"is_unread": True}
    assert rows(client, agent)[ticket.reference]["is_unread"] is True


def test_tickets_are_marked_read_and_unread_in_bulk(client, agent, customer):
    first = TicketFactory(requester=customer)
    second = TicketFactory(requester=customer)
    client.force_login(agent)
    post_json(
        client, reverse("escalated:agent_ticket_bulk"), {"ticket_ids": [first.pk, second.pk], "action": "mark_read"}
    )
    flags = rows(client, agent)
    assert (flags[first.reference]["is_unread"], flags[second.reference]["is_unread"]) == (False, False)

    post_json(client, reverse("escalated:agent_ticket_bulk"), {"ticket_ids": [first.pk], "action": "mark_unread"})
    flags = rows(client, agent)
    assert (flags[first.reference]["is_unread"], flags[second.reference]["is_unread"]) == (True, False)


def test_inbox_unread_counts_unread_open_tickets_per_queue(client, agent, customer):
    mine = TicketFactory(requester=customer, assigned_to=agent)
    TicketFactory(requester=customer, assigned_to=agent)
    unassigned = TicketFactory(requester=customer)
    TicketFactory(requester=customer, status="resolved", resolved_at=timezone.now())
    open_ticket(client, agent, mine)
    open_ticket(client, agent, unassigned)

    inbox = page(client, agent, reverse("escalated:agent_ticket_list"))["props"]["inbox"]
    assert inbox["unread"] == {"mine": 1, "unassigned": 0, "all": 1}


def test_only_tickets_the_agent_may_see_are_counted_and_marked(client, agent, customer, settings):
    settings.ESCALATED = {**settings.ESCALATED, "VISIBILITY": "department"}
    support = agent.escalated_departments.first()
    sales = DepartmentFactory()
    visible = TicketFactory(requester=customer, department=support)
    hidden = TicketFactory(requester=customer, department=sales)

    assert page(client, agent, reverse("escalated:agent_ticket_list"))["props"]["inbox"]["unread"]["all"] == 1

    assert post_json(client, reverse("escalated:agent_ticket_read", args=[hidden.pk])).status_code == 404
    post_json(
        client, reverse("escalated:agent_ticket_bulk"), {"ticket_ids": [hidden.pk, visible.pk], "action": "mark_read"}
    )
    assert list(TicketRead.objects.values_list("ticket_id", flat=True)) == [visible.pk]


def test_read_markers_go_with_the_ticket(client, agent, customer):
    ticket = TicketFactory(requester=customer)
    open_ticket(client, agent, ticket)
    Ticket.unrestricted.filter(pk=ticket.pk).delete()
    assert not TicketRead.objects.filter(ticket_id=ticket.pk).exists()


# ---- 2. Customer presence ------------------------------------------------------


def visit_portal(client, customer):
    client.force_login(customer)
    assert client.get(reverse("escalated:customer_ticket_list"), HTTP_X_INERTIA="true").status_code == 200


def test_a_customer_is_online_while_the_portal_saw_them_within_the_window(client, agent, customer):
    ticket = TicketFactory(requester=customer)
    row = rows(client, agent)[ticket.reference]
    assert (row["requester_online"], row["requester_last_seen_at"]) == (False, None)

    visit_portal(client, customer)
    row = rows(client, agent)[ticket.reference]
    assert row["requester_online"] is True
    assert row["requester_last_seen_at"] == CustomerPresence.objects.get().last_seen_at.isoformat()

    CustomerPresence.objects.update(last_seen_at=timezone.now() - timedelta(seconds=121))
    assert rows(client, agent)[ticket.reference]["requester_online"] is False


def test_the_online_window_is_configurable(client, agent, customer, settings):
    settings.ESCALATED = {**settings.ESCALATED, "PRESENCE_ONLINE_WINDOW_SECONDS": 600}
    ticket = TicketFactory(requester=customer)
    visit_portal(client, customer)
    CustomerPresence.objects.update(last_seen_at=timezone.now() - timedelta(minutes=9))
    assert rows(client, agent)[ticket.reference]["requester_online"] is True


def test_presence_is_written_at_most_once_every_30_seconds(client, customer):
    visit_portal(client, customer)
    first = CustomerPresence.objects.get().last_seen_at
    visit_portal(client, customer)
    assert CustomerPresence.objects.get().last_seen_at == first

    CustomerPresence.objects.update(last_seen_at=first - timedelta(seconds=31))
    visit_portal(client, customer)
    assert CustomerPresence.objects.get().last_seen_at > first - timedelta(seconds=5)
    assert CustomerPresence.objects.count() == 1


def test_a_widget_chat_guest_is_recorded_through_the_ticket_contact(client, agent, settings):
    from escalated import chat_tokens
    from escalated.models import EscalatedSetting

    EscalatedSetting.set("widget_enabled", "1")
    EscalatedSetting.set("chat_enabled", "1")
    contact = ContactFactory()
    ticket = TicketFactory(contact=contact, guest_email=contact.email, channel="chat")
    token, digest, expires = chat_tokens.issue()
    ChatSession.objects.create(
        ticket=ticket, status=ChatSession.Status.ACTIVE, customer_session_id=digest, customer_token_expires_at=expires
    )

    response = client.get(f"/support/widget/chat/{token}/messages", **JSON)
    assert response.status_code == 200
    assert b"requester_online" not in response.content

    client.logout()
    assert rows(client, agent)[ticket.reference]["requester_online"] is True


def test_presence_is_sent_on_the_agent_ticket_page(client, agent, customer):
    ticket = TicketFactory(requester=customer)
    visit_portal(client, customer)
    assert open_ticket(client, agent, ticket)["props"]["ticket"]["requester_online"] is True


def test_staff_browsing_the_customer_portal_are_not_recorded(client, agent):
    client.force_login(agent)
    client.get(reverse("escalated:customer_ticket_list"), HTTP_X_INERTIA="true")
    assert CustomerPresence.objects.count() == 0


def test_customers_never_see_presence(client, customer):
    ticket = TicketFactory(requester=customer)
    visit_portal(client, customer)
    response = client.get(reverse("escalated:customer_ticket_show", args=[ticket.pk]), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    assert b"requester_online" not in response.content
    assert b"requester_last_seen_at" not in response.content


# ---- 4. Notifications -----------------------------------------------------------


def feed(client, user, query=""):
    client.force_login(user)
    response = client.get(reverse("escalated:agent_notifications") + query, **JSON)
    assert response.status_code == 200, response.content[:300]
    return response.json()


def assign(ticket, agent, actor):
    from escalated.services.ticket_service import TicketService

    TicketService().assign(ticket, actor, agent)


def test_a_ticket_assignment_is_listed_with_the_contract_shape(client, agent, customer, admin_user):
    ticket = TicketFactory(requester=customer, subject="Printer on fire")
    assign(ticket, agent, admin_user)
    row = AgentNotification.objects.get()

    assert feed(client, agent) == {
        "data": [
            {
                "id": row.pk,
                "type": "ticket_assigned",
                "title": f"{ticket.reference} was assigned to you",
                "body": "Printer on fire",
                "ticket": {"id": ticket.pk, "reference": ticket.reference, "subject": "Printer on fire"},
                "url": reverse("escalated:agent_ticket_show", args=[ticket.reference]),
                "created_at": row.created_at.isoformat(),
                "read_at": None,
            }
        ],
        "meta": {"current_page": 1, "last_page": 1, "per_page": 20, "total": 1},
        "unread_count": 1,
    }


def test_assigning_yourself_notifies_nobody_by_email_either(client, agent, customer, settings, mailoutbox):
    settings.ESCALATED = {**settings.ESCALATED, "NOTIFICATION_CHANNELS": ["email"]}
    assign(TicketFactory(requester=customer), agent, agent)
    assert feed(client, agent)["data"] == []
    assert mailoutbox == []


def test_the_assignee_hears_of_customer_replies_but_not_other_agents(client, agent, other, customer):
    ticket = TicketFactory(requester=customer, assigned_to=agent)
    ReplyFactory(ticket=ticket, author=other)
    assert feed(client, agent)["data"] == []

    ReplyFactory(ticket=ticket, author=customer)
    items = feed(client, agent)["data"]
    assert [(i["type"], i["title"]) for i in items] == [("ticket_reply", f"New reply on {ticket.reference}")]


def test_the_assignee_hears_of_sla_warnings_and_breaches(client, agent, customer):
    ticket = TicketFactory(requester=customer, assigned_to=agent)
    sla_warning.send(sender=Ticket, ticket=ticket, warning_type="first_response", remaining=timedelta(minutes=20))
    sla_breached.send(sender=Ticket, ticket=ticket, breach_type="resolution")
    items = feed(client, agent)["data"]
    assert sorted(i["type"] for i in items) == ["sla_breached", "sla_warning"]
    assert next(i for i in items if i["type"] == "sla_warning")["title"] == f"SLA due soon on {ticket.reference}"


def test_the_receiving_agent_hears_of_a_chat_transfer_not_the_sender(client, agent, other, customer):
    ticket = TicketFactory(requester=customer)
    session = ChatSession.objects.create(ticket=ticket, status=ChatSession.Status.ACTIVE)
    chat_transferred.send(sender=ChatSession, session=session, ticket=ticket, from_agent=other, to_agent=agent)
    assert [i["type"] for i in feed(client, agent)["data"]] == ["chat_transferred"]
    assert feed(client, other)["data"] == []


def test_the_feed_pages_newest_first_filters_and_marks_read(client, agent, customer, admin_user):
    start = timezone.now()
    for i in range(3):
        with patch("django.utils.timezone.now", return_value=start + timedelta(minutes=i)):
            assign(TicketFactory(requester=customer, subject=f"Ticket {i + 1}"), agent, admin_user)

    first = feed(client, agent, "?per_page=2")
    assert [i["body"] for i in first["data"]] == ["Ticket 3", "Ticket 2"]
    assert first["meta"] == {"current_page": 1, "last_page": 2, "per_page": 2, "total": 3}

    response = post_json(client, reverse("escalated:agent_notification_read", args=[first["data"][0]["id"]]))
    assert response.json() == {"unread_count": 2}
    assert [i["body"] for i in feed(client, agent, "?unread=1")["data"]] == ["Ticket 2", "Ticket 1"]
    assert client.get(reverse("escalated:agent_notifications") + "?per_page=51", **JSON).status_code == 422

    assert post_json(client, reverse("escalated:agent_notifications_read_all")).json() == {"unread_count": 0}
    assert feed(client, agent)["unread_count"] == 0


def test_another_agents_notification_cannot_be_marked_read(client, agent, other, customer, admin_user):
    assign(TicketFactory(requester=customer), other, admin_user)
    client.force_login(agent)
    row = AgentNotification.objects.get()
    assert post_json(client, reverse("escalated:agent_notification_read", args=[row.pk])).status_code == 404
    row.refresh_from_db()
    assert row.read_at is None


def test_tickets_the_agent_can_no_longer_view_are_redacted(client, agent, customer, admin_user, settings):
    settings.ESCALATED = {**settings.ESCALATED, "VISIBILITY": "department"}
    support = agent.escalated_departments.first()
    billing = DepartmentFactory()
    ticket = TicketFactory(requester=customer, department=support, subject="Secret subject")
    assign(ticket, agent, admin_user)
    Ticket.unrestricted.filter(pk=ticket.pk).update(department=billing)

    item = feed(client, agent)["data"][0]
    assert item["title"] == "A ticket you can no longer view"
    assert (item["body"], item["ticket"], item["url"]) == (None, None, None)
    assert "Secret subject" not in json.dumps(item)


def test_agents_share_the_unread_count(client, agent, customer, admin_user, shared_props):
    assign(TicketFactory(requester=customer), agent, admin_user)
    shared = page(client, agent, reverse("escalated:agent_ticket_list"))["props"]["escalated"]
    assert shared["notifications"] == {"unread_count": 1}


def test_the_feed_is_off_when_switched_off(client, agent, settings, shared_props):
    settings.ESCALATED = {**settings.ESCALATED, "AGENT_NOTIFICATIONS": False}
    client.force_login(agent)
    assert client.get(reverse("escalated:agent_notifications"), **JSON).status_code == 404
    assert post_json(client, reverse("escalated:agent_notifications_read_all")).status_code == 404
    assert "notifications" not in page(client, agent, reverse("escalated:agent_ticket_list"))["props"]["escalated"]


def test_the_feed_is_for_agents_only(client, customer):
    client.force_login(customer)
    assert client.get(reverse("escalated:agent_notifications"), **JSON).status_code == 403


def test_a_new_notification_is_broadcast_on_the_agents_channel(agent, customer, admin_user, settings):
    settings.ESCALATED_BROADCASTING_ENABLED = True
    with patch("escalated.broadcasting.broadcast_event") as broadcast:
        ticket = TicketFactory(requester=customer)
        assign(ticket, agent, admin_user)
    calls = [c for c in broadcast.call_args_list if c.args[0] == "notification.created"]
    assert len(calls) == 1
    event, channel, payload = calls[0].args
    assert channel == f"escalated.agents.{agent.pk}"
    assert payload["type"] == "ticket_assigned"
    assert payload["ticket"]["reference"] == ticket.reference
