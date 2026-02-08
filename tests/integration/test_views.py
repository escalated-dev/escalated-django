import pytest
from unittest.mock import patch, MagicMock

from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser

from escalated.models import Ticket, Department, Tag
from escalated.views import customer, agent, admin
from tests.factories import (
    UserFactory,
    TicketFactory,
    DepartmentFactory,
    TagFactory,
    SlaPolicyFactory,
)


@pytest.fixture
def rf():
    return RequestFactory()


def _attach_session(request):
    """Attach a mock session to the request for middleware compat."""
    from django.contrib.sessions.backends.db import SessionStore
    request.session = SessionStore()


# ---------------------------------------------------------------------------
# Customer views
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCustomerViews:
    @patch("escalated.views.customer.render")
    def test_ticket_list_returns_user_tickets(self, mock_render, rf):
        user = UserFactory(username="cust_list")
        ticket = TicketFactory(requester=user)

        request = rf.get("/tickets/")
        request.user = user
        _attach_session(request)

        mock_render.return_value = MagicMock(status_code=200)
        customer.ticket_list(request)

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        assert call_args[0][1] == "Escalated/Customer/Index"
        props = call_args[1]["props"] if "props" in call_args[1] else call_args[0][2]
        assert "tickets" in props
        assert "pagination" in props

    @patch("escalated.views.customer.render")
    def test_ticket_create_shows_form(self, mock_render, rf):
        user = UserFactory(username="cust_create")

        request = rf.get("/tickets/create/")
        request.user = user
        _attach_session(request)

        mock_render.return_value = MagicMock(status_code=200)
        customer.ticket_create(request)

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        assert call_args[0][1] == "Escalated/Customer/Create"

    @patch("escalated.views.customer.render")
    def test_ticket_show_returns_ticket(self, mock_render, rf):
        user = UserFactory(username="cust_show")
        ticket = TicketFactory(requester=user)

        request = rf.get(f"/tickets/{ticket.pk}/")
        request.user = user
        _attach_session(request)

        mock_render.return_value = MagicMock(status_code=200)
        customer.ticket_show(request, ticket.pk)

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        assert call_args[0][1] == "Escalated/Customer/Show"

    def test_ticket_show_forbidden_for_other_user(self, rf):
        user1 = UserFactory(username="cust_show1")
        user2 = UserFactory(username="cust_show2")
        ticket = TicketFactory(requester=user1)

        request = rf.get(f"/tickets/{ticket.pk}/")
        request.user = user2
        _attach_session(request)

        response = customer.ticket_show(request, ticket.pk)
        assert response.status_code == 403

    def test_ticket_show_not_found(self, rf):
        user = UserFactory(username="cust_notfound")
        request = rf.get("/tickets/99999/")
        request.user = user
        _attach_session(request)

        response = customer.ticket_show(request, 99999)
        assert response.status_code == 404

    def test_ticket_store_creates_ticket(self, rf):
        user = UserFactory(username="cust_store")

        request = rf.post("/tickets/store/", {
            "subject": "New Issue",
            "description": "I need help with something",
            "priority": "high",
        })
        request.user = user
        _attach_session(request)

        response = customer.ticket_store(request)
        assert response.status_code == 302  # Redirect after create
        assert Ticket.objects.filter(subject="New Issue").exists()

    def test_ticket_close(self, rf):
        user = UserFactory(username="cust_close")
        ticket = TicketFactory(requester=user, status=Ticket.Status.OPEN)

        request = rf.post(f"/tickets/{ticket.pk}/close/")
        request.user = user
        _attach_session(request)

        response = customer.ticket_close(request, ticket.pk)
        assert response.status_code == 302

        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.CLOSED


