import pytest

from escalated.models import Reply, Ticket, TicketActivity, TicketLink
from escalated.services.ticket_split_service import TicketSplitService
from tests.factories import ReplyFactory, TicketFactory, UserFactory


@pytest.mark.django_db
class TestTicketSplitService:
    def setup_method(self):
        self.service = TicketSplitService()

    def test_creates_new_ticket_from_reply(self):
        source = TicketFactory()
        user = UserFactory()
        reply = ReplyFactory(ticket=source, author=user, body="Split this content")

        new_ticket = self.service.split_ticket(source, reply, {})

        assert new_ticket.pk is not None
        assert new_ticket.pk != source.pk
        assert new_ticket.description == "Split this content"
        assert new_ticket.status == Ticket.Status.OPEN

    def test_copies_metadata_from_source(self):
        source = TicketFactory(priority=Ticket.Priority.HIGH, channel="email")
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {})

        assert new_ticket.priority == Ticket.Priority.HIGH
        assert new_ticket.channel == "email"
        assert new_ticket.ticket_type == source.ticket_type

    def test_copies_requester_from_source(self):
        user = UserFactory()
        source = TicketFactory(requester=user)
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {})

        assert new_ticket.requester_content_type == source.requester_content_type
        assert new_ticket.requester_object_id == source.requester_object_id

    def test_uses_subject_override(self):
        source = TicketFactory()
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {"subject": "Custom subject"})

        assert new_ticket.subject == "Custom subject"

    def test_default_subject_includes_source_reference(self):
        source = TicketFactory()
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {})

        assert source.reference in new_ticket.subject

    def test_uses_priority_override(self):
        source = TicketFactory(priority=Ticket.Priority.LOW)
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {"priority": Ticket.Priority.URGENT})

        assert new_ticket.priority == Ticket.Priority.URGENT

    def test_links_tickets(self):
        source = TicketFactory()
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {})

        link = TicketLink.objects.get(parent_ticket=source, child_ticket=new_ticket)
        assert link.link_type == TicketLink.LinkType.RELATED

    def test_creates_system_note_on_source(self):
        source = TicketFactory()
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {})

        notes = Reply.objects.filter(ticket=source, is_internal_note=True)
        note = notes.filter(body__contains="split into new ticket").first()
        assert note is not None
        assert new_ticket.reference in note.body

    def test_creates_system_note_on_new_ticket(self):
        source = TicketFactory()
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {})

        notes = Reply.objects.filter(ticket=new_ticket, is_internal_note=True)
        note = notes.filter(body__contains="split from").first()
        assert note is not None
        assert source.reference in note.body

    def test_system_notes_have_metadata(self):
        source = TicketFactory()
        reply = ReplyFactory(ticket=source)
        user = UserFactory()

        new_ticket = self.service.split_ticket(source, reply, {}, split_by_user_id=user.pk)

        source_note = Reply.objects.filter(
            ticket=source,
            is_internal_note=True,
            body__contains="split into new ticket",
        ).first()

        assert source_note.metadata is not None
        assert source_note.metadata.get("system_note") is True
        assert source_note.metadata.get("split_by") == user.pk
        assert source_note.metadata.get("split_target") == new_ticket.reference

    def test_logs_activity_on_source(self):
        source = TicketFactory()
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {})

        activity = TicketActivity.objects.filter(ticket=source).first()
        assert activity is not None
        assert activity.properties.get("action") == "split"
        assert activity.properties.get("new_ticket_reference") == new_ticket.reference

    def test_logs_activity_on_new_ticket(self):
        source = TicketFactory()
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {})

        activity = TicketActivity.objects.filter(ticket=new_ticket).first()
        assert activity is not None
        assert activity.properties.get("action") == "split_from"
        assert activity.properties.get("source_ticket_reference") == source.reference

    def test_copies_tags_from_source(self):
        from tests.factories import TagFactory

        source = TicketFactory()
        tag1 = TagFactory()
        tag2 = TagFactory()
        source.tags.add(tag1, tag2)
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {})

        assert set(new_ticket.tags.values_list("pk", flat=True)) == {tag1.pk, tag2.pk}

    def test_copies_department_from_source(self):
        from tests.factories import DepartmentFactory

        dept = DepartmentFactory()
        source = TicketFactory(department=dept)
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {})

        assert new_ticket.department_id == dept.pk

    def test_department_override(self):
        from tests.factories import DepartmentFactory

        dept1 = DepartmentFactory()
        dept2 = DepartmentFactory()
        source = TicketFactory(department=dept1)
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {"department_id": dept2.pk})

        assert new_ticket.department_id == dept2.pk

    def test_new_ticket_has_unique_reference(self):
        source = TicketFactory()
        reply = ReplyFactory(ticket=source)

        new_ticket = self.service.split_ticket(source, reply, {})

        assert new_ticket.reference != source.reference
        assert new_ticket.reference is not None
