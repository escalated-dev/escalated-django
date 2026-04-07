import json
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

from escalated.models import (
    BusinessSchedule,
    Role,
    TicketStatus,
)
from escalated.views import admin
from tests.factories import (
    AuditLogFactory,
    BusinessScheduleFactory,
    HolidayFactory,
    PermissionFactory,
    RoleFactory,
    TicketFactory,
    TicketStatusFactory,
    UserFactory,
)


@pytest.fixture
def rf():
    return RequestFactory()


def _make_admin_request(rf, method, path, data=None, user=None):
    if user is None:
        user = UserFactory(username="admin_p1", is_staff=True, is_superuser=True)
    if method == "GET":
        request = rf.get(path)
    else:
        request = rf.post(path, data=data or {})
    request.user = user
    from django.contrib.sessions.backends.db import SessionStore

    request.session = SessionStore()
    return request


# ---------------------------------------------------------------------------
# Ticket Statuses
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStatusesAdminViews:
    @patch("escalated.views.admin.render_page")
    def test_index_returns_statuses(self, mock_render, rf):
        TicketStatusFactory(slug="test-s1")
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", "/admin/statuses/")
        admin.statuses_index(request)

        mock_render.assert_called_once()
        args = mock_render.call_args
        assert args[0][1] == "Escalated/Admin/Statuses/Index"
        props = args[1]["props"] if "props" in args[1] else args[0][2]
        assert "statuses" in props
        assert "categories" in props

    @patch("escalated.views.admin.render_page")
    def test_create_get_renders_form(self, mock_render, rf):
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", "/admin/statuses/create/")
        admin.statuses_create(request)

        mock_render.assert_called_once()

    def test_create_post_creates_status(self, rf):
        request = _make_admin_request(
            rf,
            "POST",
            "/admin/statuses/create/",
            data={
                "label": "Awaiting Response",
                "category": "pending",
                "color": "#ff0000",
                "position": "0",
            },
        )

        response = admin.statuses_create(request)
        assert response.status_code == 302
        assert TicketStatus.objects.filter(label="Awaiting Response").exists()

    def test_create_sets_default_clears_others(self, rf):
        existing = TicketStatusFactory(category="open", is_default=True, slug="default-existing")
        request = _make_admin_request(
            rf,
            "POST",
            "/admin/statuses/create/",
            data={
                "label": "New Default",
                "category": "open",
                "color": "#00ff00",
                "is_default": "true",
            },
        )

        admin.statuses_create(request)

        existing.refresh_from_db()
        assert existing.is_default is False
        new = TicketStatus.objects.get(label="New Default")
        assert new.is_default is True

    def test_edit_post_updates_status(self, rf):
        status = TicketStatusFactory(label="Old Label", slug="old-label")
        request = _make_admin_request(
            rf,
            "POST",
            f"/admin/statuses/{status.pk}/edit/",
            data={
                "label": "New Label",
                "category": "pending",
                "color": "#00ff00",
            },
        )

        response = admin.statuses_edit(request, status.pk)
        assert response.status_code == 302

        status.refresh_from_db()
        assert status.label == "New Label"
        assert status.category == "pending"

    def test_delete_removes_status(self, rf):
        status = TicketStatusFactory(slug="to-delete")
        request = _make_admin_request(rf, "POST", f"/admin/statuses/{status.pk}/delete/")

        response = admin.statuses_delete(request, status.pk)
        assert response.status_code == 302
        assert not TicketStatus.objects.filter(pk=status.pk).exists()

    def test_non_admin_forbidden(self, rf):
        user = UserFactory(username="nonadmin_status", is_staff=False)
        request = _make_admin_request(rf, "GET", "/admin/statuses/", user=user)

        response = admin.statuses_index(request)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Business Hours
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBusinessHoursAdminViews:
    @patch("escalated.views.admin.render_page")
    def test_index_returns_schedules(self, mock_render, rf):
        BusinessScheduleFactory()
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", "/admin/business-hours/")
        admin.business_hours_index(request)

        mock_render.assert_called_once()
        args = mock_render.call_args
        assert args[0][1] == "Escalated/Admin/BusinessHours/Index"
        props = args[1]["props"] if "props" in args[1] else args[0][2]
        assert "schedules" in props

    def test_create_post_with_holidays(self, rf):
        request = _make_admin_request(
            rf,
            "POST",
            "/admin/business-hours/create/",
            data={
                "name": "Test Schedule",
                "timezone": "UTC",
                "schedule": json.dumps({"monday": {"start": "09:00", "end": "17:00"}}),
                "holidays": json.dumps(
                    [
                        {"name": "Christmas", "date": "2026-12-25", "recurring": True},
                    ]
                ),
            },
        )

        response = admin.business_hours_create(request)
        assert response.status_code == 302

        sched = BusinessSchedule.objects.get(name="Test Schedule")
        assert sched.holidays.count() == 1
        assert sched.holidays.first().name == "Christmas"
        assert sched.holidays.first().recurring is True

    def test_edit_syncs_holidays(self, rf):
        sched = BusinessScheduleFactory()
        HolidayFactory(schedule=sched, name="Old Holiday")

        request = _make_admin_request(
            rf,
            "POST",
            f"/admin/business-hours/{sched.pk}/edit/",
            data={
                "name": sched.name,
                "timezone": "UTC",
                "schedule": json.dumps(sched.schedule),
                "holidays": json.dumps(
                    [
                        {"name": "New Holiday", "date": "2026-07-04", "recurring": False},
                    ]
                ),
            },
        )

        response = admin.business_hours_edit(request, sched.pk)
        assert response.status_code == 302

        assert sched.holidays.count() == 1
        assert sched.holidays.first().name == "New Holiday"

    def test_delete_removes_schedule(self, rf):
        sched = BusinessScheduleFactory()
        request = _make_admin_request(rf, "POST", f"/admin/business-hours/{sched.pk}/delete/")

        response = admin.business_hours_delete(request, sched.pk)
        assert response.status_code == 302
        assert not BusinessSchedule.objects.filter(pk=sched.pk).exists()

    def test_default_clears_others(self, rf):
        existing = BusinessScheduleFactory(is_default=True)
        request = _make_admin_request(
            rf,
            "POST",
            "/admin/business-hours/create/",
            data={
                "name": "New Default",
                "timezone": "UTC",
                "is_default": "true",
                "schedule": json.dumps({"monday": {"start": "09:00", "end": "17:00"}}),
            },
        )

        admin.business_hours_create(request)

        existing.refresh_from_db()
        assert existing.is_default is False
        assert BusinessSchedule.objects.get(name="New Default").is_default is True


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRolesAdminViews:
    @patch("escalated.views.admin.render_page")
    def test_index_returns_roles(self, mock_render, rf):
        RoleFactory(slug="test-role-idx")
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", "/admin/roles/")
        admin.roles_index(request)

        mock_render.assert_called_once()
        args = mock_render.call_args
        assert args[0][1] == "Escalated/Admin/Roles/Index"
        props = args[1]["props"] if "props" in args[1] else args[0][2]
        assert "roles" in props

    def test_create_post_with_permissions(self, rf):
        perm = PermissionFactory(slug="test-perm-create")
        request = _make_admin_request(
            rf,
            "POST",
            "/admin/roles/create/",
            data={
                "name": "Support Lead",
                "description": "Leads the support team",
                "permissions": [str(perm.pk)],
            },
        )

        response = admin.roles_create(request)
        assert response.status_code == 302

        role = Role.objects.get(name="Support Lead")
        assert role.permissions.count() == 1
        assert perm in role.permissions.all()

    def test_edit_updates_role(self, rf):
        role = RoleFactory(name="Old Role", slug="old-role")
        request = _make_admin_request(
            rf,
            "POST",
            f"/admin/roles/{role.pk}/edit/",
            data={
                "name": "Updated Role",
                "description": "Updated description",
            },
        )

        response = admin.roles_edit(request, role.pk)
        assert response.status_code == 302

        role.refresh_from_db()
        assert role.name == "Updated Role"

    def test_delete_system_role_forbidden(self, rf):
        role = RoleFactory(is_system=True, slug="system-role")
        request = _make_admin_request(rf, "POST", f"/admin/roles/{role.pk}/delete/")

        response = admin.roles_delete(request, role.pk)
        assert response.status_code == 403
        assert Role.objects.filter(pk=role.pk).exists()

    def test_delete_normal_role(self, rf):
        role = RoleFactory(slug="deletable-role")
        request = _make_admin_request(rf, "POST", f"/admin/roles/{role.pk}/delete/")

        response = admin.roles_delete(request, role.pk)
        assert response.status_code == 302
        assert not Role.objects.filter(pk=role.pk).exists()

    def test_edit_syncs_permissions(self, rf):
        role = RoleFactory(slug="perm-sync-role")
        p1 = PermissionFactory(slug="perm-a")
        p2 = PermissionFactory(slug="perm-b")
        role.permissions.add(p1)

        request = _make_admin_request(
            rf,
            "POST",
            f"/admin/roles/{role.pk}/edit/",
            data={
                "name": role.name,
                "permissions": [str(p2.pk)],
            },
        )

        admin.roles_edit(request, role.pk)

        role.refresh_from_db()
        assert p1 not in role.permissions.all()
        assert p2 in role.permissions.all()


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAuditLogsAdminViews:
    @patch("escalated.views.admin.render_page")
    def test_index_returns_logs(self, mock_render, rf):
        user = UserFactory(username="audit_admin", is_staff=True, is_superuser=True)
        ticket = TicketFactory()
        AuditLogFactory(
            user=user,
            auditable_content_type=ContentType.objects.get_for_model(ticket),
            auditable_object_id=ticket.pk,
        )
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", "/admin/audit-logs/", user=user)
        admin.audit_logs_index(request)

        mock_render.assert_called_once()
        args = mock_render.call_args
        assert args[0][1] == "Escalated/Admin/AuditLog/Index"
        props = args[1]["props"] if "props" in args[1] else args[0][2]
        assert "logs" in props
        assert "pagination" in props
        assert "filters" in props
        assert "actions" in props
        assert "resource_types" in props

    @patch("escalated.views.admin.render_page")
    def test_index_with_filters(self, mock_render, rf):
        user = UserFactory(username="audit_filter", is_staff=True, is_superuser=True)
        mock_render.return_value = MagicMock(status_code=200)

        request = rf.get("/admin/audit-logs/", {"action": "created", "user_id": str(user.pk)})
        request.user = user
        from django.contrib.sessions.backends.db import SessionStore

        request.session = SessionStore()

        admin.audit_logs_index(request)

        mock_render.assert_called_once()
        args = mock_render.call_args
        props = args[1]["props"] if "props" in args[1] else args[0][2]
        assert props["filters"]["action"] == "created"
        assert props["filters"]["user_id"] == str(user.pk)

    def test_non_admin_forbidden(self, rf):
        user = UserFactory(username="nonadmin_audit", is_staff=False)
        request = _make_admin_request(rf, "GET", "/admin/audit-logs/", user=user)

        response = admin.audit_logs_index(request)
        assert response.status_code == 403
