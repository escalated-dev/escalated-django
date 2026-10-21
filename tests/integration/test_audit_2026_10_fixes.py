"""Regression tests for the 2026-10-20 port audit (port of record: escalated-laravel).

- The shared frontend posts JSON (Inertia ``useForm``); views read it.
- Widget, guest and chat tickets send ``ticket_created``.
- The widget skips CSRF only for allowed embedding sites, honours the
  knowledge-base switches, and gates live chat on the widget and chat switches.
- The widget and chat are off by default; existing installs keep them on.
- Host user keys may be UUIDs.
- Ticket screens send the props the shared pages read.
"""

import json
import uuid

import pytest
from django.apps import apps as django_apps
from django.db import connection
from django.test import Client
from django.urls import reverse

from escalated import signals
from escalated.models import (
    ChatSession,
    EscalatedSetting,
    Reply,
    Tag,
    Ticket,
    TicketActivity,
)
from tests.factories import (
    ArticleFactory,
    CannedResponseFactory,
    ReplyFactory,
    SlaPolicyFactory,
    TicketFactory,
    UserFactory,
)
from tests.guest_proof import with_proof

SETTINGS_URL = "/support/admin/settings/update/"
WIDGET_TICKETS_URL = "/support/widget/tickets"
WIDGET_CHAT_START_URL = "/support/widget/chat/start"


def _post_json(client, url, body, **extra):
    return client.post(url, data=json.dumps(with_proof(url, body)), content_type="application/json", **extra)


def _inertia_props(client, url):
    response = client.get(url, HTTP_X_INERTIA="true")
    assert response.status_code == 200, response.status_code
    return json.loads(response.content)["props"]


@pytest.fixture
def admin_client(admin_user):
    client = Client()
    client.force_login(admin_user)
    return client


@pytest.fixture
def created_tickets():
    seen = []

    def receiver(sender, ticket, **kwargs):
        seen.append(ticket.pk)

    signals.ticket_created.connect(receiver, weak=False)
    yield seen
    signals.ticket_created.disconnect(receiver)


