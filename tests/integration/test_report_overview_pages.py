"""Admin/Reports, Reports/Dashboard and Reports/AgentDetail read what they declare.

``Admin/Reports`` (the classic overview) and ``Reports/Dashboard`` used to be
sent ``stats``/``by_department``/``ticket_volume`` and ``{status, count}`` rows,
none of which the shared screens read, so both rendered zeroes and empty charts.
They now carry escalated-laravel's ``Admin\\ReportController`` props.

``Reports/AgentDetail`` carries the props the shared page declares (Laravel's
controller is being brought to the same shape): the period's KPIs against the
period of the same length before it, response percentiles, and the
productivity, workload and CSAT charts as ``{label, value}`` rows.
"""

import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from escalated.models import Reply, SatisfactionRating, Ticket
from tests.factories import DepartmentFactory, SlaPolicyFactory, TicketFactory, UserFactory

MANIFEST_SHARED = {"errors", "auth", "current_user", "flash", "escalated", "plugin_ui", "ziggy"}


def get_page(client, url):
    response = client.get(url, HTTP_X_INERTIA="true")
    assert response.status_code == 200, f"{url} answered {response.status_code}"
    return json.loads(response.content)


def declared(page):
    from tests.test_report_screen_props import manifest

    return sorted(manifest()["props"][page]["props"])


def own_props(body):
    return sorted(set(body["props"]) - MANIFEST_SHARED)


@pytest.fixture
def seeded(db):
    agent = UserFactory(username="ada", first_name="Ada", last_name="Agent", email="ada@example.com")
    DepartmentFactory().agents.add(agent)
    policy = SlaPolicyFactory(is_active=True)
    now = timezone.now()
    # 10:00 local two days ago, so the reply and the resolution (up to four
    # hours later) land on the same day whatever time the suite runs.
    created = timezone.localtime(now - timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)

    answered = TicketFactory(subject="Answered", priority="high")
    waiting = TicketFactory(subject="Waiting", priority="low")
    previous = TicketFactory(subject="Previous")
    other = TicketFactory(subject="Someone else's")
    old = TicketFactory(subject="Old")

    Ticket.objects.filter(pk=answered.pk).update(
        assigned_to=agent,
        created_at=created,
        first_response_at=created + timedelta(hours=2),
        resolved_at=created + timedelta(hours=4),
        status="resolved",
        sla_policy=policy,
        sla_first_response_breached=False,
        sla_resolution_breached=False,
    )
    Ticket.objects.filter(pk=waiting.pk).update(
        assigned_to=agent,
        created_at=created,
        first_response_at=created + timedelta(hours=4),
        status="open",
        sla_policy=policy,
        sla_first_response_breached=True,
    )
    Ticket.objects.filter(pk=previous.pk).update(assigned_to=agent, created_at=now - timedelta(days=40))
    Ticket.objects.filter(pk=other.pk).update(created_at=created, status="open")
    Ticket.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=60), sla_first_response_breached=True)

    SatisfactionRating.objects.create(ticket=answered, rating=4)
    reply = Reply.objects.create(ticket=answered, author=agent, body="On it", is_internal_note=False)
    Reply.objects.filter(pk=reply.pk).update(created_at=created + timedelta(hours=2))
    note = Reply.objects.create(ticket=answered, author=agent, body="internal", is_internal_note=True)
    Reply.objects.filter(pk=note.pk).update(created_at=created + timedelta(hours=2))

    return {"agent": agent, "created": created}


@pytest.mark.django_db
def test_overview_sends_the_props_the_screen_reads(client, admin_user, seeded):
    client.force_login(admin_user)

    body = get_page(client, reverse("escalated:admin_reports") + "?days=30")
    props = body["props"]

    assert body["component"] == "Escalated/Admin/Reports"
    assert own_props(body) == declared("Escalated/Admin/Reports")
    assert props["period_days"] == 30
    assert props["total_tickets"] == 3
    assert props["resolved_tickets"] == 1
    assert props["avg_first_response_hours"] == 3.0
    assert props["sla_breach_count"] == 1
    assert props["by_status"] == {"open": 2, "resolved": 1}
    assert props["by_priority"]["high"] == 1
    assert props["by_priority"]["low"] == 1
    assert props["csat"] == {"average": 4.0, "total": 1, "breakdown": {"4": 1}}


@pytest.mark.django_db
def test_overview_with_no_data(client, admin_user, db):
    client.force_login(admin_user)

    props = get_page(client, reverse("escalated:admin_reports"))["props"]

    assert props["period_days"] == 30
    assert props["total_tickets"] == 0
    assert props["avg_first_response_hours"] == 0.0
    assert props["by_status"] == {}
    assert props["csat"] == {"average": 0.0, "total": 0, "breakdown": {}}


