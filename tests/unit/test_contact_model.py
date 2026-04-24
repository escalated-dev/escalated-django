import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError

from escalated.models import Contact, Ticket
from tests.factories import ContactFactory, TicketFactory


@pytest.mark.django_db
class TestContactBasics:
    def test_uses_escalated_contacts_table(self):
        assert Contact._meta.db_table == "escalated_contacts"

    def test_email_is_normalized_on_save(self):
        c = Contact.objects.create(email="  UPPER@Case.COM  ", metadata={})
        assert c.email == "upper@case.com"

    def test_email_is_unique(self):
        Contact.objects.create(email="alice@example.com", metadata={})
        with pytest.raises(IntegrityError):
            Contact.objects.create(email="alice@example.com", metadata={})


@pytest.mark.django_db
class TestFindOrCreateByEmail:
    def test_creates_new_contact(self):
        c = Contact.find_or_create_by_email("new@user.com", "New User")
        assert c.email == "new@user.com"
        assert c.name == "New User"

    def test_normalizes_case_and_whitespace_on_create(self):
        c = Contact.find_or_create_by_email("  MIX@Case.COM ")
        assert c.email == "mix@case.com"

    def test_returns_existing_for_repeat_email(self):
        first = Contact.find_or_create_by_email("alice@example.com", "Alice")
        second = Contact.find_or_create_by_email("ALICE@example.com")
        assert second.id == first.id

    def test_fills_in_blank_name_on_existing(self):
        Contact.objects.create(email="alice@example.com", name=None, metadata={})
        result = Contact.find_or_create_by_email("alice@example.com", "Alice")
        assert result.name == "Alice"

    def test_does_not_overwrite_existing_name(self):
        Contact.objects.create(email="alice@example.com", name="Alice", metadata={})
        result = Contact.find_or_create_by_email("alice@example.com", "Different")
        assert result.name == "Alice"


@pytest.mark.django_db
class TestLinkToUser:
    def test_sets_user_id(self):
        c = ContactFactory(user_id=None)
        c.link_to_user(555)
        c.refresh_from_db()
        assert c.user_id == 555


@pytest.mark.django_db
class TestPromoteToUser:
    def test_back_stamps_requester_on_prior_tickets(self):
        user = User.objects.create(username="alice", email="alice@example.com")
        contact = ContactFactory(user_id=None)
        t1 = TicketFactory(contact=contact)
        t2 = TicketFactory(contact=contact)
        user_ct = ContentType.objects.get_for_model(User)

        contact.promote_to_user(user.id, "auth.User")

        contact.refresh_from_db()
        assert contact.user_id == user.id
        for t in (t1, t2):
            t.refresh_from_db()
            assert t.requester_object_id == user.id
            assert t.requester_content_type_id == user_ct.id