# ---------------------------------------------------------------------------
# 1. JSON bodies from the shared (Inertia) pages
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSettingsSavedFromJson:
    def test_json_save_keeps_the_values_sent(self, admin_client):
        EscalatedSetting.set("guest_tickets_enabled", "0")
        response = _post_json(
            admin_client,
            SETTINGS_URL,
            {
                "guest_tickets_enabled": True,
                "widget_allowed_origins": "https://shop.example.com",
                "ticket_reference_prefix": "ZZZ",
                "auto_close_resolved_after_days": 3,
            },
            HTTP_X_INERTIA="true",
        )

        assert response.status_code == 302
        assert EscalatedSetting.get("guest_tickets_enabled") == "1"
        assert EscalatedSetting.get("widget_allowed_origins") == "https://shop.example.com"
        assert EscalatedSetting.get("ticket_reference_prefix") == "ZZZ"
        assert EscalatedSetting.get("auto_close_resolved_after_days") == "3"

    def test_json_save_leaves_switches_it_did_not_send(self, admin_client):
        for key in ("allow_customer_close", "inbound_email_enabled", "show_powered_by"):
            EscalatedSetting.set(key, "1")

        _post_json(admin_client, SETTINGS_URL, {"ticket_reference_prefix": "ABC"})

        for key in ("allow_customer_close", "inbound_email_enabled", "show_powered_by"):
            assert EscalatedSetting.get(key) == "1", key

    def test_json_false_turns_a_switch_off(self, admin_client):
        EscalatedSetting.set("allow_customer_close", "1")
        _post_json(admin_client, SETTINGS_URL, {"allow_customer_close": False})
        assert EscalatedSetting.get("allow_customer_close") == "0"

    def test_form_post_still_reads_an_absent_checkbox_as_off(self, admin_client):
        EscalatedSetting.set("allow_customer_close", "1")
        admin_client.post(SETTINGS_URL, {"guest_tickets_enabled": "1"})
        assert EscalatedSetting.get("allow_customer_close") == "0"
        assert EscalatedSetting.get("guest_tickets_enabled") == "1"

    def test_support_widget_settings_are_saved(self, admin_client):
        _post_json(
            admin_client,
            SETTINGS_URL,
            {
                "widget_enabled": True,
                "widget_color": "#112233",
                "widget_position": "bottom-left",
                "widget_greeting": "Hello there",
                "widget_departments": "1, 2",
                "chat_enabled": True,
                "knowledge_base_public": True,
            },
        )

        assert EscalatedSetting.get("widget_enabled") == "1"
        assert EscalatedSetting.get("widget_color") == "#112233"
        assert EscalatedSetting.get("widget_position") == "bottom-left"
        assert EscalatedSetting.get("widget_greeting") == "Hello there"
        assert EscalatedSetting.get("widget_departments") == "1, 2"
        assert EscalatedSetting.get("chat_enabled") == "1"
        assert EscalatedSetting.get("knowledge_base_public") == "1"

        _post_json(admin_client, SETTINGS_URL, {"widget_enabled": False})
        assert EscalatedSetting.get("widget_enabled") == "0"

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("widget_color", "red"),
            ("widget_position", "top-left"),
            ("widget_departments", "1; DROP"),
            ("widget_greeting", "x" * 256),
        ],
    )
    def test_invalid_widget_setting_saves_nothing(self, admin_client, field, value):
        _post_json(admin_client, SETTINGS_URL, {field: value, "ticket_reference_prefix": "NOPE"})

        assert EscalatedSetting.get(field) is None
        assert EscalatedSetting.get("ticket_reference_prefix") is None
        props = _inertia_props(admin_client, reverse("escalated:admin_settings"))
        assert field in props["errors"]

    def test_page_gets_typed_values_and_the_keys_it_can_save(self, admin_client):
        EscalatedSetting.set("guest_tickets_enabled", "0")
        props = _inertia_props(admin_client, reverse("escalated:admin_settings"))

        assert props["settings"]["guest_tickets_enabled"] is False
        assert props["settings"]["widget_enabled"] is False
        assert props["settings"]["max_attachments_per_reply"] == 5
        for key in ("widget_enabled", "widget_color", "widget_allowed_origins", "chat_enabled"):
            assert key in props["supported_settings"]
        # Chat appearance keys are not saved, so the page must not offer them.
        assert "chat_routing_strategy" not in props["supported_settings"]


@pytest.mark.django_db
class TestOtherFormsReadJson:
    def test_admin_tag_create(self, admin_client):
        _post_json(admin_client, reverse("escalated:admin_tags_create"), {"name": "Billing", "color": "#123456"})
        tag = Tag.objects.get(name="Billing")
        assert tag.color == "#123456"

    def test_agent_reply(self, admin_client):
        ticket = TicketFactory()
        _post_json(admin_client, reverse("escalated:agent_ticket_reply", args=[ticket.pk]), {"body": "On it"})
        assert Reply.objects.filter(ticket=ticket, body="On it").exists()

    def test_request_data_reads_json_like_a_form(self, rf):
        from escalated.request_data import request_data

        request = rf.post(
            "/x/",
            data=json.dumps({"flag": True, "off": False, "n": 3, "none": None, "ids": [1, 2], "obj": {"a": 1}}),
            content_type="application/json",
        )
        data = request_data(request)

        assert data.get("flag") == "true"
        assert data.get("off") == "false"
        assert data.get("n") == "3"
        assert data.get("none") == ""
        assert data.getlist("ids") == ["1", "2"]
        assert json.loads(data.get("obj")) == {"a": 1}
        assert data.get("missing") is None
        assert "flag" in data and "missing" not in data


