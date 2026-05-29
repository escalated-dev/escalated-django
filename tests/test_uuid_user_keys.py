import pytest

from escalated.models import Contact
from tests.factories import ContactFactory, TicketFactory


@pytest.mark.django_db
class TestUuidUserKeys:
    def test_contact_user_id_persists_string(self):
        contact = ContactFactory(user_id=None)
        uuid_user_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        contact.user_id = uuid_user_id
        contact.save(update_fields=["user_id", "updated_at"])
        contact.refresh_from_db()
        assert contact.user_id == uuid_user_id
        assert isinstance(contact.user_id, str)

    def test_ticket_requester_object_id_persists_string(self):
        ticket = TicketFactory()
        string_requester_id = "host-user-uuid-42"
        ticket.requester_object_id = string_requester_id
        ticket.save(update_fields=["requester_object_id"])
        ticket.refresh_from_db()
        assert ticket.requester_object_id == string_requester_id
        assert isinstance(ticket.requester_object_id, str)

    def test_contact_create_with_string_user_id(self):
        contact = Contact.objects.create(
            email="uuid-link@example.com",
            user_id="550e8400-e29b-41d4-a716-446655440000",
            metadata={},
        )
        contact.refresh_from_db()
        assert contact.user_id == "550e8400-e29b-41d4-a716-446655440000"
