"""The shared widget's API contract.

Each test sends exactly the request ``EscalatedWidget.vue`` sends (paths without a
trailing slash, JSON bodies) and asserts the fields the widget reads.
"""

import json

import pytest
from django.core.cache import cache

from escalated import guest_access
from escalated.models import ChatSession, EscalatedSetting, Reply, Ticket
from escalated.services.chat_session_service import ChatSessionService
from tests.factories import ArticleCategoryFactory, ArticleFactory, DepartmentFactory, UserFactory
from tests.guest_proof import with_proof

pytestmark = pytest.mark.usefixtures("widget_on")

W = "/support/widget"
SHOP = "https://shop.example.com"


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()


def api(client, method, path, body=None, origin=None):
    """Send a request the way the widget's ``api()`` helper does."""
    headers = {"HTTP_ACCEPT": "application/json"}
    if origin:
        headers["HTTP_ORIGIN"] = origin
    if method == "GET":
        return client.get(f"{W}{path}", **headers)
    return client.post(
        f"{W}{path}",
        data=json.dumps(with_proof(f"{W}{path}", body)) if body is not None else "",
        content_type="application/json",
        **headers,
    )


def start_chat(client, **extra):
    response = api(client, "POST", "/chat/start", {"name": "Jane Doe", "email": "jane@example.com", **extra})
    assert response.status_code == 201, response.content
    return response.json()


@pytest.mark.django_db
class TestConfig:
    def test_returns_the_keys_the_widget_reads(self, client):
        sales = DepartmentFactory(name="Sales")
        DepartmentFactory(name="Closed", is_active=False)
        EscalatedSetting.set("widget_accent_color", "#ff0000")
        EscalatedSetting.set("widget_greeting", "Hello!")

        response = api(client, "GET", "/config")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["color"] == "#ff0000"
        assert data["greeting"] == "Hello!"
        assert data["position"] == "bottom-right"
        assert data["departments"] == [{"id": sales.pk, "name": "Sales"}]
        assert data["kb_enabled"] is True
        assert data["guest_tickets_enabled"] is True
        assert data["accepts_metadata"] is True
        # Mailbox-verified status lookup (docs/guest-access.md).
        assert data["status_lookup_enabled"] is True
        assert data["guest_verification_required"] is True

    def test_keeps_the_existing_keys(self, client):
        data = api(client, "GET", "/config").json()
        for key in ("widget_enabled", "widget_title", "widget_greeting", "widget_accent_color", "kb_search_enabled"):
            assert key in data

    def test_reflects_the_admin_switches(self, client):
        EscalatedSetting.set("widget_kb_search_enabled", "false")
        EscalatedSetting.set("widget_ticket_creation_enabled", "false")
        EscalatedSetting.set("widget_position", "bottom-left")

        data = api(client, "GET", "/config").json()

        assert data["kb_enabled"] is False
        assert data["guest_tickets_enabled"] is False
        assert data["position"] == "bottom-left"

    def test_disabled_widget_answers_enabled_false_with_403(self, client):
        EscalatedSetting.set("widget_enabled", "false")
        response = api(client, "GET", "/config")
        assert response.status_code == 403
        assert response.json()["enabled"] is False

    def test_the_trailing_slash_route_still_works(self, client):
        assert client.get(f"{W}/config/").json()["color"]


@pytest.mark.django_db
class TestArticles:
    def test_searches_articles(self, client):
        cat = ArticleCategoryFactory()
        ArticleFactory(category=cat, title="How to reset password", slug="reset", status="published")
        ArticleFactory(category=cat, title="Billing FAQ", status="published")

        response = api(client, "GET", "/articles?q=reset")

        assert response.status_code == 200
        articles = response.json()["articles"]
        assert [a["slug"] for a in articles] == ["reset"]
        assert set(articles[0]) >= {"title", "slug", "excerpt"}

    def test_shows_an_article_by_slug_with_top_level_fields(self, client):
        cat = ArticleCategoryFactory(name="Accounts")
        article = ArticleFactory(
            category=cat, title="Reset", slug="reset-password", body="<p>Do it</p>", status="published"
        )

        response = api(client, "GET", "/articles/reset-password")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Reset"
        assert data["slug"] == "reset-password"
        assert data["body"] == "<p>Do it</p>"
        assert data["category"] == "Accounts"
        article.refresh_from_db()
        assert article.view_count == 1

    def test_hides_unpublished_and_unknown_articles(self, client):
        ArticleFactory(slug="draft-one", status="draft")
        assert api(client, "GET", "/articles/draft-one").status_code == 404
        assert api(client, "GET", "/articles/missing").status_code == 404

    def test_the_old_id_route_still_works(self, client):
        article = ArticleFactory(status="published")
        assert client.get(f"{W}/articles/{article.pk}/").json()["article"]["slug"] == article.slug