# ---------------------------------------------------------------------------
# 2. ticket_created for widget, guest and chat tickets
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("widget_on")
class TestTicketCreatedSignal:
    def _assert_created_side_effects(self, ticket, created_tickets, policy):
        ticket.refresh_from_db()
        assert created_tickets == [ticket.pk]
        assert ticket.sla_policy_id == policy.pk
        assert TicketActivity.objects.filter(ticket=ticket, type=TicketActivity.ActivityType.CREATED).exists()

    def test_widget_ticket(self, client, created_tickets):
        policy = SlaPolicyFactory(is_default=True)
        response = _post_json(
            client,
            WIDGET_TICKETS_URL,
            {"name": "Ann", "email": "ann@example.com", "subject": "Help", "description": "Broken"},
        )
        assert response.status_code == 201
        self._assert_created_side_effects(Ticket.objects.get(channel="widget"), created_tickets, policy)

    def test_guest_portal_ticket(self, client, created_tickets):
        policy = SlaPolicyFactory(is_default=True)
        response = client.post(
            "/support/guest/store/",
            with_proof(
                "/support/guest/store/",
                {"name": "Bo", "email": "bo@example.com", "subject": "Hi", "description": "Question"},
            ),
        )
        assert response.status_code == 302
        self._assert_created_side_effects(Ticket.objects.get(guest_email="bo@example.com"), created_tickets, policy)

    def test_chat_ticket(self, client, created_tickets):
        policy = SlaPolicyFactory(is_default=True)
        response = _post_json(client, WIDGET_CHAT_START_URL, {"name": "Cy", "email": "cy@example.com"})
        assert response.status_code == 201
        self._assert_created_side_effects(Ticket.objects.get(channel="chat"), created_tickets, policy)


# ---------------------------------------------------------------------------
# 3. Widget security: CSRF, knowledge-base switches, chat gate
# ---------------------------------------------------------------------------

CSRF_MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]
TICKET_BODY = {"name": "Ann", "email": "ann@example.com", "subject": "Help", "description": "Broken"}


@pytest.mark.django_db
@pytest.mark.usefixtures("widget_on")
class TestWidgetCsrf:
    @pytest.fixture(autouse=True)
    def _csrf(self, settings):
        settings.MIDDLEWARE = CSRF_MIDDLEWARE
        self.client = Client(enforce_csrf_checks=True)

    def test_allowed_embedding_site_needs_no_token(self):
        EscalatedSetting.set("widget_allowed_origins", "https://shop.example.com")
        response = _post_json(self.client, WIDGET_TICKETS_URL, TICKET_BODY, HTTP_ORIGIN="https://shop.example.com")
        assert response.status_code == 201

    def test_other_site_is_checked(self):
        EscalatedSetting.set("widget_allowed_origins", "https://shop.example.com")
        response = _post_json(self.client, WIDGET_TICKETS_URL, TICKET_BODY, HTTP_ORIGIN="https://evil.example.net")
        assert response.status_code == 403
        assert not Ticket.objects.exists()

    def test_request_without_origin_is_checked(self):
        response = _post_json(self.client, WIDGET_TICKETS_URL, TICKET_BODY)
        assert response.status_code == 403

    def test_chat_start_from_other_site_is_checked(self):
        response = _post_json(
            self.client, WIDGET_CHAT_START_URL, {"name": "A", "email": "a@x.io"}, HTTP_ORIGIN="https://evil.example"
        )
        assert response.status_code == 403
        assert not ChatSession.objects.exists()

    def test_reads_need_no_token(self):
        assert self.client.get("/support/widget/config").status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures("widget_on")
class TestWidgetKnowledgeBaseSwitches:
    def test_disabled_knowledge_base_is_not_served(self, client):
        article = ArticleFactory(title="Reset password", status="published")
        EscalatedSetting.set("knowledge_base_enabled", "0")

        assert client.get("/support/widget/articles", {"q": "Reset"}).status_code == 404
        assert client.get(f"/support/widget/articles/{article.slug}").status_code == 404
        assert client.get(f"/support/widget/articles/{article.pk}/").status_code == 404
        assert json.loads(client.get("/support/widget/config").content)["kb_enabled"] is False

    def test_private_knowledge_base_is_not_served_to_guests(self, client):
        article = ArticleFactory(title="Reset password", status="published")
        EscalatedSetting.set("knowledge_base_public", "0")

        assert client.get("/support/widget/articles", {"q": "Reset"}).status_code == 403
        assert client.get(f"/support/widget/articles/{article.slug}").status_code == 403
        assert json.loads(client.get("/support/widget/config").content)["kb_enabled"] is False

    def test_private_knowledge_base_is_served_to_a_signed_in_user(self, client):
        ArticleFactory(title="Reset password", status="published")
        EscalatedSetting.set("knowledge_base_public", "0")
        client.force_login(UserFactory())

        assert client.get("/support/widget/articles", {"q": "Reset"}).status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures("widget_on")
