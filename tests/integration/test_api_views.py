"""
Integration tests for the Escalated REST API views.

These tests exercise the views directly using RequestFactory,
simulating authenticated API requests by pre-setting request.user
and request.api_token (as the middleware would do).
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from django.test import RequestFactory
from django.utils import timezone

from escalated.models import (
    ApiToken,
    CannedResponse,
    Department,
    Macro,
    Tag,
    Ticket,
)
from escalated.views import api
from tests.factories import (
    ApiTokenFactory,
    CannedResponseFactory,
    DepartmentFactory,
    MacroFactory,
    ReplyFactory,
    TagFactory,
    TicketFactory,
    UserFactory,
)


@pytest.fixture
def rf():
    return RequestFactory()


def _api_get(rf, path, user, api_token, query_params=None):
    """Create a GET request simulating API authentication."""
    request = rf.get(path, data=query_params or {})
    request.user = user
    request.api_token = api_token
    return request


def _api_post(rf, path, user, api_token, data=None):
    """Create a POST request with JSON body simulating API authentication."""
    body = json.dumps(data or {})
    request = rf.post(
        path,
        data=body,
        content_type="application/json",
    )
    request.user = user
    request.api_token = api_token
    return request


def _api_patch(rf, path, user, api_token, data=None):
    """Create a PATCH request with JSON body simulating API authentication."""
    body = json.dumps(data or {})
    request = rf.patch(
        path,
        data=body,
        content_type="application/json",
    )
    request.user = user
    request.api_token = api_token
    return request


def _api_delete(rf, path, user, api_token):
    """Create a DELETE request simulating API authentication."""
    request = rf.delete(path)
    request.user = user
    request.api_token = api_token
    return request


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiAuthValidate:
    def test_validate_returns_user_info(self, rf):
        user = UserFactory(username="auth_validate_user", is_staff=True)
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user, abilities=["agent", "admin"])

        request = _api_post(rf, "/api/auth/validate/", user, token)
        response = api.auth_validate(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["user"]["id"] == user.pk
        assert data["user"]["email"] == user.email
        assert data["abilities"] == ["agent", "admin"]
        assert data["token_name"] == token.name
        assert data["is_agent"] is True
        assert data["is_admin"] is True


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiDashboard:
    def test_dashboard_returns_stats(self, rf):
        user = UserFactory(username="dash_user")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        # Create some tickets
        TicketFactory(status=Ticket.Status.OPEN)
        TicketFactory(status=Ticket.Status.OPEN, assigned_to=user)
        TicketFactory(status=Ticket.Status.OPEN, assigned_to=None)

        request = _api_get(rf, "/api/dashboard/", user, token)
        response = api.dashboard(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "stats" in data
        assert "open" in data["stats"]
        assert "my_assigned" in data["stats"]
        assert "unassigned" in data["stats"]
        assert "sla_breached" in data["stats"]
        assert "resolved_today" in data["stats"]
        assert "recent_tickets" in data
        assert "needs_attention" in data
        assert "my_performance" in data


# ---------------------------------------------------------------------------
# Tickets - List
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiTicketList:
    def test_ticket_list_returns_paginated_data(self, rf):
        user = UserFactory(username="list_user")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        for _ in range(3):
            TicketFactory()

        request = _api_get(rf, "/api/tickets/", user, token)
        response = api.ticket_list(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "data" in data
        assert "meta" in data
        assert data["meta"]["total"] == 3
        assert len(data["data"]) == 3

    def test_ticket_list_filter_by_status(self, rf):
        user = UserFactory(username="list_status")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        TicketFactory(status=Ticket.Status.OPEN)
        TicketFactory(status=Ticket.Status.CLOSED)

        request = _api_get(
            rf, "/api/tickets/", user, token, {"status": "open"}
        )
        response = api.ticket_list(request)

        data = json.loads(response.content)
        assert data["meta"]["total"] == 1
        assert data["data"][0]["status"] == "open"

    def test_ticket_list_filter_by_priority(self, rf):
        user = UserFactory(username="list_priority")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        TicketFactory(priority=Ticket.Priority.HIGH)
        TicketFactory(priority=Ticket.Priority.LOW)

        request = _api_get(
            rf, "/api/tickets/", user, token, {"priority": "high"}
        )
        response = api.ticket_list(request)

        data = json.loads(response.content)
        assert data["meta"]["total"] == 1
        assert data["data"][0]["priority"] == "high"

    def test_ticket_list_filter_by_search(self, rf):
        user = UserFactory(username="list_search")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        TicketFactory(subject="Payment refund issue")
        TicketFactory(subject="General question")

        request = _api_get(
            rf, "/api/tickets/", user, token, {"search": "Payment"}
        )
        response = api.ticket_list(request)

        data = json.loads(response.content)
        assert data["meta"]["total"] == 1

    def test_ticket_list_pagination(self, rf):
        user = UserFactory(username="list_page")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        for _ in range(30):
            TicketFactory()

        request = _api_get(
            rf, "/api/tickets/", user, token, {"per_page": "10", "page": "2"}
        )
        response = api.ticket_list(request)

        data = json.loads(response.content)
        assert data["meta"]["per_page"] == 10
        assert data["meta"]["current_page"] == 2
        assert len(data["data"]) == 10


# ---------------------------------------------------------------------------
# Tickets - Show
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiTicketShow:
    def test_ticket_show_by_reference(self, rf):
        user = UserFactory(username="show_ref")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory(requester=user)

        request = _api_get(rf, f"/api/tickets/{ticket.reference}/", user, token)
        response = api.ticket_show(request, ticket.reference)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["data"]["reference"] == ticket.reference
        assert data["data"]["subject"] == ticket.subject

    def test_ticket_show_by_id(self, rf):
        user = UserFactory(username="show_id")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()

        request = _api_get(rf, f"/api/tickets/{ticket.pk}/", user, token)
        response = api.ticket_show(request, str(ticket.pk))

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["data"]["id"] == ticket.pk

    def test_ticket_show_not_found(self, rf):
        user = UserFactory(username="show_404")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        request = _api_get(rf, "/api/tickets/NONEXIST/", user, token)
        response = api.ticket_show(request, "NONEXIST")

        assert response.status_code == 404

    def test_ticket_show_includes_replies(self, rf):
        user = UserFactory(username="show_replies")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()
        ReplyFactory(ticket=ticket, author=user, body="Test reply")

        request = _api_get(rf, f"/api/tickets/{ticket.reference}/", user, token)
        response = api.ticket_show(request, ticket.reference)

        data = json.loads(response.content)
        assert "replies" in data["data"]
        assert len(data["data"]["replies"]) == 1
        assert data["data"]["replies"][0]["body"] == "Test reply"


# ---------------------------------------------------------------------------
# Tickets - Create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiTicketCreate:
    @patch("escalated.views.api.TicketService")
    def test_ticket_create_success(self, MockService, rf):
        user = UserFactory(username="create_user")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        # Create real ticket to return
        ticket = TicketFactory(
            requester=user, subject="API Test", description="API Description"
        )

        mock_svc = MagicMock()
        mock_svc.create.return_value = ticket
        MockService.return_value = mock_svc

        request = _api_post(rf, "/api/tickets/create/", user, token, {
            "subject": "API Test",
            "description": "API Description",
            "priority": "high",
        })
        response = api.ticket_create(request)

        assert response.status_code == 201
        data = json.loads(response.content)
        assert data["message"] == "Ticket created."
        assert "data" in data

    def test_ticket_create_missing_subject_returns_422(self, rf):
        user = UserFactory(username="create_no_subject")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        request = _api_post(rf, "/api/tickets/create/", user, token, {
            "description": "Some desc",
        })
        response = api.ticket_create(request)

        assert response.status_code == 422
        data = json.loads(response.content)
        assert "subject" in data["errors"]

    def test_ticket_create_missing_description_returns_422(self, rf):
        user = UserFactory(username="create_no_desc")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        request = _api_post(rf, "/api/tickets/create/", user, token, {
            "subject": "Subject only",
        })
        response = api.ticket_create(request)

        assert response.status_code == 422
        data = json.loads(response.content)
        assert "description" in data["errors"]

    def test_ticket_create_invalid_priority_returns_422(self, rf):
        user = UserFactory(username="create_bad_prio")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        request = _api_post(rf, "/api/tickets/create/", user, token, {
            "subject": "Test",
            "description": "Test",
            "priority": "invalid_priority",
        })
        response = api.ticket_create(request)

        assert response.status_code == 422
        data = json.loads(response.content)
        assert "priority" in data["errors"]


# ---------------------------------------------------------------------------
# Tickets - Reply
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiTicketReply:
    @patch("escalated.views.api.TicketService")
    def test_ticket_reply_success(self, MockService, rf):
        user = UserFactory(username="reply_user")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()
        reply = ReplyFactory(ticket=ticket, author=user, body="Reply body")

        mock_svc = MagicMock()
        mock_svc.reply.return_value = reply
        MockService.return_value = mock_svc

        request = _api_post(
            rf, f"/api/tickets/{ticket.reference}/reply/", user, token,
            {"body": "Reply body"},
        )
        response = api.ticket_reply(request, ticket.reference)

        assert response.status_code == 201
        data = json.loads(response.content)
        assert data["message"] == "Reply sent."
        assert data["data"]["body"] == "Reply body"

    def test_ticket_reply_missing_body_returns_422(self, rf):
        user = UserFactory(username="reply_no_body")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()

        request = _api_post(
            rf, f"/api/tickets/{ticket.reference}/reply/", user, token, {}
        )
        response = api.ticket_reply(request, ticket.reference)

        assert response.status_code == 422

    def test_ticket_reply_not_found(self, rf):
        user = UserFactory(username="reply_404")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        request = _api_post(
            rf, "/api/tickets/NONEXIST/reply/", user, token,
            {"body": "Reply"},
        )
        response = api.ticket_reply(request, "NONEXIST")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tickets - Status
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiTicketStatus:
    @patch("escalated.views.api.TicketService")
    def test_ticket_status_update(self, MockService, rf):
        user = UserFactory(username="status_user")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory(status=Ticket.Status.OPEN)

        mock_svc = MagicMock()
        MockService.return_value = mock_svc

        request = _api_patch(
            rf, f"/api/tickets/{ticket.reference}/status/", user, token,
            {"status": "in_progress"},
        )
        response = api.ticket_status(request, ticket.reference)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["message"] == "Status updated."
        assert data["status"] == "in_progress"

    def test_ticket_status_invalid_returns_422(self, rf):
        user = UserFactory(username="status_invalid")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()

        request = _api_patch(
            rf, f"/api/tickets/{ticket.reference}/status/", user, token,
            {"status": "nonexistent"},
        )
        response = api.ticket_status(request, ticket.reference)

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Tickets - Priority
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiTicketPriority:
    @patch("escalated.views.api.TicketService")
    def test_ticket_priority_update(self, MockService, rf):
        user = UserFactory(username="priority_user")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory(priority=Ticket.Priority.MEDIUM)

        mock_svc = MagicMock()
        MockService.return_value = mock_svc

        request = _api_patch(
            rf, f"/api/tickets/{ticket.reference}/priority/", user, token,
            {"priority": "urgent"},
        )
        response = api.ticket_priority(request, ticket.reference)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["priority"] == "urgent"

    def test_ticket_priority_invalid_returns_422(self, rf):
        user = UserFactory(username="prio_invalid")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()

        request = _api_patch(
            rf, f"/api/tickets/{ticket.reference}/priority/", user, token,
            {"priority": "super_duper"},
        )
        response = api.ticket_priority(request, ticket.reference)

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Tickets - Assign
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiTicketAssign:
    @patch("escalated.views.api.TicketService")
    def test_ticket_assign_success(self, MockService, rf):
        user = UserFactory(username="assign_user")
        agent = UserFactory(username="assign_agent")
        department = DepartmentFactory()
        department.agents.add(user, agent)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()

        mock_svc = MagicMock()
        MockService.return_value = mock_svc

        request = _api_post(
            rf, f"/api/tickets/{ticket.reference}/assign/", user, token,
            {"agent_id": agent.pk},
        )
        response = api.ticket_assign(request, ticket.reference)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["message"] == "Ticket assigned."

    def test_ticket_assign_missing_agent_id_returns_422(self, rf):
        user = UserFactory(username="assign_missing")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()

        request = _api_post(
            rf, f"/api/tickets/{ticket.reference}/assign/", user, token, {}
        )
        response = api.ticket_assign(request, ticket.reference)

        assert response.status_code == 422

    def test_ticket_assign_agent_not_found_returns_404(self, rf):
        user = UserFactory(username="assign_404")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()

        request = _api_post(
            rf, f"/api/tickets/{ticket.reference}/assign/", user, token,
            {"agent_id": 99999},
        )
        response = api.ticket_assign(request, ticket.reference)

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tickets - Follow
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiTicketFollow:
    def test_ticket_follow_toggles(self, rf):
        user = UserFactory(username="follow_user")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()

        # Follow
        request = _api_post(
            rf, f"/api/tickets/{ticket.reference}/follow/", user, token
        )
        response = api.ticket_follow(request, ticket.reference)

        data = json.loads(response.content)
        assert data["following"] is True

        # Unfollow
        request = _api_post(
            rf, f"/api/tickets/{ticket.reference}/follow/", user, token
        )
        response = api.ticket_follow(request, ticket.reference)

        data = json.loads(response.content)
        assert data["following"] is False


# ---------------------------------------------------------------------------
# Tickets - Tags
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiTicketTags:
    @patch("escalated.views.api.TicketService")
    def test_ticket_tags_sync(self, MockService, rf):
        user = UserFactory(username="tags_user")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()
        tag1 = TagFactory(name="Bug", slug="bug")
        tag2 = TagFactory(name="Feature", slug="feature")

        mock_svc = MagicMock()
        MockService.return_value = mock_svc

        request = _api_post(
            rf, f"/api/tickets/{ticket.reference}/tags/", user, token,
            {"tag_ids": [tag1.pk, tag2.pk]},
        )
        response = api.ticket_tags(request, ticket.reference)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["message"] == "Tags updated."

    def test_ticket_tags_missing_tag_ids_returns_422(self, rf):
        user = UserFactory(username="tags_missing")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()

        request = _api_post(
            rf, f"/api/tickets/{ticket.reference}/tags/", user, token, {}
        )
        response = api.ticket_tags(request, ticket.reference)

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Tickets - Macro
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiTicketMacro:
    def test_ticket_macro_not_found_returns_404(self, rf):
        user = UserFactory(username="macro_404")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()

        request = _api_post(
            rf, f"/api/tickets/{ticket.reference}/macro/", user, token,
            {"macro_id": 99999},
        )
        response = api.ticket_apply_macro(request, ticket.reference)

        assert response.status_code == 404

    def test_ticket_macro_missing_id_returns_422(self, rf):
        user = UserFactory(username="macro_missing")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()

        request = _api_post(
            rf, f"/api/tickets/{ticket.reference}/macro/", user, token, {}
        )
        response = api.ticket_apply_macro(request, ticket.reference)

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Tickets - Delete
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiTicketDelete:
    def test_ticket_delete_success(self, rf):
        user = UserFactory(username="delete_user")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        ticket = TicketFactory()
        ticket_pk = ticket.pk

        request = _api_delete(
            rf, f"/api/tickets/{ticket.reference}/delete/", user, token
        )
        response = api.ticket_destroy(request, ticket.reference)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["message"] == "Ticket deleted."
        assert not Ticket.objects.filter(pk=ticket_pk).exists()

    def test_ticket_delete_not_found(self, rf):
        user = UserFactory(username="delete_404")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        request = _api_delete(
            rf, "/api/tickets/NONEXIST/delete/", user, token
        )
        response = api.ticket_destroy(request, "NONEXIST")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiResources:
    def test_resource_agents(self, rf):
        user = UserFactory(username="res_agents", is_staff=True)
        token = ApiTokenFactory(user=user)

        department = DepartmentFactory()
        agent1 = UserFactory(username="agent_res1")
        department.agents.add(agent1)

        request = _api_get(rf, "/api/agents/", user, token)
        response = api.resource_agents(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "data" in data
        # Should include at least the agent and the staff user
        assert len(data["data"]) >= 1

    def test_resource_departments(self, rf):
        user = UserFactory(username="res_depts")
        token = ApiTokenFactory(user=user)

        DepartmentFactory(name="Support", slug="support")
        DepartmentFactory(name="Sales", slug="sales")

        request = _api_get(rf, "/api/departments/", user, token)
        response = api.resource_departments(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data["data"]) >= 2

    def test_resource_tags(self, rf):
        user = UserFactory(username="res_tags")
        token = ApiTokenFactory(user=user)

        TagFactory(name="Bug", slug="bug-res")
        TagFactory(name="Feature", slug="feature-res")

        request = _api_get(rf, "/api/tags/", user, token)
        response = api.resource_tags(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data["data"]) >= 2

    def test_resource_canned_responses(self, rf):
        user = UserFactory(username="res_canned")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        CannedResponseFactory(created_by=user, title="Hello")

        request = _api_get(rf, "/api/canned-responses/", user, token)
        response = api.resource_canned_responses(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data["data"]) >= 1

    def test_resource_macros(self, rf):
        user = UserFactory(username="res_macros")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user)

        MacroFactory(created_by=user, name="Close and tag")

        request = _api_get(rf, "/api/macros/", user, token)
        response = api.resource_macros(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data["data"]) >= 1

    def test_resource_realtime_config(self, rf):
        user = UserFactory(username="res_realtime")
        token = ApiTokenFactory(user=user)

        request = _api_get(rf, "/api/realtime/config/", user, token)
        response = api.resource_realtime_config(request)

        assert response.status_code == 200
