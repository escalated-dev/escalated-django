"""Cross-origin embedding of the widget: CORS, guest forcing, host metadata, embed.js."""

import json
from pathlib import Path

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import JsonResponse
from django.test import Client, RequestFactory

from escalated.models import ChatSession, EscalatedSetting, Ticket
from escalated.widget_embed import EMBED_SCRIPT_PATH, widget_cors
from tests.guest_proof import with_proof

pytestmark = pytest.mark.usefixtures("widget_on")

SHOP = "https://shop.example.com"
EVIL = "https://evil.example.net"

CONFIG = "/support/widget/config/"
CREATE = "/support/widget/tickets/create/"
CHAT_START = "/support/widget/chat/start/"
SCRIPT = "/support/widget/embed.js"
INERTIA = {"HTTP_X_INERTIA": "true"}


@pytest.fixture(autouse=True)
def allow_shop(settings):
    settings.ESCALATED = {**settings.ESCALATED, "WIDGET_ALLOWED_ORIGINS": [SHOP]}


def ticket_payload(**extra):
    return {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "subject": "Where is my order?",
        "description": "It has not arrived yet.",
        **extra,
    }


def post_json(client, url, data, origin=None):
    headers = {"HTTP_ORIGIN": origin} if origin else {}
    return client.post(url, data=json.dumps(with_proof(url, data)), content_type="application/json", **headers)