class TestWidgetChatGate:
    def test_chat_disabled(self, client):
        EscalatedSetting.set("chat_enabled", "0")

        assert _post_json(client, WIDGET_CHAT_START_URL, {"name": "A", "email": "a@x.io"}).status_code == 403
        assert json.loads(client.get("/support/widget/chat/availability").content)["available"] is False
        assert json.loads(client.get("/support/widget/config").content)["chat_enabled"] is False
        assert not ChatSession.objects.exists()

    def test_widget_disabled(self, client):
        EscalatedSetting.set("widget_enabled", "0")

        assert _post_json(client, WIDGET_CHAT_START_URL, {"name": "A", "email": "a@x.io"}).status_code == 403
        assert _post_json(client, "/support/widget/chat/start/", {"name": "A", "email": "a@x.io"}).status_code == 403
        assert json.loads(client.get("/support/widget/chat/availability").content)["available"] is False

    def test_open_session_stops_when_chat_is_switched_off(self, client):
        started = json.loads(_post_json(client, WIDGET_CHAT_START_URL, {"name": "A", "email": "a@x.io"}).content)
        EscalatedSetting.set("chat_enabled", "0")

        response = _post_json(client, f"/support/widget/chat/{started['id']}/messages", {"body": "hi"})
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# 4. Widget and chat off by default; existing installs keep them on
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWidgetDefaults:
    def test_widget_is_off_on_a_fresh_install(self, client):
        assert client.get("/support/widget/config").status_code == 403
        assert _post_json(client, WIDGET_TICKETS_URL, TICKET_BODY).status_code == 403

    def test_chat_is_off_until_switched_on(self, client):
        EscalatedSetting.set("widget_enabled", "1")
        assert _post_json(client, WIDGET_CHAT_START_URL, {"name": "A", "email": "a@x.io"}).status_code == 403

    def _run_migration(self):
        from importlib import import_module

        module = import_module("escalated.migrations.0031_widget_chat_defaults_and_activity_encoder")

        class Editor:
            pass

        editor = Editor()
        editor.connection = connection
        module.keep_widget_on_for_existing_installs(django_apps, editor)

    def test_migration_keeps_an_existing_install_on(self):
        TicketFactory()
        self._run_migration()
        assert EscalatedSetting.get_bool("widget_enabled") is True
        assert EscalatedSetting.get_bool("chat_enabled") is True

    def test_migration_keeps_an_admin_choice(self):
        TicketFactory()
        EscalatedSetting.set("widget_enabled", "0")
        self._run_migration()
        assert EscalatedSetting.get("widget_enabled") == "0"

    def test_migration_leaves_a_fresh_install_off(self):
        self._run_migration()
        assert EscalatedSetting.get("widget_enabled") is None
        assert EscalatedSetting.get("chat_enabled") is None

    def test_config_reads_the_saved_widget_settings(self, client, department):
        from tests.factories import DepartmentFactory

        other = DepartmentFactory()
        EscalatedSetting.set("widget_enabled", "1")
        EscalatedSetting.set("widget_color", "#ABCDEF")
        EscalatedSetting.set("widget_departments", str(department.pk))

        config = json.loads(client.get("/support/widget/config").content)
        assert config["color"] == "#ABCDEF"
        assert [d["id"] for d in config["departments"]] == [department.pk]
        assert other.pk not in [d["id"] for d in config["departments"]]


