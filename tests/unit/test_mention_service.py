import pytest

from escalated.services.mention_service import MentionService


@pytest.mark.django_db
class TestMentionService:
    def setup_method(self):
        self.service = MentionService()

    def test_extract_single_mention(self):
        result = self.service.extract_mentions("Hello @john please review")
        assert result == ["john"]

    def test_extract_multiple_mentions(self):
        result = self.service.extract_mentions("@alice and @bob please check")
        assert set(result) == {"alice", "bob"}

    def test_extract_dotted_username(self):
        result = self.service.extract_mentions("cc @john.doe")
        assert result == ["john.doe"]

    def test_extract_deduplicates(self):
        result = self.service.extract_mentions("@alice said @alice should review")
        assert result == ["alice"]

    def test_extract_empty_for_none(self):
        assert self.service.extract_mentions(None) == []

    def test_extract_empty_for_no_mentions(self):
        assert self.service.extract_mentions("No mentions here") == []

    def test_search_agents_returns_list(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username="testuser", email="test@example.com", password="pass")
        results = self.service.search_agents("test")
        assert len(results) >= 1
        assert results[0]["id"] == user.pk

    def test_search_agents_empty_query(self):
        assert self.service.search_agents("") == []

    def test_search_agents_no_match(self):
        assert self.service.search_agents("zzzznonexistent") == []

    def test_unread_mentions(self):
        from django.contrib.auth import get_user_model

        from escalated.mention_models import Mention
        from escalated.models import Reply, Ticket

        User = get_user_model()
        user = User.objects.create_user(username="agent1", email="agent@test.com", password="pass")
        ticket = Ticket.objects.create(subject="Test", description="Test desc", status="open", priority="medium")
        reply = Reply.objects.create(ticket=ticket, body="test @agent1", is_internal_note=False)
        Mention.objects.create(reply=reply, user=user)

        unread = self.service.unread_mentions(user.pk)
        assert unread.count() == 1

    def test_mark_as_read(self):
        from django.contrib.auth import get_user_model

        from escalated.mention_models import Mention
        from escalated.models import Reply, Ticket

        User = get_user_model()
        user = User.objects.create_user(username="agent2", email="agent2@test.com", password="pass")
        ticket = Ticket.objects.create(subject="Test", description="Test desc", status="open", priority="medium")
        reply = Reply.objects.create(ticket=ticket, body="test", is_internal_note=False)
        mention = Mention.objects.create(reply=reply, user=user)

        self.service.mark_as_read([mention.id], user.pk)
        mention.refresh_from_db()
        assert mention.read_at is not None