@pytest.mark.django_db
def test_dashboard_sends_the_props_the_screen_reads(client, admin_user, seeded):
    client.force_login(admin_user)

    body = get_page(client, reverse("escalated:admin_reports_dashboard") + "?days=30")
    props = body["props"]
    day = timezone.localtime(seeded["created"]).date().isoformat()

    assert body["component"] == "Escalated/Admin/Reports/Dashboard"
    assert own_props(body) == declared("Escalated/Admin/Reports/Dashboard")
    assert props["period_days"] == 30
    assert props["volume"] == [{"label": day, "value": 3}]
    # Every ticket, as Laravel's getTicketsByStatus / getTicketsByPriority.
    assert {"label": "resolved", "value": 1} in props["by_status"]
    assert all(set(row) == {"label", "value"} for row in props["by_status"] + props["by_priority"])
    assert sum(row["value"] for row in props["by_status"]) == 5
    assert props["avg_response_hours"] == 3.0
    assert props["avg_resolution_hours"] == 4.0
    assert props["sla_compliance"] == 50.0
    assert props["csat_average"] == 4.0
    assert props["agent_performance"] == [
        {
            "agent_id": seeded["agent"].pk,
            "agent_name": "Ada Agent",
            "total_tickets": 2,
            "resolved_tickets": 1,
            "avg_response_hours": 3.0,
            "avg_resolution_hours": 4.0,
        }
    ]


@pytest.mark.django_db
def test_dashboard_with_no_data(client, admin_user, db):
    client.force_login(admin_user)

    props = get_page(client, reverse("escalated:admin_reports_dashboard"))["props"]

    assert props["volume"] == []
    assert props["sla_compliance"] == 100.0
    assert props["csat_average"] == 0.0
    assert props["avg_response_hours"] == 0.0
    assert props["agent_performance"] == []


@pytest.mark.django_db
def test_agent_detail_sends_the_props_the_screen_reads(client, admin_user, seeded):
    client.force_login(admin_user)
    agent = seeded["agent"]

    url = reverse("escalated:admin_reports_agent_detail", kwargs={"agent_id": agent.pk}) + "?days=30"
    body = get_page(client, url)
    props = body["props"]
    day = timezone.localtime(seeded["created"]).date().isoformat()

    assert body["component"] == "Escalated/Admin/Reports/AgentDetail"
    assert own_props(body) == declared("Escalated/Admin/Reports/AgentDetail")
    assert props["period_days"] == 30
    assert props["agent"] == {"id": agent.pk, "name": "Ada Agent", "email": "ada@example.com"}
    assert props["total_tickets"] == 2
    assert props["resolved_tickets"] == 1
    assert props["avg_frt"] == 3.0
    assert props["avg_resolution"] == 4.0
    assert props["csat_score"] == 4.0
    assert list(props["response_percentiles"]) == ["p50", "p75", "p90", "p95", "p99"]
    assert props["response_percentiles"]["p50"] == 3.0
    assert props["response_percentiles"]["p99"] == 4.0
    # One public reply and one resolution that day; the internal note is not counted.
    assert props["productivity"] == [{"label": day, "value": 2, "values": [1, 1]}]
    assert props["workload"] == [{"label": day, "value": 2}]
    assert props["csat_breakdown"] == [{"label": "4 stars", "value": 1}]
    assert props["prev_total_tickets"] == 1
    assert props["prev_resolved_tickets"] == 0
    assert props["prev_avg_frt"] == 0.0
    assert props["prev_avg_resolution"] == 0.0
    assert props["prev_csat_score"] is None


@pytest.mark.django_db
def test_agent_detail_for_an_agent_with_no_tickets(client, admin_user, agent_user):
    client.force_login(admin_user)

    props = get_page(client, reverse("escalated:admin_reports_agent_detail", kwargs={"agent_id": agent_user.pk}))[
        "props"
    ]

    assert props["period_days"] == 30
    assert props["agent"]["id"] == agent_user.pk
    assert props["total_tickets"] == 0
    assert props["csat_score"] is None
    assert props["response_percentiles"] == {"p50": 0.0, "p75": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}
    assert props["productivity"] == []
    assert props["workload"] == []
    assert props["csat_breakdown"] == []
    for old in ("agent_id", "metrics", "percentiles"):
        assert old not in props


@pytest.mark.django_db
@pytest.mark.parametrize("route", ["escalated:admin_reports", "escalated:admin_reports_dashboard"])
def test_overview_screens_are_admin_only(client, agent_user, route):
    client.force_login(agent_user)

    assert client.get(reverse(route), HTTP_X_INERTIA="true").status_code in (302, 403)


@pytest.mark.django_db
def test_agent_detail_is_admin_only(client, agent_user):
    client.force_login(agent_user)

    url = reverse("escalated:admin_reports_agent_detail", kwargs={"agent_id": agent_user.pk})

    assert client.get(url, HTTP_X_INERTIA="true").status_code in (302, 403)
