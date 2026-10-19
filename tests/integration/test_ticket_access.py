"""Opt-in ticket access must cover every query entry point."""

import pytest
from django.urls import reverse

from escalated.models import Ticket
from escalated.policies.ticket_policy import TicketPolicy
from tests.factories import DepartmentFactory, TicketFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("field", ["account_type", "account_id"])
def test_account_identity_preserves_trailing_spaces(settings, agent_user, field):
    from types import SimpleNamespace

    from escalated.services.automation_runner import AutomationRunner
    from escalated.ticket_access import ticket_access

    company = DepartmentFactory()
    identity = {"account_type": "escalated.Department", "account_id": str(company.pk)}
    exact = TicketFactory(**identity)
    padded = TicketFactory(**{**identity, field: identity[field] + " "})
    assert list(Ticket.objects.filter(**identity).values_list("pk", flat=True)) == [exact.pk]
    assert list(Ticket.objects.exclude(**identity).values_list("pk", flat=True)) == [padded.pk]
    rule = SimpleNamespace(
        conditions=[{"field": "account", "value": {"type": identity["account_type"], "id": identity["account_id"]}}]
    )
    assert list(AutomationRunner()._find_matching_tickets(rule).values_list("pk", flat=True)) == [exact.pk]
    settings.ESCALATED = {
        **settings.ESCALATED,
        "ACCOUNTS": {"ENABLED": True, "SCOPE_AGENTS": True, "RESOLVER": lambda model: company},
    }
    with ticket_access(agent_user):
        assert list(Ticket.objects.values_list("pk", flat=True)) == [exact.pk]


@pytest.fixture
def access_setup(settings, agent_user):
    settings.ESCALATED = {**settings.ESCALATED, "VISIBILITY": "department"}
    department = agent_user.escalated_departments.first()
    visible = TicketFactory(department=department, subject="Searchable visible")
    hidden = TicketFactory(department=DepartmentFactory(), subject="Searchable hidden", assigned_to=agent_user)
    unassigned = TicketFactory(department=None, subject="Searchable unassigned")
    return agent_user, visible, hidden, unassigned


@pytest.mark.parametrize("action", ["view", "update", "reply", "add_note", "assign", "close"])
def test_policy_denies_other_departments_even_when_assigned(access_setup, action):
    agent, visible, hidden, unassigned = access_setup
    policy = getattr(TicketPolicy, action)
    assert policy(agent, visible)
    assert not policy(agent, hidden)
    assert not policy(agent, unassigned)


@pytest.mark.parametrize("params", [{}, {"search": "Searchable"}, {"assigned": "me"}])
def test_list_and_search_scope_before_pagination(client, access_setup, params):
    agent, visible, hidden, unassigned = access_setup
    client.force_login(agent)
    response = client.get(reverse("escalated:agent_ticket_list"), params, HTTP_X_INERTIA="true")
    assert response.status_code == 200
    tickets = response.json()["props"]["tickets"]
    assert {row["id"] for row in tickets["data"]} == (set() if params.get("assigned") else {visible.pk})


def test_http_detail_cannot_load_hidden_ticket(client, access_setup):
    agent, visible, hidden, unassigned = access_setup
    client.force_login(agent)
    response = client.get(reverse("escalated:agent_ticket_show", args=[hidden.pk]), HTTP_X_INERTIA="true")
    assert response.status_code in (403, 404)


def test_direct_queries_context_is_reset_and_admin_bypasses(access_setup, admin_user):
    from escalated.ticket_access import ticket_access

    agent, visible, hidden, unassigned = access_setup
    with ticket_access(agent):
        assert list(Ticket.objects.values_list("pk", flat=True)) == [visible.pk]
    assert Ticket.objects.count() == 3
    with ticket_access(admin_user):
        assert Ticket.objects.count() == 3


def test_legacy_access_is_unchanged(settings, access_setup):
    from escalated.ticket_access import ticket_access

    agent, visible, hidden, unassigned = access_setup
    settings.ESCALATED = {**settings.ESCALATED, "VISIBILITY": "all"}
    with ticket_access(agent):
        assert Ticket.objects.count() == 3
    assert TicketPolicy.view(agent, hidden)


def test_bulk_action_only_changes_visible_tickets(client, access_setup):
    agent, visible, hidden, unassigned = access_setup
    client.force_login(agent)
    response = client.post(
        reverse("escalated:agent_ticket_bulk"),
        {
            "ticket_ids": [visible.pk, hidden.pk],
            "action": "close",
        },
        content_type="application/json",
    )
    assert response.status_code == 302
    assert Ticket.objects.get(pk=visible.pk).status == "closed"
    assert Ticket.objects.get(pk=hidden.pk).status == "open"


