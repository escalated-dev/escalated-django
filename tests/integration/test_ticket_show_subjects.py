"""The agent and admin ticket pages send ``ticket.subjects`` as the API does,
so the sidebar's Related card appears (B1, ecom-core 2026-11-24)."""

import pytest
from django.urls import reverse

from escalated.api_serializers import ApiTicketDetailSerializer
from escalated.models import Tag
from tests.factories import TagFactory, TicketFactory

pytestmark = pytest.mark.django_db

TAG_TYPE = "escalated.Tag"


@pytest.fixture
def linked_ticket(settings):
    settings.ESCALATED = {**settings.ESCALATED, "TICKET_SUBJECT_TYPES": [TAG_TYPE]}
    ticket = TicketFactory()
    ticket.attach_subject(TagFactory(name="Order 1001"), role="order")
    return ticket


def _subjects(client, user, url):
    client.force_login(user)
    response = client.get(url, HTTP_X_INERTIA="true")
    assert response.status_code == 200, response.content[:500]
    return response.json()["props"]["ticket"]["subjects"]


@pytest.mark.parametrize(
    ("url_name", "who"),
    [("escalated:agent_ticket_show", "agent_user"), ("escalated:admin_tickets_show", "admin_user")],
)
def test_ticket_page_sends_subjects_as_the_api_does(client, request, linked_ticket, url_name, who):
    user = request.getfixturevalue(who)
    if who == "agent_user":
        linked_ticket.department = user.escalated_departments.first()
        linked_ticket.save()

    subjects = _subjects(client, user, reverse(url_name, args=[linked_ticket.pk]))

    assert subjects == ApiTicketDetailSerializer.serialize(linked_ticket)["subjects"]
    assert subjects[0]["type"] == TAG_TYPE
    assert subjects[0]["role"] == "order"
    assert subjects[0]["id"] == str(Tag.objects.get(name="Order 1001").pk)
