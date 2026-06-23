import pytest

from escalated.services.newsletter.bounce_suppression_store import BounceSuppressionStore


@pytest.mark.django_db
class TestBounceSuppressionStore:
    def test_case_insensitive(self):
        store = BounceSuppressionStore()
        store.mark_bounced("USER@Example.com")
        assert store.is_bounced("user@example.com")
        assert store.filter_sendable(["user@example.com", "ok@example.com"]) == ["ok@example.com"]
