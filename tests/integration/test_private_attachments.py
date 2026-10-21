"""Private attachment delivery: signed, expiring, access-checked downloads.

Serialized attachments link to the package's download view, never to MEDIA.
"""

import json
from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.test import Client, override_settings

from escalated.models import ApiToken, Attachment, Department
from tests.factories import ReplyFactory, TicketFactory, UserFactory

INERTIA = {"HTTP_X_INERTIA": "true"}


@pytest.fixture(autouse=True)
def media_root(tmp_path):
    with override_settings(MEDIA_ROOT=str(tmp_path), MEDIA_URL="/media/"):
        yield tmp_path


def attach(parent, name="report.txt", content=b"hello", mime="text/plain"):
    return Attachment.objects.create(
        content_type=ContentType.objects.get_for_model(parent),
        object_id=parent.pk,
        file=ContentFile(content, name=name),
        original_filename=name,
        mime_type=mime,
        size=len(content),
    )


def client_for(user=None):
    client = Client()
    if user is not None:
        client.force_login(user)
    return client


def make_agent():
    agent = UserFactory()
    department = Department.objects.create(name="Support", slug="support-att", is_active=True)
    department.agents.add(agent)
    return agent


def link(attachment, guest_ticket=None):
    from escalated import attachment_access

    if guest_ticket is None:
        return attachment_access.download_url(attachment)
    with attachment_access.for_guest(guest_ticket):
        return attachment_access.download_url(attachment)


def body(response):
    return b"".join(response.streaming_content)


@pytest.mark.django_db
class TestSerializedLinks:
    def test_customer_page_links_to_the_download_view_not_media(self):
        requester = UserFactory()
        ticket = TicketFactory(requester=requester)
        attachment = attach(ticket)

        response = client_for(requester).get(f"/support/tickets/{ticket.pk}/", **INERTIA)
        props = json.loads(response.content)["props"]
        url = props["ticket"]["attachments"][0]["url"]
        assert url.startswith(f"/support/attachments/{attachment.pk}/?token=")
        assert "/media/" not in json.dumps(props)

    def test_api_serializer_links_to_the_download_view(self):
        from escalated.api_serializers import ApiAttachmentSerializer

        attachment = attach(TicketFactory())
        assert ApiAttachmentSerializer.serialize(attachment)["url"].startswith(
            f"/support/attachments/{attachment.pk}/?token="
        )