# ---------------------------------------------------------------------------
# Agent views
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAgentViews:
    @patch("escalated.views.agent.render")
    def test_dashboard_returns_stats(self, mock_render, rf):
        department = DepartmentFactory()
        agent_user = UserFactory(username="agent_dash")
        department.agents.add(agent_user)

        request = rf.get("/agent/")
        request.user = agent_user
        _attach_session(request)

        mock_render.return_value = MagicMock(status_code=200)
        agent.dashboard(request)

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        assert call_args[0][1] == "Escalated/Agent/Dashboard"
        props = call_args[1]["props"] if "props" in call_args[1] else call_args[0][2]
        assert "stats" in props

    @patch("escalated.views.agent.render")
    def test_ticket_list_with_filters(self, mock_render, rf):
        department = DepartmentFactory()
        agent_user = UserFactory(username="agent_list")
        department.agents.add(agent_user)
        TicketFactory(status=Ticket.Status.OPEN)

        request = rf.get("/agent/tickets/?status=open")
        request.user = agent_user
        _attach_session(request)

        mock_render.return_value = MagicMock(status_code=200)
        agent.ticket_list(request)

        mock_render.assert_called_once()

    def test_dashboard_forbidden_for_non_agent(self, rf):
        user = UserFactory(username="non_agent")

        request = rf.get("/agent/")
        request.user = user
        _attach_session(request)

        response = agent.dashboard(request)
        assert response.status_code == 403

    def test_ticket_assign(self, rf):
        department = DepartmentFactory()
        agent_user = UserFactory(username="agent_assign")
        target_agent = UserFactory(username="target_agent")
        department.agents.add(agent_user, target_agent)

        ticket = TicketFactory(status=Ticket.Status.OPEN)

        request = rf.post(f"/agent/tickets/{ticket.pk}/assign/", {
            "agent_id": target_agent.pk,
        })
        request.user = agent_user
        _attach_session(request)

        response = agent.ticket_assign(request, ticket.pk)
        assert response.status_code == 302

        ticket.refresh_from_db()
        assert ticket.assigned_to == target_agent

    def test_ticket_status_change(self, rf):
        department = DepartmentFactory()
        agent_user = UserFactory(username="agent_status")
        department.agents.add(agent_user)
        ticket = TicketFactory(status=Ticket.Status.OPEN)

        request = rf.post(f"/agent/tickets/{ticket.pk}/status/", {
            "status": "in_progress",
        })
        request.user = agent_user
        _attach_session(request)

        response = agent.ticket_status(request, ticket.pk)
        assert response.status_code == 302

        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.IN_PROGRESS

    def test_ticket_priority_change(self, rf):
        department = DepartmentFactory()
        agent_user = UserFactory(username="agent_priority")
        department.agents.add(agent_user)
        ticket = TicketFactory(priority=Ticket.Priority.MEDIUM)

        request = rf.post(f"/agent/tickets/{ticket.pk}/priority/", {
            "priority": "urgent",
        })
        request.user = agent_user
        _attach_session(request)

        response = agent.ticket_priority(request, ticket.pk)
        assert response.status_code == 302

        ticket.refresh_from_db()
        assert ticket.priority == Ticket.Priority.URGENT


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAdminViews:
    @patch("escalated.views.admin.render")
    def test_reports_returns_stats(self, mock_render, rf):
        admin_user = UserFactory(
            username="admin_reports", is_staff=True, is_superuser=True
        )

        request = rf.get("/admin/reports/")
        request.user = admin_user
        _attach_session(request)

        mock_render.return_value = MagicMock(status_code=200)
        admin.reports(request)

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        assert call_args[0][1] == "Escalated/Admin/Reports"

    def test_reports_forbidden_for_non_admin(self, rf):
        user = UserFactory(username="non_admin_reports")

        request = rf.get("/admin/reports/")
        request.user = user
        _attach_session(request)

        response = admin.reports(request)
        assert response.status_code == 403

    def test_departments_create(self, rf):
        admin_user = UserFactory(
            username="admin_dept", is_staff=True, is_superuser=True
        )

        request = rf.post("/admin/departments/create/", {
            "name": "Engineering",
            "slug": "engineering",
            "description": "Engineering team",
            "is_active": "true",
        })
        request.user = admin_user
        _attach_session(request)

        response = admin.departments_create(request)
        assert response.status_code == 302
        assert Department.objects.filter(slug="engineering").exists()

    def test_tags_create(self, rf):
        admin_user = UserFactory(
            username="admin_tag", is_staff=True, is_superuser=True
        )

        request = rf.post("/admin/tags/create/", {
            "name": "Bug",
            "slug": "bug",
            "color": "#ef4444",
        })
        request.user = admin_user
        _attach_session(request)

        response = admin.tags_create(request)
        assert response.status_code == 302
        assert Tag.objects.filter(slug="bug").exists()

    def test_tags_delete(self, rf):
        admin_user = UserFactory(
            username="admin_tag_del", is_staff=True, is_superuser=True
        )
        tag = TagFactory(name="ToDelete", slug="to-delete")

        request = rf.post(f"/admin/tags/{tag.pk}/delete/")
        request.user = admin_user
        _attach_session(request)

        response = admin.tags_delete(request, tag.pk)
        assert response.status_code == 302
        assert not Tag.objects.filter(pk=tag.pk).exists()
