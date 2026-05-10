"""
Integration tests for the admin Users management views.

Mirrors escalated-laravel#94 (UserController). Because the Django host User
model doesn't ship is_admin / is_agent columns, the package maps:
    is_admin <-> User.is_staff
    is_agent <-> membership in any active Department
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from escalated.views import admin
from tests.factories import DepartmentFactory, UserFactory


@pytest.fixture
def rf():
    return RequestFactory()


def _attach_session(request):
    from django.contrib.sessions.backends.db import SessionStore

    request.session = SessionStore()


def _make_admin(username="admin_users"):
    return UserFactory(username=username, is_staff=True, is_superuser=True)


def _make_agent(username="agent_users"):
    user = UserFactory(username=username)
    department = DepartmentFactory(slug=f"dept-{username}")
    department.agents.add(user)
    return user


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdminUsersIndex:
    @patch("escalated.views.admin.render_page")
    def test_index_lists_users_with_flags_for_admin(self, mock_render, rf):
        admin_user = _make_admin("admin_idx")
        _make_agent("agent_idx")
        UserFactory(username="customer_idx", email="customer@example.com")

        mock_render.return_value = MagicMock(status_code=200)

        request = rf.get("/support/admin/users/")
        request.user = admin_user
        _attach_session(request)

        admin.users_index(request)

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        props = call_args[1]["props"] if "props" in call_args[1] else call_args[0][2]

        assert "users" in props
        emails = [row["email"] for row in props["users"]["data"]]
        assert any(email.startswith("admin_idx") for email in emails)
        assert "customer@example.com" in emails
        assert any(email.startswith("agent_idx") for email in emails)

        # Verify is_admin / is_agent flags are surfaced on rows.
        by_email = {row["email"]: row for row in props["users"]["data"]}
        admin_row = next(r for e, r in by_email.items() if e.startswith("admin_idx"))
        agent_row = next(r for e, r in by_email.items() if e.startswith("agent_idx"))
        customer_row = by_email["customer@example.com"]
        assert admin_row["is_admin"] is True
        assert agent_row["is_agent"] is True
        assert agent_row["is_admin"] is False
        assert customer_row["is_admin"] is False
        assert customer_row["is_agent"] is False

        # currentUserId reflects the request user.
        assert props["currentUserId"] == admin_user.pk

    def test_index_forbidden_for_non_admin(self, rf):
        agent = _make_agent("agent_forbid")

        request = rf.get("/support/admin/users/")
        request.user = agent
        _attach_session(request)

        response = admin.users_index(request)
        assert response.status_code == 403

    @patch("escalated.views.admin.render_page")
    def test_index_filters_by_search_term(self, mock_render, rf):
        admin_user = _make_admin("admin_search")
        UserFactory(username="jane_acme", email="jane@acme.test")
        UserFactory(username="bob_globex", email="bob@globex.test")

        mock_render.return_value = MagicMock(status_code=200)

        request = rf.get("/support/admin/users/?search=acme")
        request.user = admin_user
        _attach_session(request)

        admin.users_index(request)

        props = mock_render.call_args[1].get("props") or mock_render.call_args[0][2]
        emails = [row["email"] for row in props["users"]["data"]]
        assert "jane@acme.test" in emails
        assert "bob@globex.test" not in emails
        assert props["filters"]["search"] == "acme"


# ---------------------------------------------------------------------------
# updateRole
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdminUsersRole:
    def test_promote_to_admin_sets_is_staff_and_attaches_agent_department(self, rf):
        admin_user = _make_admin("admin_promote")
        target = UserFactory(username="someone_admin", email="someone@example.com")
        DepartmentFactory(slug="default-promote")

        request = rf.post(
            f"/support/admin/users/{target.pk}/role/",
            data=json.dumps({"role": "admin", "value": True}),
            content_type="application/json",
        )
        request.user = admin_user
        _attach_session(request)

        response = admin.users_role(request, target.pk)

        # back()-style redirect mirroring Laravel.
        assert response.status_code == 302

        target.refresh_from_db()
        assert target.is_staff is True
        # Admins are agents: target must now belong to at least one active dept.
        from escalated.models import Department

        assert Department.objects.filter(agents=target, is_active=True).exists()

    def test_promote_to_agent_only_does_not_grant_admin(self, rf):
        admin_user = _make_admin("admin_agentonly")
        target = UserFactory(username="someone_agent", email="someone_a@example.com")
        DepartmentFactory(slug="default-agentonly")

        request = rf.post(
            f"/support/admin/users/{target.pk}/role/",
            data=json.dumps({"role": "agent", "value": True}),
            content_type="application/json",
        )
        request.user = admin_user
        _attach_session(request)

        response = admin.users_role(request, target.pk)
        assert response.status_code == 302

        target.refresh_from_db()
        assert target.is_staff is False
        from escalated.models import Department

        assert Department.objects.filter(agents=target, is_active=True).exists()

    def test_prevents_self_demote(self, rf):
        admin_user = _make_admin("admin_selfdemote")

        request = rf.post(
            f"/support/admin/users/{admin_user.pk}/role/",
            data=json.dumps({"role": "admin", "value": False}),
            content_type="application/json",
        )
        request.user = admin_user
        _attach_session(request)

        response = admin.users_role(request, admin_user.pk)
        assert response.status_code == 302

        admin_user.refresh_from_db()
        # Crucially, the admin flag must NOT have been flipped.
        assert admin_user.is_staff is True

    def test_revoking_agent_from_admin_cascades_to_remove_admin(self, rf):
        admin_user = _make_admin("admin_cascade")
        target = _make_agent("target_cascade")
        target.is_staff = True
        target.save()

        request = rf.post(
            f"/support/admin/users/{target.pk}/role/",
            data=json.dumps({"role": "agent", "value": False}),
            content_type="application/json",
        )
        request.user = admin_user
        _attach_session(request)

        response = admin.users_role(request, target.pk)
        assert response.status_code == 302

        target.refresh_from_db()
        assert target.is_staff is False
        from escalated.models import Department

        assert not Department.objects.filter(agents=target, is_active=True).exists()

    def test_role_forbidden_for_non_admin(self, rf):
        agent = _make_agent("agent_role_forbid")
        target = UserFactory(username="target_role_forbid")

        request = rf.post(
            f"/support/admin/users/{target.pk}/role/",
            data=json.dumps({"role": "admin", "value": True}),
            content_type="application/json",
        )
        request.user = agent
        _attach_session(request)

        response = admin.users_role(request, target.pk)
        assert response.status_code == 403
