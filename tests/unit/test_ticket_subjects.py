"""Ticket subjects — host entities a ticket is *about*."""

import json

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import override_settings

from escalated.models import Tag, TicketSubject
from escalated.serializers import TicketSerializer
from escalated.ticket_subjects import resolve_allowed_model_class, serialize_ticket_subject_link
from tests.factories import TagFactory, TicketFactory

TAG_TYPE = "escalated.Tag"


@pytest.fixture
def allow_tags(settings):
    settings.ESCALATED = {
        **settings.ESCALATED,
        "TICKET_SUBJECT_TYPES": [TAG_TYPE],
    }


@pytest.mark.django_db
class TestTicketSubjectModel:
    def test_attach_preserves_string_object_id(self, allow_tags):
        ticket = TicketFactory()
        tag_ct = ContentType.objects.get_for_model(Tag)
        link = TicketSubject.objects.create(
            ticket=ticket,
            content_type=tag_ct,
            object_id="prj_9f1c",
            role="project",
        )

        assert link.object_id == "prj_9f1c"
        assert link.role == "project"

    def test_attach_subject_idempotent_and_updates_role(self, allow_tags):
        ticket = TicketFactory()
        tag = TagFactory()

        ticket.attach_subject(tag)
        ticket.attach_subject(tag, role="account")

        assert ticket.subjects.count() == 1
        assert ticket.subjects.first().role == "account"

    def test_detach_subject(self, allow_tags):
        ticket = TicketFactory()
        tag = TagFactory()
        ticket.attach_subject(tag)

        assert ticket.detach_subject(tag) == 1
        assert ticket.subjects.count() == 0

    def test_sync_subjects_replaces_and_orders(self, allow_tags):
        ticket = TicketFactory()
        a = TagFactory(slug="a")
        b = TagFactory(slug="b")
        c = TagFactory(slug="c")

        ticket.attach_subject(a)
        ticket.sync_subjects([(b, "primary"), c])

        links = list(ticket.subjects.all())
        assert len(links) == 2
        assert links[0].object_id == str(b.pk)
        assert links[0].role == "primary"
        assert links[0].position == 0
        assert links[1].object_id == str(c.pk)
        assert links[1].position == 1

    def test_rejects_type_outside_allowlist(self, settings):
        settings.ESCALATED = {
            **settings.ESCALATED,
            "TICKET_SUBJECT_TYPES": ["auth.User"],
        }
        ticket = TicketFactory()
        tag = TagFactory()

        with pytest.raises(ValueError, match="not an allowed ticket subject"):
            ticket.attach_subject(tag)

    @override_settings(ESCALATED={"TICKET_SUBJECT_TYPES": []})
    def test_allows_any_model_when_allowlist_empty(self, settings):
        settings.ESCALATED = {**settings.ESCALATED, "TICKET_SUBJECT_TYPES": []}
        ticket = TicketFactory()
        tag = TagFactory()

        link = ticket.attach_subject(tag)
        assert isinstance(link, TicketSubject)


@pytest.mark.django_db
class TestTicketSubjectSerialization:
    def test_serializes_name_fallback(self, allow_tags):
        ticket = TicketFactory()
        tag = TagFactory(name="Billing", slug="billing")
        ticket.attach_subject(tag, role="topic")

        data = TicketSerializer.serialize(ticket)

        assert data["subjects"][0]["title"] == "Billing"
        assert data["subjects"][0]["type"] == TAG_TYPE
        assert data["subjects"][0]["missing"] is False

    def test_serializes_presentation_contract(self, allow_tags):
        from unittest.mock import PropertyMock, patch

        ticket = TicketFactory()
        tag = TagFactory(name="Billing", slug="billing")
        link = ticket.attach_subject(tag, role="topic")

        presenter = type(
            "Presenter",
            (),
            {
                "_meta": tag._meta,
                "ticket_subject_title": lambda self: "Billing",
                "ticket_subject_subtitle": lambda self: "Topic · billing",
                "ticket_subject_url": lambda self: "https://app.test/tags/billing",
                "ticket_subject_color": lambda self: "#2563eb",
                "ticket_subject_icon": lambda self: "tag",
            },
        )()

        with patch.object(type(link), "subject", new_callable=PropertyMock, return_value=presenter):
            payload = serialize_ticket_subject_link(link)

        assert payload["subtitle"] == "Topic · billing"
        assert payload["url"] == "https://app.test/tags/billing"
        assert payload["color"] == "#2563eb"
        assert payload["icon"] == "tag"

    def test_missing_subject_graceful_fallback(self, allow_tags):
        ticket = TicketFactory()
        tag = TagFactory()
        link = ticket.attach_subject(tag)
        tag_id = tag.pk
        tag.delete()

        payload = serialize_ticket_subject_link(TicketSubject.objects.get(pk=link.pk))

        assert payload["missing"] is True
        assert payload["id"] == str(tag_id)
        assert str(tag_id) in payload["title"]


@pytest.mark.django_db
class TestTicketSubjectAllowlistResolution:
    def test_resolve_allowed_model_class(self, allow_tags):
        model_class = resolve_allowed_model_class(TAG_TYPE)
        assert model_class is Tag

    def test_resolve_rejects_unknown_type(self, allow_tags):
        with pytest.raises(ValidationError):
            resolve_allowed_model_class("auth.NotAllowed")

    def test_resolve_rejects_when_allowlist_empty(self, settings):
        settings.ESCALATED = {**settings.ESCALATED, "TICKET_SUBJECT_TYPES": []}
        with pytest.raises(ValidationError):
            resolve_allowed_model_class(TAG_TYPE)


@pytest.mark.django_db
class TestTicketSubjectApi:
    def test_api_attach_and_detach(self, rf, settings):
        from escalated.views import api
        from tests.factories import ApiTokenFactory, DepartmentFactory, UserFactory
        from tests.integration.test_api_views import _api_post

        settings.ESCALATED = {**settings.ESCALATED, "TICKET_SUBJECT_TYPES": [TAG_TYPE]}

        user = UserFactory(username="subj_agent")
        department = DepartmentFactory()
        department.agents.add(user)
        token = ApiTokenFactory(user=user, abilities=["tickets:update"])

        ticket = TicketFactory()
        tag = TagFactory(name="Billing", slug="billing")

        request = _api_post(
            rf,
            f"/api/tickets/{ticket.reference}/subjects/",
            user,
            token,
            {"type": TAG_TYPE, "id": tag.pk, "role": "topic"},
        )
        response = api.ticket_subjects_store(request, ticket.reference)
        assert response.status_code == 200
        link_id = json.loads(response.content)["id"]
        assert ticket.subjects.count() == 1
        assert TicketSubject.objects.filter(pk=link_id, object_id=str(tag.pk)).exists()

        request = rf.delete(
            f"/api/tickets/{ticket.reference}/subjects/{link_id}/",
            HTTP_AUTHORIZATION=f"Bearer {token.plain_text}",
        )
        request.user = user
        request.api_token = token
        response = api.ticket_subjects_destroy(request, ticket.reference, link_id)
        assert response.status_code == 200
        assert ticket.subjects.count() == 0