@pytest.mark.django_db
class TestDownload:
    def test_agent_downloads_with_private_download_headers(self):
        attachment = attach(TicketFactory(), name="notes.txt", content=b"secret notes")
        response = client_for(make_agent()).get(link(attachment))

        assert response.status_code == 200
        assert body(response) == b"secret notes"
        assert response["Content-Disposition"].startswith("attachment;")
        assert 'filename="notes.txt"' in response["Content-Disposition"]
        assert response["X-Content-Type-Options"] == "nosniff"
        assert "private" in response["Cache-Control"] and "no-store" in response["Cache-Control"]
        assert response["Content-Type"].startswith("text/plain")

    def test_unsafe_types_are_sent_as_octet_stream(self):
        attachment = attach(TicketFactory(), name="page.html", content=b"<script>x</script>", mime="text/html")
        response = client_for(make_agent()).get(link(attachment))
        assert response.status_code == 200
        assert response["Content-Type"] == "application/octet-stream"

    def test_filename_is_reduced_to_a_safe_basename(self):
        attachment = attach(TicketFactory(), name="report.txt")
        attachment.original_filename = '..\\..\\evil\r\n".txt'
        attachment.save()
        response = client_for(make_agent()).get(link(attachment))
        disposition = response["Content-Disposition"]
        assert "\r" not in disposition and "\n" not in disposition
        assert ".." not in disposition and "\\" not in disposition

    def test_requester_downloads_ticket_and_public_reply_attachments(self):
        requester = UserFactory()
        ticket = TicketFactory(requester=requester)
        on_ticket = attach(ticket)
        on_reply = attach(ReplyFactory(ticket=ticket, is_internal_note=False))
        client = client_for(requester)
        assert client.get(link(on_ticket)).status_code == 200
        assert client.get(link(on_reply)).status_code == 200

    def test_requester_never_gets_an_internal_note_attachment(self):
        requester = UserFactory()
        ticket = TicketFactory(requester=requester)
        on_note = attach(ReplyFactory(ticket=ticket, is_internal_note=True))
        assert client_for(requester).get(link(on_note)).status_code == 403
        assert client_for(make_agent()).get(link(on_note)).status_code == 200

    def test_other_customers_and_anonymous_visitors_are_refused(self):
        attachment = attach(TicketFactory(requester=UserFactory()))
        assert client_for(UserFactory()).get(link(attachment)).status_code == 403
        assert client_for().get(link(attachment)).status_code == 403

    def test_a_missing_tampered_or_mismatched_token_is_refused(self):
        attachment = attach(TicketFactory())
        other = attach(TicketFactory())
        agent = make_agent()
        client = client_for(agent)
        assert client.get(f"/support/attachments/{attachment.pk}/").status_code == 403
        assert client.get(link(attachment) + "x").status_code == 403
        token = link(other).split("token=")[1]
        assert client.get(f"/support/attachments/{attachment.pk}/?token={token}").status_code == 403

    def test_links_expire(self):
        attachment = attach(TicketFactory())
        url = link(attachment)
        import time

        later = time.time() + 11 * 60
        with patch("django.core.signing.time.time", return_value=later):
            response = client_for(make_agent()).get(url)
        assert response.status_code == 403

    def test_a_missing_file_is_404(self, media_root):
        attachment = attach(TicketFactory())
        attachment.file.delete(save=False)
        assert client_for(make_agent()).get(link(attachment)).status_code == 404


@pytest.mark.django_db
class TestGuests:
    def guest_ticket(self):
        return TicketFactory(guest_name="G", guest_email="g@example.com", guest_token="a" * 64)

    def test_guest_page_links_download_without_a_session(self):
        ticket = self.guest_ticket()
        attach(ticket)
        with override_settings(ESCALATED={"UI_ENABLED": True}):
            response = Client().get(f"/support/guest/{ticket.guest_token}/", **INERTIA)
        props = json.loads(response.content)["props"]
        url = props["attachments"][0]["url"]
        download = Client().get(url)
        assert download.status_code == 200
        assert body(download) == b"hello"

    def test_rotating_the_guest_credential_revokes_issued_links(self):
        ticket = self.guest_ticket()
        url = link(attach(ticket), guest_ticket=ticket)
        assert Client().get(url).status_code == 200
        ticket.guest_token = "b" * 64
        ticket.save(update_fields=["guest_token"])
        assert Client().get(url).status_code == 403

    def test_a_guest_link_never_covers_internal_notes_or_other_tickets(self):
        ticket = self.guest_ticket()
        on_note = attach(ReplyFactory(ticket=ticket, is_internal_note=True))
        assert Client().get(link(on_note, guest_ticket=ticket)).status_code == 403
        other = attach(TicketFactory(guest_token="c" * 64))
        assert Client().get(link(other, guest_ticket=ticket)).status_code == 403


@pytest.mark.django_db
class TestBearerTokens:
    def test_requester_token_downloads(self):
        requester = UserFactory()
        attachment = attach(TicketFactory(requester=requester))
        plain = ApiToken.create_token(requester, "mobile")["plain_text_token"]
        response = Client().get(link(attachment), HTTP_AUTHORIZATION=f"Bearer {plain}")
        assert response.status_code == 200, response.content

    def test_an_invalid_bearer_token_never_falls_back_to_the_session(self):
        attachment = attach(TicketFactory())
        response = client_for(make_agent()).get(link(attachment), HTTP_AUTHORIZATION="Bearer nope")
        assert response.status_code == 401
