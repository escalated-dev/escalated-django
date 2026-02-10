"""
Unit tests for the ApiToken model.
"""

import hashlib
import secrets
from datetime import timedelta

import pytest
from django.utils import timezone

from escalated.models import ApiToken
from tests.factories import UserFactory, ApiTokenFactory


@pytest.mark.django_db
class TestApiTokenModel:
    def test_create_token_returns_model_and_plain_text(self):
        user = UserFactory(username="token_user")
        result = ApiToken.create_token(user, "My Token")

        assert "token" in result
        assert "plain_text_token" in result
        assert isinstance(result["token"], ApiToken)
        assert len(result["plain_text_token"]) == 64  # hex(32) = 64 chars

    def test_create_token_hashes_with_sha256(self):
        user = UserFactory(username="hash_user")
        result = ApiToken.create_token(user, "Hash Test")

        plain = result["plain_text_token"]
        expected_hash = hashlib.sha256(plain.encode()).hexdigest()
        assert result["token"].token == expected_hash

    def test_create_token_stores_abilities(self):
        user = UserFactory(username="abilities_user")
        result = ApiToken.create_token(user, "Abilities Test", abilities=["agent", "admin"])

        assert result["token"].abilities == ["agent", "admin"]

    def test_create_token_default_abilities_is_wildcard(self):
        user = UserFactory(username="default_abilities")
        result = ApiToken.create_token(user, "Default")

        assert result["token"].abilities == ["*"]

    def test_create_token_with_expiry(self):
        user = UserFactory(username="expiry_user")
        expires_at = timezone.now() + timedelta(days=30)
        result = ApiToken.create_token(user, "Expiry Test", expires_at=expires_at)

        assert result["token"].expires_at is not None
        assert result["token"].is_expired is False

    def test_find_by_plain_text_success(self):
        user = UserFactory(username="find_user")
        result = ApiToken.create_token(user, "Find Test")

        found = ApiToken.find_by_plain_text(result["plain_text_token"])
        assert found is not None
        assert found.pk == result["token"].pk

    def test_find_by_plain_text_returns_none_for_invalid(self):
        found = ApiToken.find_by_plain_text("nonexistent_token_value")
        assert found is None

    def test_has_ability_wildcard(self):
        user = UserFactory(username="wildcard_user")
        result = ApiToken.create_token(user, "Wildcard", abilities=["*"])

        assert result["token"].has_ability("agent") is True
        assert result["token"].has_ability("admin") is True
        assert result["token"].has_ability("anything") is True

    def test_has_ability_specific(self):
        user = UserFactory(username="specific_user")
        result = ApiToken.create_token(user, "Specific", abilities=["agent"])

        assert result["token"].has_ability("agent") is True
        assert result["token"].has_ability("admin") is False

    def test_has_ability_empty(self):
        user = UserFactory(username="empty_abilities")
        result = ApiToken.create_token(user, "Empty", abilities=[])

        assert result["token"].has_ability("agent") is False

    def test_is_expired_false_when_no_expiry(self):
        user = UserFactory(username="no_expiry")
        result = ApiToken.create_token(user, "No Expiry")

        assert result["token"].is_expired is False

    def test_is_expired_false_when_future_expiry(self):
        user = UserFactory(username="future_expiry")
        expires_at = timezone.now() + timedelta(days=30)
        result = ApiToken.create_token(user, "Future", expires_at=expires_at)

        assert result["token"].is_expired is False

    def test_is_expired_true_when_past_expiry(self):
        user = UserFactory(username="past_expiry")
        expires_at = timezone.now() - timedelta(days=1)
        result = ApiToken.create_token(user, "Past", expires_at=expires_at)

        assert result["token"].is_expired is True

    def test_active_queryset(self):
        user = UserFactory(username="qs_active")
        result_active = ApiToken.create_token(user, "Active")
        result_expired = ApiToken.create_token(
            user, "Expired",
            expires_at=timezone.now() - timedelta(days=1),
        )

        active = ApiToken.objects.active()
        assert result_active["token"] in active
        assert result_expired["token"] not in active

    def test_expired_queryset(self):
        user = UserFactory(username="qs_expired")
        result_active = ApiToken.create_token(user, "Active")
        result_expired = ApiToken.create_token(
            user, "Expired",
            expires_at=timezone.now() - timedelta(days=1),
        )

        expired = ApiToken.objects.expired()
        assert result_expired["token"] in expired
        assert result_active["token"] not in expired

    def test_tokenable_resolves_to_user(self):
        user = UserFactory(username="tokenable_user")
        result = ApiToken.create_token(user, "Tokenable Test")

        token = result["token"]
        assert token.tokenable == user
        assert token.tokenable.pk == user.pk

    def test_str_representation(self):
        user = UserFactory(username="str_user")
        result = ApiToken.create_token(user, "My Token Name")

        assert "My Token Name" in str(result["token"])