# ---------------------------------------------------------------------------
# 5. UUID / string user keys
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStringUserKeys:
    def test_activity_properties_accept_a_uuid(self):
        ticket = TicketFactory()
        agent_id = uuid.uuid4()
        activity = TicketActivity.objects.create(
            ticket=ticket, type=TicketActivity.ActivityType.ASSIGNED, properties={"agent_id": agent_id}
        )
        activity.refresh_from_db()
        assert activity.properties["agent_id"] == str(agent_id)

    def test_user_pk_uses_the_user_models_key_field(self, monkeypatch):
        from django.db import models

        from escalated import user_keys

        class UuidUser:
            class _meta:
                pk = models.UUIDField(primary_key=True)

        monkeypatch.setattr(user_keys, "get_user_model", lambda: UuidUser)
        value = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert user_keys.user_pk(value) == uuid.UUID(value)

    def test_user_pk_rejects_a_bad_key(self):
        from django.core.exceptions import ValidationError

        from escalated.user_keys import user_pk

        with pytest.raises(ValidationError):
            user_pk("not-a-key")

    def test_macro_assign_with_a_text_key(self, agent_user):
        from escalated.services.macro_service import MacroService
        from tests.factories import MacroFactory

        ticket = TicketFactory()
        macro = MacroFactory(actions=[{"type": "assign", "value": str(agent_user.pk)}])
        MacroService().apply(macro, ticket, agent_user)
        ticket.refresh_from_db()
        assert ticket.assigned_to_id == agent_user.pk

    def test_workflow_assign_and_follow_with_a_text_key(self, agent_user):
        from escalated.services.workflow_engine import WorkflowEngine

        ticket = TicketFactory()
        engine = WorkflowEngine()
        assert engine._execute_single_action({"type": "assign_agent", "value": str(agent_user.pk)}, ticket, None) == (
            "executed"
        )
        assert engine._execute_single_action({"type": "add_follower", "value": str(agent_user.pk)}, ticket, None) == (
            "executed"
        )
        ticket.refresh_from_db()
        assert ticket.assigned_to_id == agent_user.pk


# ---------------------------------------------------------------------------
# 6. Ticket screens send the props the shared pages read
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTicketScreenProps:
    def test_customer_show_nests_the_public_thread(self, client):
        customer = UserFactory()
        ticket = TicketFactory(requester=customer)
        public = ReplyFactory(ticket=ticket, body="Public answer")
        ReplyFactory(ticket=ticket, body="Agents only", is_internal_note=True)
        client.force_login(customer)

        props = _inertia_props(client, reverse("escalated:customer_ticket_show", args=[ticket.pk]))

        assert [r["id"] for r in props["ticket"]["replies"]] == [public.pk]
        assert "satisfaction_rating" in props["ticket"]

    def test_admin_show_nests_thread_and_sends_canned_responses(self, admin_client):
        ticket = TicketFactory()
        reply = ReplyFactory(ticket=ticket)
        canned = CannedResponseFactory()

        props = _inertia_props(admin_client, reverse("escalated:admin_tickets_show", args=[ticket.pk]))

        assert [r["id"] for r in props["ticket"]["replies"]] == [reply.pk]
        assert "activities" in props["ticket"]
        assert "pinned_notes" in props["ticket"]
        assert [c["id"] for c in props["cannedResponses"]] == [canned.pk]

    def test_agent_show_sends_canned_responses(self, admin_client):
        ticket = TicketFactory()
        canned = CannedResponseFactory()

        props = _inertia_props(admin_client, reverse("escalated:agent_ticket_show", args=[ticket.pk]))

        assert [c["id"] for c in props["cannedResponses"]] == [canned.pk]
        assert "pinned_notes" in props["ticket"]

    def test_canned_responses_index_sends_responses(self, admin_client):
        canned = CannedResponseFactory()
        props = _inertia_props(admin_client, reverse("escalated:admin_canned_responses_index"))
        assert [c["id"] for c in props["responses"]] == [canned.pk]