def test_reports_and_child_queries_are_scoped(access_setup):
    from escalated.models import SatisfactionRating
    from escalated.services.reporting_service import ReportingService
    from escalated.ticket_access import ticket_access

    agent, visible, hidden, unassigned = access_setup
    SatisfactionRating.objects.create(ticket=visible, rating=5)
    SatisfactionRating.objects.create(ticket=hidden, rating=1)
    with ticket_access(agent):
        assert sum(row["count"] for row in ReportingService().get_tickets_by_status()) == 1
        assert list(SatisfactionRating.objects.values_list("rating", flat=True)) == [5]


def test_api_token_list_detail_and_mutation(access_setup, rf):
    import json

    from django.urls import resolve

    from escalated.api_middleware import AuthenticateApiToken
    from escalated.models import ApiToken

    agent, visible, hidden, unassigned = access_setup
    token = ApiToken.create_token(agent, "access test")
    for suffix, method, expected in [
        ("", "get", 200),
        (hidden.reference + "/", "get", 404),
        (hidden.reference + "/status/", "patch", 404),
    ]:
        request = getattr(rf, method)(
            "/support/support/api/v1/tickets/" + suffix,
            data=json.dumps({"status": "closed"}) if method != "get" else {},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer " + token["plain_text_token"],
        )
        match = resolve(request.path)
        assert AuthenticateApiToken(lambda request: None).process_view(request, match.func, (), match.kwargs) is None
        response = match.func(request, **match.kwargs)
        assert response.status_code == expected
        if not suffix:
            assert {row["id"] for row in json.loads(response.content)["data"]} == {visible.pk}


def test_account_and_department_intersect_with_type_identity(settings, access_setup):
    from escalated.ticket_access import ticket_access

    agent, visible, hidden, unassigned = access_setup
    company = DepartmentFactory()
    settings.ESCALATED = {
        **settings.ESCALATED,
        "ACCOUNTS": {"ENABLED": True, "SCOPE_AGENTS": True, "RESOLVER": lambda model: company},
    }
    Ticket.objects.filter(pk__in=[visible.pk, hidden.pk]).update(
        account_type="escalated.Department", account_id=str(company.pk)
    )
    wrong_type = TicketFactory(department=visible.department, account_type="other.Company", account_id=str(company.pk))
    with ticket_access(agent):
        assert list(Ticket.objects.values_list("pk", flat=True)) == [visible.pk]
        assert not TicketPolicy.view(agent, wrong_type)
    settings.ESCALATED["ACCOUNTS"]["RESOLVER"] = lambda model: None
    with ticket_access(agent):
        assert not Ticket.objects.exists()


def test_subject_populates_account_without_overwriting(settings):
    settings.ESCALATED = {
        **settings.ESCALATED,
        "ACCOUNTS": {
            "ENABLED": True,
            "RESOLVER": lambda model: model if isinstance(model, type(DepartmentFactory.build())) else None,
        },
    }
    first, second = DepartmentFactory(), DepartmentFactory()
    ticket = TicketFactory()
    stale = Ticket.objects.get(pk=ticket.pk)
    ticket.attach_subject(first)
    stale.attach_subject(second)
    ticket.refresh_from_db()
    assert ticket.account_type == "escalated.Department"
    assert ticket.account_id == str(first.pk)


def test_targeted_sla_precedence_and_department_move_preserves_deadline(settings, user):
    from escalated.services.ticket_service import TicketService
    from tests.factories import SlaPolicyFactory

    settings.ESCALATED = {**settings.ESCALATED, "SLA": {"ENABLED": True, "TARGETED": True}}
    department = DepartmentFactory()
    SlaPolicyFactory(is_default=True)
    SlaPolicyFactory(ticket_type="incident")
    SlaPolicyFactory(department=department)
    both = SlaPolicyFactory(department=department, ticket_type="incident")
    ticket = TicketService().create(
        user,
        {"subject": "Incident", "description": "Details", "department_id": department.pk, "ticket_type": "incident"},
    )
    assert ticket.sla_policy_id == both.pk
    due = ticket.first_response_due_at
    ticket.department = DepartmentFactory()
    ticket.save()
    ticket.refresh_from_db()
    assert ticket.sla_policy_id == both.pk
    assert ticket.first_response_due_at == due


def test_rules_match_complete_account_identity():
    from types import SimpleNamespace

    from escalated.services.automation_runner import AutomationRunner
    from escalated.services.escalation_service import EscalationService
    from escalated.services.workflow_engine import WorkflowEngine
    from tests.factories import EscalationRuleFactory

    visible = TicketFactory(ticket_type="incident", account_type="company", account_id="north")
    hidden = TicketFactory(ticket_type="incident", account_type="partner", account_id="north")
    conditions = [
        {"field": "account", "value": {"type": "company", "id": "north"}},
        {"field": "ticket_type", "value": "incident"},
    ]
    assert list(AutomationRunner()._find_matching_tickets(SimpleNamespace(conditions=conditions))) == [visible]
    assert WorkflowEngine().evaluate_conditions(conditions, visible)
    assert not WorkflowEngine().evaluate_conditions(conditions, hidden)
    rule = EscalationRuleFactory(conditions={"account": {"type": "company", "id": "north"}, "ticket_type": "incident"})
    assert not EscalationService._matches_conditions(hidden, rule)


