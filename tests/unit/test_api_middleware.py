"""
Unit tests for the API authentication and rate limit middleware.
"""

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory
from django.utils import timezone

from escalated.api_middleware import AuthenticateApiToken, ApiRateLimit
from escalated.models import ApiToken
from tests.factories import UserFactory, DepartmentFactory, ApiTokenFactory


@pytest.fixture
def rf():
    return RequestFactory()


def _make_middleware_pair():
    """Create instances of both middleware."""
    auth = AuthenticateApiToken(lambda r: MagicMock(status_code=200))
    rate = ApiRateLimit(lambda r: MagicMock(status_code=200))
    return auth, rate


@pytest.mark.django_db
class TestAuthenticateApiToken:
    def test_missing_authorization_header_returns_401(self, rf):
        auth, _ = _make_middleware_pair()
        request = rf.get("/api/test/")

        response = auth.process_view(request, None, [], {})
        assert response is not None
        assert response.status_code == 401
        data = json.loads(response.content)
        assert data["message"] == "Unauthenticated."

    def test_non_bearer_authorization_returns_401(self, rf):
        auth, _ = _make_middleware_pair()
        request = rf.get("/api/test/", HTTP_AUTHORIZATION="Basic abc123")

        response = auth.process_view(request, None, [], {})
        assert response is not None
        assert response.status_code == 401

    def test_empty_bearer_token_returns_401(self, rf):
        auth, _ = _make_middleware_pair()
        request = rf.get("/api/test/", HTTP_AUTHORIZATION="Bearer ")

        response = auth.process_view(request, None, [], {})
        assert response is not None
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, rf):
        auth, _ = _make_middleware_pair()
        request = rf.get(
            "/api/test/",
            HTTP_AUTHORIZATION="Bearer invalid_token_value",
        )

        response = auth.process_view(request, None, [], {})
        assert response is not None
        assert response.status_code == 401
        data = json.loads(response.content)
        assert data["message"] == "Invalid token."

    def test_expired_token_returns_401(self, rf):
        user = UserFactory(username="expired_mw")
        department = DepartmentFactory()
        department.agents.add(user)

        result = ApiToken.create_token(
            user, "Expired",
            expires_at=timezone.now() - timedelta(days=1),
        )

        auth, _ = _make_middleware_pair()
        request = rf.get(
            "/api/test/",
            HTTP_AUTHORIZATION=f"Bearer {result['plain_text_token']}",
        )

        response = auth.process_view(request, None, [], {})
        assert response is not None
        assert response.status_code == 401
        data = json.loads(response.content)
        assert data["message"] == "Token has expired."

    def test_valid_token_sets_user_and_returns_none(self, rf):
        user = UserFactory(username="valid_mw")
        department = DepartmentFactory()
        department.agents.add(user)

        result = ApiToken.create_token(user, "Valid")

        auth, _ = _make_middleware_pair()
        request = rf.get(
            "/api/test/",
            HTTP_AUTHORIZATION=f"Bearer {result['plain_text_token']}",
        )

        response = auth.process_view(request, None, [], {})
        assert response is None  # Middleware passes through
        assert request.user == user
        assert request.api_token.pk == result["token"].pk

    def test_valid_token_updates_last_used(self, rf):
        user = UserFactory(username="used_mw")
        department = DepartmentFactory()
        department.agents.add(user)

        result = ApiToken.create_token(user, "Used")
        assert result["token"].last_used_at is None

        auth, _ = _make_middleware_pair()
        request = rf.get(
            "/api/test/",
            HTTP_AUTHORIZATION=f"Bearer {result['plain_text_token']}",
        )

        auth.process_view(request, None, [], {})

        result["token"].refresh_from_db()
        assert result["token"].last_used_at is not None

    def test_token_owner_deleted_returns_401(self, rf):
        user = UserFactory(username="deleted_owner")
        result = ApiToken.create_token(user, "Orphan")

        # Delete the user — the token remains in DB
        user.delete()

        auth, _ = _make_middleware_pair()
        request = rf.get(
            "/api/test/",
            HTTP_AUTHORIZATION=f"Bearer {result['plain_text_token']}",
        )

        response = auth.process_view(request, None, [], {})
        assert response is not None
        assert response.status_code == 401
        data = json.loads(response.content)
        assert data["message"] == "Token owner not found."


@pytest.mark.django_db
class TestApiRateLimit:
    def test_rate_limit_allows_requests_under_limit(self, rf):
        _, rate = _make_middleware_pair()
        user = UserFactory(username="rate_ok")
        token = ApiTokenFactory(user=user)

        request = rf.get("/api/test/")
        request.api_token = token

        # Should pass through (return None)
        response = rate.process_view(request, None, [], {})
        assert response is None

    @patch("escalated.api_middleware.get_setting")
    def test_rate_limit_blocks_when_exceeded(self, mock_setting, rf):
        mock_setting.return_value = 2  # Only 2 requests/min

        _, rate = _make_middleware_pair()
        user = UserFactory(username="rate_block")
        token = ApiTokenFactory(user=user)

        from django.core.cache import cache
        cache.clear()

        # Set cache to already have 2 hits
        cache.set(f"escalated_api:{token.pk}", 2, 60)

        request = rf.get("/api/test/")
        request.api_token = token

        response = rate.process_view(request, None, [], {})
        assert response is not None
        assert response.status_code == 429
        data = json.loads(response.content)
        assert data["message"] == "Too many requests."
        assert "Retry-After" in response

    def test_rate_limit_adds_headers_to_response(self, rf):
        _, rate = _make_middleware_pair()
        user = UserFactory(username="rate_headers")
        token = ApiTokenFactory(user=user)

        from django.core.cache import cache
        cache.clear()

        request = rf.get("/api/test/")
        request.api_token = token

        mock_response = MagicMock()
        mock_response.__setitem__ = MagicMock()
        mock_response.__getitem__ = MagicMock()

        result = rate.process_response(request, mock_response)
        # Should have set X-RateLimit-Limit and X-RateLimit-Remaining
        calls = {c[0][0] for c in mock_response.__setitem__.call_args_list}
        assert "X-RateLimit-Limit" in calls
        assert "X-RateLimit-Remaining" in calls