@pytest.mark.django_db
class TestPreflight:
    def test_answers_a_preflight_from_an_allowed_site(self, client):
        response = client.options(
            CREATE,
            HTTP_ORIGIN=SHOP,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,authorization",
        )

        assert response.status_code == 204
        assert response["Access-Control-Allow-Origin"] == SHOP
        assert response["Access-Control-Allow-Methods"] == "GET, POST, OPTIONS"
        assert "Content-Type" in response["Access-Control-Allow-Headers"]
        assert "Authorization" in response["Access-Control-Allow-Headers"]
        assert response["Access-Control-Max-Age"] == "600"
        assert "Origin" in response["Vary"]
        assert not response.has_header("Access-Control-Allow-Credentials")

    def test_answers_preflights_on_the_chat_routes(self, client):
        response = client.options(CHAT_START, HTTP_ORIGIN=SHOP, HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST")

        assert response.status_code == 204
        assert response["Access-Control-Allow-Origin"] == SHOP

    def test_gives_no_cors_grant_to_a_site_that_is_not_allowed(self, client):
        preflight = client.options(CREATE, HTTP_ORIGIN=EVIL, HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST")
        config = client.get(CONFIG, HTTP_ORIGIN=EVIL)

        assert preflight.status_code == 204
        assert not preflight.has_header("Access-Control-Allow-Origin")
        assert config.status_code == 200
        assert not config.has_header("Access-Control-Allow-Origin")


@pytest.mark.django_db
class TestCrossOriginRequests:
    def test_lets_an_allowed_site_create_a_ticket(self, client):
        response = post_json(client, CREATE, ticket_payload(), origin=SHOP)

        assert response.status_code == 200
        assert response["Access-Control-Allow-Origin"] == SHOP
        assert response["Access-Control-Expose-Headers"] == "Retry-After"
        assert "Origin" in response["Vary"]
        assert not response.has_header("Access-Control-Allow-Credentials")
        assert Ticket.objects.filter(subject="Where is my order?").exists()

    def test_an_allowed_site_needs_no_csrf_token_under_csrf_middleware(self, settings):
        settings.MIDDLEWARE = [*settings.MIDDLEWARE, "django.middleware.csrf.CsrfViewMiddleware"]
        client = Client(enforce_csrf_checks=True)

        response = post_json(client, CREATE, ticket_payload(), origin=SHOP)

        assert response.status_code == 200
        assert response["Access-Control-Allow-Origin"] == SHOP

    @pytest.mark.parametrize("origin", [EVIL, "http://testserver", None])
    def test_other_sites_and_same_origin_get_no_cors_headers(self, client, origin):
        response = post_json(client, CREATE, ticket_payload(), origin=origin)

        assert response.status_code == 200
        assert not response.has_header("Access-Control-Allow-Origin")
        assert not response.has_header("Access-Control-Expose-Headers")

    def test_reads_allowed_sites_from_the_admin_setting_including_wildcards(self, client, settings):
        settings.ESCALATED = {**settings.ESCALATED, "WIDGET_ALLOWED_ORIGINS": []}
        EscalatedSetting.set("widget_allowed_origins", "https://*.brand.test\nhttp://localhost:5173")

        def allowed(origin):
            return client.get(CONFIG, HTTP_ORIGIN=origin).get("Access-Control-Allow-Origin")

        assert allowed("https://help.brand.test") == "https://help.brand.test"
        assert allowed("https://a.b.brand.test") == "https://a.b.brand.test"
        assert allowed("http://localhost:5173") == "http://localhost:5173"
        assert allowed("https://brand.test") is None
        assert allowed("http://help.brand.test") is None
        assert allowed("https://evilbrand.test") is None
        assert allowed("http://localhost:5174") is None

    def test_adds_cors_headers_to_validation_answers(self, client):
        response = post_json(client, CREATE, {"name": "x"}, origin=SHOP)

        assert response.status_code == 400
        assert response["Access-Control-Allow-Origin"] == SHOP

    def test_adds_cors_headers_to_rate_limit_answers(self, client):
        EscalatedSetting.set("widget_rate_limit", "1")

        assert client.get(CONFIG, HTTP_ORIGIN=SHOP).status_code == 200
        limited = client.get(CONFIG, HTTP_ORIGIN=SHOP)

        assert limited.status_code == 429
        assert limited["Access-Control-Allow-Origin"] == SHOP
        assert "Retry-After" in limited["Access-Control-Expose-Headers"]

    def test_adds_cors_headers_to_guest_throttle_answers(self, client, settings):
        settings.ESCALATED = {
            **settings.ESCALATED,
            "GUEST_RATE_LIMIT": {"ENABLED": True, "TICKETS_PER_MINUTE": 1, "REPLIES_PER_MINUTE": 1},
        }

        post_json(client, CREATE, ticket_payload(), origin=SHOP)
        limited = post_json(client, CREATE, ticket_payload(), origin=SHOP)

        assert limited.status_code == 429
        assert limited.has_header("Retry-After")
        assert limited["Access-Control-Allow-Origin"] == SHOP

    def test_adds_cors_headers_when_the_widget_is_disabled(self, client):
        EscalatedSetting.set("widget_enabled", "0")

        response = client.get(CONFIG, HTTP_ORIGIN=SHOP)

        assert response.status_code == 403
        assert response["Access-Control-Allow-Origin"] == SHOP

    def test_appends_origin_to_an_existing_vary_header(self, rf):
        def view(request):
            response = JsonResponse({})
            response["Vary"] = "Accept-Language"
            return response

        response = widget_cors(view)(rf.get(CONFIG, HTTP_ORIGIN=SHOP))

        assert response["Vary"] == "Accept-Language, Origin"


@pytest.mark.django_db
class TestGuestForcing:
    @staticmethod
    def probe(request):
        return JsonResponse({"authenticated": request.user.is_authenticated})

    def test_an_embedded_visitor_is_a_guest_even_when_signed_in(self, admin_user):
        request = RequestFactory().get(CONFIG, HTTP_ORIGIN=SHOP)
        request.user = admin_user

        response = widget_cors(self.probe)(request)

        assert json.loads(response.content) == {"authenticated": False}
        assert isinstance(request.user, AnonymousUser)

    @pytest.mark.parametrize("origin", [EVIL, "http://testserver", None])
    def test_other_requests_keep_the_signed_in_user(self, admin_user, origin):
        extra = {"HTTP_ORIGIN": origin} if origin else {}
        request = RequestFactory().get(CONFIG, **extra)
        request.user = admin_user

        response = widget_cors(self.probe)(request)

        assert json.loads(response.content) == {"authenticated": True}


@pytest.mark.django_db
class TestConfig:
    def test_tells_the_widget_it_accepts_host_parameters(self, client):
        data = client.get(CONFIG).json()

        assert data["accepts_metadata"] is True
        for key in (
            "widget_enabled",
            "widget_title",
            "widget_greeting",
            "widget_accent_color",
            "kb_search_enabled",
            "ticket_creation_enabled",
        ):
            assert key in data


@pytest.mark.django_db
class TestTicketMetadata:
    def test_stores_sanitised_host_parameters(self, client):
        response = post_json(
            client,
            CREATE,
            ticket_payload(
                metadata={
                    "order_number": "A-1001",
                    "plan": " pro ",
                    "items": 3,
                    "ratio": 1.5,
                    "vip": True,
                    "page_url": "https://shop.example.com/orders/A-1001",
                    "embedded_on": "https://spoofed.example",
                    "nested": {"not": "kept"},
                    "list": [1, 2],
                    "empty": None,
                    "bad key!": "dropped",
                    "note": "a" * 600,
                }
            ),
            origin=SHOP,
        )

        assert response.status_code == 200
        metadata = Ticket.objects.get(reference=response.json()["ticket"]["reference"]).metadata
        assert metadata == {
            "order_number": "A-1001",
            "plan": "pro",
            "items": 3,
            "ratio": 1.5,
            "vip": True,
            "page_url": "https://shop.example.com/orders/A-1001",
            "note": "a" * 500,
            "embedded_on": SHOP,
        }

    def test_drops_a_page_url_that_is_not_a_web_address(self, client):
        response = post_json(
            client,
            CREATE,
            ticket_payload(metadata={"page_url": "javascript:alert(1)", "plan": "pro"}),
            origin=SHOP,
        )

        ticket = Ticket.objects.get(reference=response.json()["ticket"]["reference"])
        assert ticket.metadata == {"plan": "pro", "embedded_on": SHOP}

    def test_drops_an_overlong_page_url(self, client):
        response = post_json(
            client,
            CREATE,
            ticket_payload(metadata={"page_url": "https://shop.example.com/" + "a" * 2048}),
        )

        assert Ticket.objects.get(reference=response.json()["ticket"]["reference"]).metadata is None

    def test_keeps_at_most_25_entries(self, client):
        response = post_json(client, CREATE, ticket_payload(metadata={f"k{i:02d}": i for i in range(40)}))

        metadata = Ticket.objects.get(reference=response.json()["ticket"]["reference"]).metadata
        assert len(metadata) == 25
        assert "k00" in metadata and "k24" in metadata and "k25" not in metadata

    def test_same_origin_requests_cannot_set_embedded_on(self, client):
        response = post_json(client, CREATE, ticket_payload(metadata={"embedded_on": SHOP, "plan": "pro"}))

        ticket = Ticket.objects.get(reference=response.json()["ticket"]["reference"])
        assert ticket.metadata == {"plan": "pro"}

    def test_leaves_widget_tickets_without_host_parameters_unchanged(self, client):
        response = post_json(client, CREATE, ticket_payload())

        assert Ticket.objects.get(reference=response.json()["ticket"]["reference"]).metadata is None

    @pytest.mark.parametrize("metadata", ["a string", [1, 2], {f"k{i}": i for i in range(51)}])
    def test_rejects_metadata_that_is_not_a_small_object(self, client, metadata):
        response = post_json(client, CREATE, ticket_payload(metadata=metadata), origin=SHOP)

        assert response.status_code == 400
        assert "metadata" in response.json()["errors"]
        assert response["Access-Control-Allow-Origin"] == SHOP
        assert not Ticket.objects.exists()


@pytest.mark.django_db
class TestChatMetadata:
    def test_lets_an_allowed_site_start_a_chat_and_keeps_its_host_parameters(self, client):
        response = post_json(
            client,
            CHAT_START,
            {
                "name": "John Doe",
                "email": "john@example.com",
                "metadata": {"page_url": "https://shop.example.com/cart", "cart_total": 129.5, "deep": {"x": 1}},
            },
            origin=SHOP,
        )

        assert response.status_code == 200
        assert response["Access-Control-Allow-Origin"] == SHOP
        expected = {"page_url": "https://shop.example.com/cart", "cart_total": 129.5, "embedded_on": SHOP}
        ticket = Ticket.objects.get(reference=response.json()["ticket_reference"])
        assert ticket.chat_metadata == expected
        assert ChatSession.objects.get(ticket=ticket).metadata == expected

    def test_rejects_chat_metadata_that_is_not_an_object(self, client):
        response = post_json(
            client, CHAT_START, {"name": "John", "email": "john@example.com", "metadata": "x"}, origin=SHOP
        )

        assert response.status_code == 400
        assert "metadata" in response.json()["errors"]
        assert not ChatSession.objects.exists()


class TestEmbedScript:
    def test_serves_the_standalone_widget_script(self, client):
        response = client.get(SCRIPT)

        assert response.status_code == 200
        assert response["Content-Type"] == "application/javascript; charset=utf-8"
        assert response["Cache-Control"] == "public, max-age=3600"
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["Cross-Origin-Resource-Policy"] == "cross-origin"
        assert response["Access-Control-Allow-Origin"] == "*"
        assert response.content == Path(EMBED_SCRIPT_PATH).read_bytes()
        assert response.content

        cached = client.get(SCRIPT, HTTP_IF_NONE_MATCH=response["ETag"])
        assert cached.status_code == 304
        assert cached.content == b""

    def test_the_bundle_ships_with_the_package(self):
        package_dir = Path(__file__).resolve().parents[2] / "escalated"
        assert Path(EMBED_SCRIPT_PATH).resolve().is_relative_to(package_dir)
        assert Path(EMBED_SCRIPT_PATH).stat().st_size > 10_000


@pytest.mark.django_db
class TestAdminSetting:
    def _client(self, admin_user):
        client = Client()
        client.force_login(admin_user)
        return client

    def test_saves_and_returns_the_embedding_sites(self, admin_user):
        client = self._client(admin_user)

        response = client.post(
            "/support/admin/settings/update/",
            {"widget_allowed_origins": "https://shop.example.com\r\nhttps://*.brand.test\n"},
        )

        assert response.status_code == 302
        assert EscalatedSetting.get("widget_allowed_origins") == "https://shop.example.com\nhttps://*.brand.test"
        props = json.loads(client.get("/support/admin/settings/", **INERTIA).content)["props"]
        assert props["settings"]["widget_allowed_origins"] == "https://shop.example.com\nhttps://*.brand.test"
        assert props["errors"] == {}

    def test_rejects_invalid_entries_and_keeps_the_old_list(self, admin_user):
        EscalatedSetting.set("widget_allowed_origins", "https://shop.example.com")
        EscalatedSetting.set("ticket_reference_prefix", "ESC")
        client = self._client(admin_user)

        response = client.post(
            "/support/admin/settings/update/",
            {"widget_allowed_origins": "https://shop.example.com/checkout\n*", "ticket_reference_prefix": "NEW"},
        )

        assert response.status_code == 302
        assert EscalatedSetting.get("widget_allowed_origins") == "https://shop.example.com"
        assert EscalatedSetting.get("ticket_reference_prefix") == "ESC"
        props = json.loads(client.get("/support/admin/settings/", **INERTIA).content)["props"]
        assert "widget_allowed_origins" in props["errors"]

    def test_an_empty_list_clears_the_setting(self, admin_user):
        EscalatedSetting.set("widget_allowed_origins", "https://shop.example.com")

        self._client(admin_user).post("/support/admin/settings/update/", {"widget_allowed_origins": "  "})

        assert EscalatedSetting.get("widget_allowed_origins") == ""
