"""Reports/AgentMetrics, SlaReport and CsatReport against escalated-laravel.

Laravel's Admin\\ReportController renders them at /admin/reports/agents, /sla
and /csat with the props asserted here. They read the last ``days`` days of
tickets (30 by default); ratings are counted by when they were given.
"""

import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from escalated.models import SatisfactionRating, Ticket
from tests.factories import DepartmentFactory, SlaPolicyFactory, TicketFactory, UserFactory


def get_page(client, route, **query):
    response = client.get(reverse(route), query, HTTP_X_INERTIA="true")
    assert response.status_code == 200, f"{route} answered {response.status_code}"
    return json.loads(response.content)


@pytest.fixture
def seeded(db):
    agent = UserFactory(username="agent", first_name="Ada", last_name="Agent")
    DepartmentFactory().agents.add(agent)
    policy = SlaPolicyFactory(name="Standard", is_active=True)
    SlaPolicyFactory(name="Retired", is_active=False)
    now = timezone.now()

    met = TicketFactory(subject="Met", priority="high")
    breached = TicketFactory(subject="Breached", priority="low")
    old = TicketFactory(subject="Old")
    Ticket.objects.filter(pk=met.pk).update(
        sla_policy=policy,
        assigned_to=agent,
        sla_first_response_breached=False,
        sla_resolution_breached=False,
        first_response_at=met.created_at + timedelta(hours=2),
        resolved_at=met.created_at + timedelta(hours=6),
        status="resolved",
    )
    Ticket.objects.filter(pk=breached.pk).update(
        sla_policy=policy,
        assigned_to=agent,
        sla_first_response_breached=True,
        sla_resolution_breached=False,
        first_response_at=None,
        resolved_at=None,
    )
    Ticket.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=60), sla_first_response_breached=True)
    SatisfactionRating.objects.create(ticket=met, rating=4)
    return {"agent": agent, "met": met, "breached": breached, "policy": policy}


@pytest.mark.django_db
def test_agent_metrics(client, admin_user, seeded):
    client.force_login(admin_user)

    body = get_page(client, "escalated:admin_reports_agents", days=7)

    assert body["component"] == "Escalated/Admin/Reports/AgentMetrics"
    assert body["props"]["period_days"] == 7
    assert body["props"]["agents"] == [
        {
            "agent_id": seeded["agent"].pk,
            "agent_name": "Ada Agent",
            "total_tickets": 2,
            "resolved_tickets": 1,
            "avg_response_hours": 2.0,
            "avg_resolution_hours": 6.0,
        }
    ]


@pytest.mark.django_db
def test_sla_report(client, admin_user, seeded):
    client.force_login(admin_user)

    body = get_page(client, "escalated:admin_reports_sla")
    props = body["props"]

    assert body["component"] == "Escalated/Admin/Reports/SlaReport"
    assert props["period_days"] == 30
    assert props["compliance_rate"] == 50.0
    # Active policies only, as Laravel's SlaPolicy::active().
    assert props["compliance_by_policy"] == [{"policy_name": "Standard", "total": 2, "met": 1, "breached": 1}]

    assert [row["subject"] for row in props["breaches"]] == ["Breached"]
    row = props["breaches"][0]
    for key in (
        "id",
        "reference",
        "subject",
        "assigned_to",
        "sla_policy_id",
        "sla_first_response_breached",
        "sla_resolution_breached",
        "first_response_at",
        "resolved_at",
        "created_at",
        "assignee",
        "sla_policy",
    ):
        assert key in row, key
    assert row["reference"] == seeded["breached"].reference
    assert row["sla_first_response_breached"] is True
    assert row["sla_policy"]["name"] == "Standard"
    assert row["assignee"]["name"] == "Ada Agent"


@pytest.mark.django_db
def test_sla_compliance_is_full_with_no_sla_tickets(client, admin_user, db):
    client.force_login(admin_user)

    props = get_page(client, "escalated:admin_reports_sla")["props"]

    assert props["compliance_rate"] == 100.0
    assert props["breaches"] == []


@pytest.mark.django_db
def test_csat_report(client, admin_user, seeded):
    client.force_login(admin_user)

    body = get_page(client, "escalated:admin_reports_csat")
    props = body["props"]

    assert body["component"] == "Escalated/Admin/Reports/CsatReport"
    assert props["period_days"] == 30
    assert props["csat_average"] == 4.0
    assert props["total_ratings"] == 1
    # One rating over the two tickets raised in the window.
    assert props["response_rate"] == 50.0
    assert props["by_agent"] == [
        {"agent_id": seeded["agent"].pk, "agent_name": "Ada Agent", "avg_rating": 4.0, "total_ratings": 1}
    ]
    rated = timezone.localtime(SatisfactionRating.objects.get().created_at).date().isoformat()
    assert props["over_time"] == [{"label": rated, "value": 4.0}]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "route", ["escalated:admin_reports_agents", "escalated:admin_reports_sla", "escalated:admin_reports_csat"]
)
def test_admin_only(client, agent_user, route):
    client.force_login(agent_user)

    response = client.get(reverse(route), HTTP_X_INERTIA="true")

    assert response.status_code in (302, 403)