def test_linked_ticket_summaries_and_chat_sessions_do_not_leak(access_setup):
    from escalated.api_serializers import ApiTicketDetailSerializer
    from escalated.models import ChatSession, TicketLink
    from escalated.ticket_access import can_access_chat, ticket_access

    agent, visible, hidden, unassigned = access_setup
    TicketLink.objects.create(parent_ticket=visible, child_ticket=hidden, link_type="related")
    chat = ChatSession.objects.create(ticket=hidden, customer_session_id="private-guest-session")
    with ticket_access(agent):
        assert not TicketLink.objects.exists()
        assert not ChatSession.objects.exists()
        assert not ApiTicketDetailSerializer.serialize(visible)["related_tickets"]
    assert not can_access_chat(agent, chat.pk)
    assert not can_access_chat(None, chat.pk)
    assert can_access_chat(None, chat.pk, "private-guest-session")


def test_notifications_and_broadcast_polling_recheck_membership(access_setup, settings):
    from unittest.mock import patch

    from escalated.broadcasting import broadcast_event, get_pending_events
    from escalated.services.notification_service import NotificationService
    from escalated.ticket_access import can_access_channel, ticket_access

    agent, visible, hidden, unassigned = access_setup
    settings.ESCALATED_BROADCASTING_ENABLED = True
    assert NotificationService._recipient_email(agent, hidden) is None
    assert NotificationService._recipient_email(agent, visible) == agent.email
    assert can_access_channel(agent, f"ticket.{visible.pk}")
    assert not can_access_channel(agent, "tickets")
    with patch("escalated.broadcasting.get_channel_layer", return_value=None):
        broadcast_event("ticket.created", f"ticket.{hidden.pk}", {"ticket_id": hidden.pk})
    with ticket_access(agent):
        assert get_pending_events(f"ticket.{hidden.pk}") == []
    assert len(get_pending_events(f"ticket.{hidden.pk}")) == 1


def test_assignment_skips_agents_from_other_accounts(settings, access_setup):
    from escalated.services.assignment_service import AssignmentService
    from tests.factories import UserFactory

    agent, visible, hidden, unassigned = access_setup
    eligible = UserFactory()
    visible.department.agents.add(eligible)
    company, other = DepartmentFactory(), DepartmentFactory()
    settings.ESCALATED = {
        **settings.ESCALATED,
        "ACCOUNTS": {
            "ENABLED": True,
            "SCOPE_AGENTS": True,
            "RESOLVER": lambda user: company if user.pk == eligible.pk else other,
        },
    }
    visible.account_type, visible.account_id = "escalated.Department", str(company.pk)
    visible.save()
    assert AssignmentService.auto_assign(visible) == eligible


def test_sla_targets_default_off_inactive_and_no_match(settings):
    from escalated.services.sla_service import SlaService
    from tests.factories import SlaPolicyFactory

    ticket = TicketFactory(ticket_type="question")
    target = SlaPolicyFactory(is_default=True, ticket_type="question")
    assert SlaService.select_policy(ticket) is None
    default = SlaPolicyFactory(is_default=True)
    assert SlaService.select_policy(ticket) == default
    settings.ESCALATED = {**settings.ESCALATED, "SLA": {"TARGETED": True}}
    assert SlaService.select_policy(ticket) == target
    target.is_active = False
    target.save()
    assert SlaService.select_policy(ticket) == default


@pytest.mark.parametrize("value", [{"id": "north"}, {"type": "company"}, "north", None])
def test_malformed_account_rules_fail_closed(value):
    from types import SimpleNamespace

    from escalated.services.automation_runner import AutomationRunner
    from escalated.services.workflow_engine import WorkflowEngine

    ticket = TicketFactory()
    conditions = [{"field": "account", "value": value}]
    assert not AutomationRunner()._find_matching_tickets(SimpleNamespace(conditions=conditions)).exists()
    assert not WorkflowEngine().evaluate_conditions(conditions, ticket)


def test_account_filter_pair_validation_and_case_sensitivity(client, settings, access_setup):
    agent, visible, hidden, unassigned = access_setup
    settings.ESCALATED = {**settings.ESCALATED, "ACCOUNTS": {"ENABLED": True}}
    Ticket.objects.filter(pk=visible.pk).update(account_type="company", account_id="North")
    client.force_login(agent)
    route = reverse("escalated:agent_ticket_list")
    assert client.get(route, {"account_id": "North"}, HTTP_X_INERTIA="true").status_code == 422
    response = client.get(route, {"account_type": "company", "account_id": "north"}, HTTP_X_INERTIA="true")
    assert response.json()["props"]["tickets"]["data"] == []
    response = client.get(route, {"account_type": "company", "account_id": "North"}, HTTP_X_INERTIA="true")
    assert [row["id"] for row in response.json()["props"]["tickets"]["data"]] == [visible.pk]