@pytest.mark.django_db
class TestTickets:
    def payload(self, **extra):
        return {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "subject": "Where is my order?",
            "description": "It has not arrived yet.",
            "department_id": None,
            **extra,
        }

    def test_creates_a_ticket_with_a_top_level_reference(self, client):
        response = api(client, "POST", "/tickets", self.payload())

        assert response.status_code == 201
        data = response.json()
        ticket = Ticket.objects.get(reference=data["reference"])
        assert data["message"]
        assert guest_access.resolve(data["guest_access_token"]) == ticket
        assert data["expires_at"]
        assert ticket.channel == "widget"

    def test_routes_to_the_chosen_department(self, client):
        support = DepartmentFactory()
        data = api(client, "POST", "/tickets", self.payload(department_id=support.pk)).json()
        assert Ticket.objects.get(reference=data["reference"]).department == support

    @pytest.mark.parametrize("department", ["inactive", "missing"])
    def test_rejects_an_unknown_department(self, client, department):
        dept_id = DepartmentFactory(is_active=False).pk if department == "inactive" else 99999
        response = api(client, "POST", "/tickets", self.payload(department_id=dept_id))
        assert response.status_code == 422
        assert "department_id" in response.json()["errors"]

    def test_validation_errors_use_message_and_field_lists(self, client):
        response = api(client, "POST", "/tickets", self.payload(subject="", description=""))

        assert response.status_code == 422
        data = response.json()
        assert data["message"]
        assert isinstance(data["errors"]["subject"], list)
        assert isinstance(data["errors"]["description"], list)

    def test_works_cross_origin_with_cors(self, client, settings):
        settings.ESCALATED = {**settings.ESCALATED, "WIDGET_ALLOWED_ORIGINS": [SHOP]}
        response = api(client, "POST", "/tickets", self.payload(), origin=SHOP)
        assert response.status_code == 201
        assert response["Access-Control-Allow-Origin"] == SHOP

    def test_the_old_create_route_keeps_its_shape(self, client):
        body = with_proof(f"{W}/tickets/create/", self.payload())
        response = client.post(f"{W}/tickets/create/", data=json.dumps(body), content_type="application/json")
        assert response.status_code == 200
        assert response.json()["ticket"]["reference"]

    def test_has_no_email_based_status_lookup(self, client):
        ticket = api(client, "POST", "/tickets", self.payload()).json()
        response = client.get(f"{W}/tickets/{ticket['reference']}?email=jane@example.com")
        assert response.status_code == 404


