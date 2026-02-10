"""
Integration tests for the admin API token management views.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from django.test import RequestFactory

from escalated.models import ApiToken
from escalated.views import admin_api_tokens
from tests.factories import (
    ApiTokenFactory,
    DepartmentFactory,
    UserFactory,
)


@pytest.fixture
def rf():
    return RequestFactory()


def _attach_session(request):
    """Attach a mock session to the request."""
    from django.contrib.sessions.backends.db import SessionStore
    request.session = SessionStore()


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdminApiTokensIndex:
    @patch("escalated.views.admin_api_tokens.render")
    def test_index_returns_tokens_for_admin(self, mock_render, rf):
        admin = UserFactory(username="admin_idx", is_staff=True, is_superuser=True)
        user = UserFactory(username="token_owner")
        department = DepartmentFactory()
        department.agents.add(user)
        ApiTokenFactory(user=user)
        ApiTokenFactory(user=user)

        mock_render.return_value = MagicMock(status_code=200)

        request = rf.get("/admin/api-tokens/")
        request.user = admin
        _attach_session(request)

        admin_api_tokens.api_tokens_index(request)

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        props = call_args[1]["props"] if "props" in call_args[1] else call_args[0][2]
        assert "tokens" in props
        assert len(props["tokens"]) == 2

    def test_index_forbidden_for_non_admin(self, rf):
        user = UserFactory(username="nonadmin_idx")

        request = rf.get("/admin/api-tokens/")
        request.user = user
        _attach_session(request)

        response = admin_api_tokens.api_tokens_index(request)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdminApiTokensCreate:
    def test_create_returns_plain_text_token(self, rf):
        admin = UserFactory(username="admin_create", is_staff=True, is_superuser=True)
        user = UserFactory(username="create_owner")

        request = rf.post(
            "/admin/api-tokens/create/",
            data=json.dumps({
                "name": "Test Token",
                "user_id": user.pk,
                "abilities": ["agent"],
                "expires_in_days": 30,
            }),
            content_type="application/json",
        )
        request.user = admin
        _attach_session(request)

        response = admin_api_tokens.api_tokens_create(request)

        assert response.status_code == 201
        data = json.loads(response.content)
        assert "plain_text_token" in data
        assert len(data["plain_text_token"]) == 64
        assert data["token"]["name"] == "Test Token"

        # Verify token exists in DB
        assert ApiToken.objects.filter(name="Test Token").exists()

    def test_create_missing_name_returns_422(self, rf):
        admin = UserFactory(username="admin_no_name", is_staff=True, is_superuser=True)
        user = UserFactory(username="owner_no_name")

        request = rf.post(
            "/admin/api-tokens/create/",
            data=json.dumps({"user_id": user.pk}),
            content_type="application/json",
        )
        request.user = admin
        _attach_session(request)

        response = admin_api_tokens.api_tokens_create(request)
        assert response.status_code == 422

    def test_create_missing_user_returns_422(self, rf):
        admin = UserFactory(username="admin_no_user", is_staff=True, is_superuser=True)

        request = rf.post(
            "/admin/api-tokens/create/",
            data=json.dumps({"name": "Token"}),
            content_type="application/json",
        )
        request.user = admin
        _attach_session(request)

        response = admin_api_tokens.api_tokens_create(request)
        assert response.status_code == 422

    def test_create_nonexistent_user_returns_404(self, rf):
        admin = UserFactory(username="admin_bad_user", is_staff=True, is_superuser=True)

        request = rf.post(
            "/admin/api-tokens/create/",
            data=json.dumps({"name": "Token", "user_id": 99999}),
            content_type="application/json",
        )
        request.user = admin
        _attach_session(request)

        response = admin_api_tokens.api_tokens_create(request)
        assert response.status_code == 404

    def test_create_forbidden_for_non_admin(self, rf):
        user = UserFactory(username="nonadmin_create")

        request = rf.post(
            "/admin/api-tokens/create/",
            data=json.dumps({"name": "Token", "user_id": user.pk}),
            content_type="application/json",
        )
        request.user = user
        _attach_session(request)

        response = admin_api_tokens.api_tokens_create(request)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdminApiTokensUpdate:
    def test_update_name_and_abilities(self, rf):
        admin = UserFactory(username="admin_update", is_staff=True, is_superuser=True)
        user = UserFactory(username="update_owner")
        token = ApiTokenFactory(user=user, abilities=["agent"])

        request = rf.post(
            f"/admin/api-tokens/{token.pk}/update/",
            data=json.dumps({
                "name": "Updated Name",
                "abilities": ["agent", "admin"],
            }),
            content_type="application/json",
        )
        request.user = admin
        _attach_session(request)

        response = admin_api_tokens.api_tokens_update(request, token.pk)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["token"]["name"] == "Updated Name"

        token.refresh_from_db()
        assert token.name == "Updated Name"
        assert token.abilities == ["agent", "admin"]

    def test_update_not_found_returns_404(self, rf):
        admin = UserFactory(username="admin_update_404", is_staff=True, is_superuser=True)

        request = rf.post(
            "/admin/api-tokens/99999/update/",
            data=json.dumps({"name": "X"}),
            content_type="application/json",
        )
        request.user = admin
        _attach_session(request)

        response = admin_api_tokens.api_tokens_update(request, 99999)
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Destroy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdminApiTokensDestroy:
    def test_destroy_removes_token(self, rf):
        admin = UserFactory(username="admin_destroy", is_staff=True, is_superuser=True)
        user = UserFactory(username="destroy_owner")
        token = ApiTokenFactory(user=user)
        token_pk = token.pk

        request = rf.post(f"/admin/api-tokens/{token.pk}/delete/")
        request.user = admin
        _attach_session(request)

        response = admin_api_tokens.api_tokens_destroy(request, token_pk)

        assert response.status_code == 200
        assert not ApiToken.objects.filter(pk=token_pk).exists()

    def test_destroy_nonexistent_token_is_idempotent(self, rf):
        admin = UserFactory(username="admin_destroy_ok", is_staff=True, is_superuser=True)

        request = rf.post("/admin/api-tokens/99999/delete/")
        request.user = admin
        _attach_session(request)

        response = admin_api_tokens.api_tokens_destroy(request, 99999)
        assert response.status_code == 200
