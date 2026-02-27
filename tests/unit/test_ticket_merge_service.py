import pytest

from escalated.models import Ticket, Reply
from escalated.services.ticket_merge_service import TicketMergeService
from tests.factories import UserFactory, TicketFactory, ReplyFactory


@pytest.mark.django_db
class TestTicketMergeService:
    def setup_method(self):
        self.service = TicketMergeService()

    def test_moves_replies_to_target(self):
        source = TicketFactory()
        target = TicketFactory()
        user = UserFactory()
        r1 = ReplyFactory(ticket=source, author=user)
        r2 = ReplyFactory(ticket=source, author=user)

        self.service.merge(source, target)

        r1.refresh_from_db()
        r2.refresh_from_db()
        assert r1.ticket == target
        assert r2.ticket == target

    def test_closes_source_ticket(self):
        source = TicketFactory(status=Ticket.Status.OPEN)
        target = TicketFactory()

        self.service.merge(source, target)

        source.refresh_from_db()
        assert source.status == Ticket.Status.CLOSED

    def test_sets_merged_into_on_source(self):
        source = TicketFactory()
        target = TicketFactory()

        self.service.merge(source, target)

        source.refresh_from_db()
        assert source.merged_into == target

    def test_creates_system_note_on_target(self):
        source = TicketFactory()
        target = TicketFactory()

        self.service.merge(source, target)

        target_notes = Reply.objects.filter(ticket=target, is_internal_note=True)
        assert target_notes.count() >= 1
        note = target_notes.filter(body__contains="merged into this ticket").first()
        assert note is not None
        assert source.reference in note.body

    def test_creates_system_note_on_source(self):
        source = TicketFactory()
        target = TicketFactory()

        self.service.merge(source, target)

        source_notes = Reply.objects.filter(ticket=source, is_internal_note=True)
        assert source_notes.count() >= 1
        note = source_notes.filter(body__contains="was merged into").first()
        assert note is not None
        assert target.reference in note.body

    def test_system_notes_have_metadata(self):
        source = TicketFactory()
        target = TicketFactory()
        user = UserFactory()

        self.service.merge(source, target, merged_by_user_id=user.pk)

        target_note = Reply.objects.filter(
            ticket=target, is_internal_note=True,
            body__contains="merged into this ticket",
        ).first()

        assert target_note.metadata is not None
        assert target_note.metadata.get("system_note") is True
        assert target_note.metadata.get("merged_by") == user.pk

    def test_preserves_existing_target_replies(self):
        source = TicketFactory()
        target = TicketFactory()
        user = UserFactory()
        existing_reply = ReplyFactory(ticket=target, author=user)

        self.service.merge(source, target)

        existing_reply.refresh_from_db()
        assert existing_reply.ticket == target

    def test_source_with_no_replies(self):
        source = TicketFactory()
        target = TicketFactory()

        # Should not raise
        self.service.merge(source, target)

        source.refresh_from_db()
        assert source.status == Ticket.Status.CLOSED
        assert source.merged_into == target