@pytest.mark.django_db
class TestChat:
    def test_availability(self, client):
        response = api(client, "GET", "/chat/availability")
        assert response.status_code == 200
        assert response.json()["available"] is False

    def test_start_returns_an_unguessable_id(self, client):
        dept = DepartmentFactory()
        data = start_chat(client, department_id=dept.pk, message="Hi there")

        assert len(data["id"]) >= 32
        assert data["status"] == "waiting"
        session = ChatSession.objects.get(customer_session_id=data["id"])
        assert session.ticket.department == dept
        assert [m["body"] for m in data["messages"]] == ["Hi there"]
        assert data["agent"] is None

    def test_start_validates_with_422(self, client):
        response = api(client, "POST", "/chat/start", {"name": "", "email": ""})
        assert response.status_code == 422
        assert isinstance(response.json()["errors"]["email"], list)

    def test_the_guest_sends_and_reads_messages(self, client):
        chat = start_chat(client)

        assert api(client, "POST", f"/chat/{chat['id']}/messages", {"body": "Hello"}).status_code == 200

        session = ChatSession.objects.get(customer_session_id=chat["id"])
        agent = UserFactory(first_name="Sam", last_name="Agent")
        ChatSessionService().assign_agent(session, agent)
        ChatSessionService().send_message(session, body="How can I help?", sender=agent, sender_type="agent")
        Reply.objects.create(ticket=session.ticket, author=agent, body="secret", is_internal_note=True)
        ChatSessionService().update_typing(session, is_typing=True, sender_type="agent")

        data = api(client, "GET", f"/chat/{chat['id']}/messages").json()

        assert [(m["body"], m["is_agent"], m["author"]["name"]) for m in data["messages"]] == [
            ("Hello", False, "Jane Doe"),
            ("How can I help?", True, "Sam Agent"),
        ]
        assert all({"id", "created_at"} <= set(m) for m in data["messages"])
        assert data["agent"] == {"name": "Sam Agent"}
        # The widget renders `typing` as text ("{{ typing }} is typing...").
        assert data["typing"] == "Sam Agent"
        assert data["ended"] is False

    def test_rejects_an_empty_message(self, client):
        chat = start_chat(client)
        assert api(client, "POST", f"/chat/{chat['id']}/messages", {"body": " "}).status_code == 422

    def test_typing_end_and_rate(self, client):
        chat = start_chat(client)

        assert api(client, "POST", f"/chat/{chat['id']}/typing").status_code == 200
        session = ChatSession.objects.get(customer_session_id=chat["id"])
        assert session.customer_typing_at is not None

        assert api(client, "POST", f"/chat/{chat['id']}/end").status_code == 200
        assert api(client, "GET", f"/chat/{chat['id']}/messages").json()["ended"] is True
        assert api(client, "POST", f"/chat/{chat['id']}/messages", {"body": "late"}).status_code == 422

        response = api(client, "POST", f"/chat/{chat['id']}/rate", {"rating": 5, "comment": "Great"})
        assert response.status_code == 200
        session.refresh_from_db()
        assert (session.rating, session.rating_comment) == (5, "Great")

    def test_rejects_a_bad_rating(self, client):
        chat = start_chat(client)
        api(client, "POST", f"/chat/{chat['id']}/end")
        assert api(client, "POST", f"/chat/{chat['id']}/rate", {"rating": 9}).status_code == 422

    @pytest.mark.parametrize("suffix", ["messages", "typing", "end", "rate"])
    def test_unknown_session_tokens_get_404(self, client, suffix):
        session = start_chat(client)
        unknown = "0" * 32
        method = "GET" if suffix == "messages" else "POST"
        assert api(client, method, f"/chat/{unknown}/{suffix}", {"rating": 5}).status_code == 404
        # The numeric primary key is not a valid token either.
        pk = ChatSession.objects.get(customer_session_id=session["id"]).pk
        assert api(client, method, f"/chat/{pk}/{suffix}", {"rating": 5}).status_code == 404

    def test_chat_routes_answer_allowed_sites_with_cors(self, client, settings):
        settings.ESCALATED = {**settings.ESCALATED, "WIDGET_ALLOWED_ORIGINS": [SHOP]}
        chat = start_chat(client)
        response = api(client, "GET", f"/chat/{chat['id']}/messages", origin=SHOP)
        assert response["Access-Control-Allow-Origin"] == SHOP

        preflight = client.options(
            f"{W}/chat/{chat['id']}/messages",
            HTTP_ORIGIN=SHOP,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        assert preflight.status_code == 204
        assert preflight["Access-Control-Allow-Origin"] == SHOP

    def test_the_old_session_id_routes_still_work(self, client):
        chat = start_chat(client)
        response = client.post(
            f"{W}/chat/message/",
            data=json.dumps({"session_id": chat["session_id"], "body": "Hello"}),
            content_type="application/json",
        )
        assert response.status_code == 200
