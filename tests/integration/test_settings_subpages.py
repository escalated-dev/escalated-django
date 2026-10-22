"""The admin Settings sub-pages, through the real router.

The contract is what escalated-laravel's controllers pass to the shared Vue
pages under ``Escalated/Admin/Settings/*``: the component name, every prop key
the page reads, the fields it posts, the validation it gets, and the flash it
comes back to.
"""

import json

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from escalated.models import EscalatedSetting
from tests.factories import UserFactory

INERTIA = {"HTTP_X_INERTIA": "true"}

CSAT = "/support/admin/settings/csat/"
PUBLIC_TICKETS = "/support/admin/settings/public-tickets/"
DATA_RETENTION = "/support/admin/settings/data-retention/"
DATABASE = "/support/admin/settings/database/"
DATABASE_TEST = "/support/admin/settings/database/test/"
EMAIL = "/support/admin/settings/email/"


@pytest.fixture
def ui_enabled():
    with override_settings(ESCALATED={"UI_ENABLED": True}):
        yield


@pytest.fixture
def admin_client(db, ui_enabled):
    client = Client()
    client.force_login(UserFactory(username="settings_admin", is_staff=True, is_superuser=True))
    return client


@pytest.fixture
def agent_client(db, ui_enabled):
    client = Client()
    client.force_login(UserFactory(username="settings_nobody"))
    return client


def page(response):
    assert response.status_code == 200, response.content[:500]
    return json.loads(response.content)


def props(client, url):
    return page(client.get(url, **INERTIA))["props"]


def post_json(client, url, body, method="post"):
    return getattr(client, method)(url, data=json.dumps(body), content_type="application/json", **INERTIA)


def setting(key):
    return EscalatedSetting.get(key)


# ---------------------------------------------------------------------------
# Route names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, path",
    [
        ("admin_settings_csat", CSAT),
        ("admin_settings_csat_update", CSAT),
        ("admin_settings_public_tickets", PUBLIC_TICKETS),
        ("admin_settings_public_tickets_update", PUBLIC_TICKETS),
        ("admin_settings_data_retention", DATA_RETENTION),
        ("admin_settings_data_retention_update", DATA_RETENTION),
        ("admin_settings_database", DATABASE),
        ("admin_settings_database_update", DATABASE),
        ("admin_settings_database_test", DATABASE_TEST),
        ("admin_settings_email", EMAIL),
        ("admin_settings_email_update", EMAIL),
    ],
)
def test_route_names_resolve(name, path):
    assert reverse(f"escalated:{name}") == path


# ---------------------------------------------------------------------------
# Admin only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url", [CSAT, PUBLIC_TICKETS, DATA_RETENTION, DATABASE, EMAIL])
def test_non_admin_cannot_view(agent_client, url):
    assert agent_client.get(url, **INERTIA).status_code == 403


@pytest.mark.parametrize(
    "url, body",
    [
        (CSAT, {"csat_scale": "1-3"}),
        (PUBLIC_TICKETS, {"guest_policy_mode": "guest_user", "guest_policy_user_id": 1}),
        (DATA_RETENTION, {"retention_closed_tickets": "1_year"}),
        (DATABASE, {"connection": "default"}),
        (DATABASE_TEST, {"connection": "default"}),
        (EMAIL, {"addresses": [{"email": "a@example.com"}]}),
    ],
)
def test_non_admin_cannot_save(agent_client, url, body):
    assert post_json(agent_client, url, body).status_code == 403
    assert setting("csat_scale") is None
    assert setting("guest_policy_mode") is None
    assert setting("retention_closed_tickets") is None
    assert setting("email_addresses") is None


# ---------------------------------------------------------------------------
# CsatSettings
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCsat:
    def test_renders_defaults(self, admin_client):
        body = page(admin_client.get(CSAT, **INERTIA))
        assert body["component"] == "Escalated/Admin/Settings/CsatSettings"
        assert body["props"]["settings"] == {
            "csat_question_text": "How would you rate your support experience?",
            "csat_scale": "1-5",
            "csat_delivery_trigger": "on_resolve",
            "csat_delay_hours": 0,
        }

    def test_save_persists_and_flashes(self, admin_client):
        response = post_json(
            admin_client,
            CSAT,
            {
                "csat_question_text": "How did we do?",
                "csat_scale": "1-3",
                "csat_delivery_trigger": "delayed",
                "csat_delay_hours": 24,
            },
        )
        assert response.status_code in (302, 303)
        assert response["Location"] == CSAT
        assert setting("csat_question_text") == "How did we do?"
        assert setting("csat_scale") == "1-3"
        assert setting("csat_delivery_trigger") == "delayed"
        assert setting("csat_delay_hours") == "24"

        shown = props(admin_client, CSAT)
        assert shown["flash"] == {"success": "CSAT settings updated."}
        assert shown["settings"]["csat_delay_hours"] == 24
        # Shown once.
        assert props(admin_client, CSAT)["flash"] == {}

    def test_invalid_save_changes_nothing(self, admin_client):
        response = post_json(
            admin_client,
            CSAT,
            {
                "csat_question_text": "",
                "csat_scale": "1-10",
                "csat_delivery_trigger": "sometimes",
                "csat_delay_hours": 500,
            },
        )
        assert response.status_code in (302, 303)
        assert setting("csat_scale") is None
        errors = props(admin_client, CSAT)["errors"]
        assert set(errors) == {"csat_question_text", "csat_scale", "csat_delivery_trigger", "csat_delay_hours"}


# ---------------------------------------------------------------------------
# PublicTickets
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPublicTickets:
    def test_renders_defaults(self, admin_client):
        body = page(admin_client.get(PUBLIC_TICKETS, **INERTIA))
        assert body["component"] == "Escalated/Admin/Settings/PublicTickets"
        assert body["props"]["settings"] == {
            "guest_policy_mode": "unassigned",
            "guest_policy_user_id": None,
            "guest_policy_signup_url_template": "",
        }

    @pytest.mark.parametrize("method", ["post", "put"])
    def test_save_guest_user_persists_and_flashes(self, admin_client, method):
        response = post_json(
            admin_client,
            PUBLIC_TICKETS,
            {
                "guest_policy_mode": "guest_user",
                "guest_policy_user_id": 7,
                "guest_policy_signup_url_template": "https://example.com/{email}",
            },
            method=method,
        )
        assert response.status_code in (302, 303)
        assert response["Location"] == PUBLIC_TICKETS
        assert setting("guest_policy_mode") == "guest_user"
        assert setting("guest_policy_user_id") == "7"
        # Only kept for prompt_signup.
        assert setting("guest_policy_signup_url_template") == ""

        shown = props(admin_client, PUBLIC_TICKETS)
        assert shown["flash"] == {"success": "Guest policy updated."}
        assert shown["settings"]["guest_policy_user_id"] == "7"

    def test_prompt_signup_keeps_template_and_clears_user(self, admin_client):
        EscalatedSetting.set("guest_policy_user_id", "7")
        post_json(
            admin_client,
            PUBLIC_TICKETS,
            {"guest_policy_mode": "prompt_signup", "guest_policy_signup_url_template": "https://x.test/signup"},
        )
        assert setting("guest_policy_user_id") == ""
        assert setting("guest_policy_signup_url_template") == "https://x.test/signup"

    def test_guest_user_without_user_id_is_rejected(self, admin_client):
        response = post_json(admin_client, PUBLIC_TICKETS, {"guest_policy_mode": "guest_user"})
        assert response.status_code in (302, 303)
        assert setting("guest_policy_mode") is None
        assert "guest_policy_user_id" in props(admin_client, PUBLIC_TICKETS)["errors"]

    def test_unknown_mode_is_rejected(self, admin_client):
        post_json(admin_client, PUBLIC_TICKETS, {"guest_policy_mode": "everyone"})
        assert setting("guest_policy_mode") is None
        assert "guest_policy_mode" in props(admin_client, PUBLIC_TICKETS)["errors"]


# ---------------------------------------------------------------------------
# DataRetention
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDataRetention:
    def test_renders_defaults(self, admin_client):
        body = page(admin_client.get(DATA_RETENTION, **INERTIA))
        assert body["component"] == "Escalated/Admin/Settings/DataRetention"
        assert body["props"]["settings"] == {
            "retention_closed_tickets": "never",
            "retention_attachments": "never",
            "retention_audit_logs": "never",
            "retention_user_data_gdpr": False,
        }
        assert body["props"]["purgePreview"] == {"tickets": 0, "attachments": 0, "audit_logs": 0}

    def test_save_persists_and_flashes(self, admin_client):
        response = post_json(
            admin_client,
            DATA_RETENTION,
            {
                "retention_closed_tickets": "2_years",
                "retention_attachments": "1_year",
                "retention_audit_logs": "90_days",
                "retention_user_data_gdpr": True,
            },
        )
        assert response.status_code in (302, 303)
        assert response["Location"] == DATA_RETENTION
        assert setting("retention_closed_tickets") == "2_years"
        assert setting("retention_attachments") == "1_year"
        assert setting("retention_audit_logs") == "90_days"
        assert setting("retention_user_data_gdpr") == "1"

        shown = props(admin_client, DATA_RETENTION)
        assert shown["flash"] == {"success": "Data retention settings updated."}
        assert shown["settings"]["retention_user_data_gdpr"] is True

    def test_gdpr_accepts_zero(self, admin_client):
        post_json(
            admin_client,
            DATA_RETENTION,
            {
                "retention_closed_tickets": "never",
                "retention_attachments": "never",
                "retention_audit_logs": "never",
                "retention_user_data_gdpr": "0",
            },
        )
        assert setting("retention_user_data_gdpr") == "0"

    def test_invalid_save_changes_nothing(self, admin_client):
        post_json(
            admin_client,
            DATA_RETENTION,
            {
                "retention_closed_tickets": "90_days",
                "retention_attachments": "forever",
                "retention_audit_logs": "1_year",
                "retention_user_data_gdpr": "maybe",
            },
        )
        assert setting("retention_closed_tickets") is None
        errors = props(admin_client, DATA_RETENTION)["errors"]
        assert set(errors) == {
            "retention_closed_tickets",
            "retention_attachments",
            "retention_audit_logs",
            "retention_user_data_gdpr",
        }

    def test_preview_counts_what_the_purge_would_remove(self, admin_client):
        from tests.integration.test_purge_expired_data import make_attachment, make_audit_log, make_closed_ticket

        make_closed_ticket(days_ago=800)
        make_closed_ticket(days_ago=10)
        make_attachment(days_ago=400)
        make_audit_log(days_ago=100)
        make_audit_log(days_ago=1)
        EscalatedSetting.set("retention_closed_tickets", "2_years")
        EscalatedSetting.set("retention_attachments", "1_year")
        EscalatedSetting.set("retention_audit_logs", "90_days")

        assert props(admin_client, DATA_RETENTION)["purgePreview"] == {
            "tickets": 1,
            "attachments": 1,
            "audit_logs": 1,
        }


# ---------------------------------------------------------------------------
# DatabaseConnection
# ---------------------------------------------------------------------------

CONNECTION_KEYS = {
    "name",
    "driver",
    "database",
    "is_current",
    "is_host_default",
    "reachable",
    "migrated",
    "ticket_count",
    "error",
}


@pytest.mark.django_db
class TestDatabaseConnection:
    def test_renders_the_connection_read_only(self, admin_client):
        from tests.factories import TicketFactory

        TicketFactory()
        body = page(admin_client.get(DATABASE, **INERTIA))
        assert body["component"] == "Escalated/Admin/Settings/DatabaseConnection"
        shown = body["props"]
        assert shown["current"] == "default"
        assert shown["hostDefault"] == "default"
        assert shown["pinnedByConfig"] is True
        assert shown["tablePrefix"] == "escalated_"

        assert [c["name"] for c in shown["connections"]] == ["default"]
        connection = shown["connections"][0]
        assert set(connection) == CONNECTION_KEYS
        assert connection["is_current"] is True
        assert connection["is_host_default"] is True
        assert connection["reachable"] is True
        assert connection["migrated"] is True
        assert connection["ticket_count"] == 1
        assert connection["error"] is None
        assert connection["driver"]
        # A label, never credentials.
        assert "PASSWORD" not in json.dumps(connection)

    def test_update_is_refused_because_the_connection_is_pinned(self, admin_client):
        response = post_json(admin_client, DATABASE, {"connection": "default"})
        assert response.status_code in (302, 303)
        assert response["Location"] == DATABASE
        assert props(admin_client, DATABASE)["flash"] == {
            "error": "The database connection is set in configuration and cannot be changed from here."
        }

    def test_test_describes_a_configured_connection(self, admin_client):
        response = post_json(admin_client, DATABASE_TEST, {"connection": "default"})
        assert response.status_code == 200
        described = response.json()
        assert set(described) == CONNECTION_KEYS
        assert described["name"] == "default"
        assert described["reachable"] is True

    def test_test_rejects_an_unknown_connection(self, admin_client):
        response = post_json(admin_client, DATABASE_TEST, {"connection": "nowhere"})
        assert response.status_code == 422
        assert "connection" in response.json()["errors"]

    def test_test_requires_a_connection(self, admin_client):
        response = post_json(admin_client, DATABASE_TEST, {})
        assert response.status_code == 422
        assert "connection" in response.json()["errors"]

    def test_an_unreachable_probe_is_reported_not_raised(self, admin_client, monkeypatch):
        from escalated.services import connection_inspector

        def boom(alias):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(connection_inspector, "_probe", boom)
        connection = props(admin_client, DATABASE)["connections"][0]
        assert connection["reachable"] is False
        assert connection["migrated"] is False
        assert connection["ticket_count"] is None
        assert "connection refused" in connection["error"]


# ---------------------------------------------------------------------------
# EmailSettings
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEmailSettings:
    def test_renders_defaults(self, admin_client):
        body = page(admin_client.get(EMAIL, **INERTIA))
        assert body["component"] == "Escalated/Admin/Settings/EmailSettings"
        assert body["props"]["addresses"] == []
        assert body["props"]["defaultReplyAddress"] == ""

    def test_save_persists_normalised_addresses_and_flashes(self, admin_client):
        response = post_json(
            admin_client,
            EMAIL,
            {
                "addresses": [
                    {
                        "email": "support@example.com",
                        "display_name": "Support",
                        "department_id": "3",
                        "dkim_status": "verified",
                        "extra": "dropped",
                    },
                    {"email": "billing@example.com"},
                ],
                "default_reply_address": "support@example.com",
            },
        )
        assert response.status_code in (302, 303)
        assert response["Location"] == EMAIL
        assert json.loads(setting("email_addresses")) == [
            {
                "email": "support@example.com",
                "display_name": "Support",
                "department_id": 3,
                "dkim_status": "verified",
            },
            {"email": "billing@example.com", "display_name": None, "department_id": None, "dkim_status": "unknown"},
        ]
        assert setting("default_reply_address") == "support@example.com"

        shown = props(admin_client, EMAIL)
        assert shown["flash"] == {"success": "Email settings updated."}
        assert shown["defaultReplyAddress"] == "support@example.com"
        assert [a["email"] for a in shown["addresses"]] == ["support@example.com", "billing@example.com"]
        assert set(shown["addresses"][0]) == {"email", "display_name", "department_id", "dkim_status"}

    def test_default_reply_address_is_left_alone_when_not_sent(self, admin_client):
        EscalatedSetting.set("default_reply_address", "keep@example.com")
        post_json(admin_client, EMAIL, {"addresses": [{"email": "a@example.com"}]})
        assert setting("default_reply_address") == "keep@example.com"

    def test_invalid_save_changes_nothing(self, admin_client):
        post_json(
            admin_client,
            EMAIL,
            {
                "addresses": [{"email": "not-an-email", "dkim_status": "great", "department_id": "x"}],
                "default_reply_address": "nope",
            },
        )
        assert setting("email_addresses") is None
        errors = props(admin_client, EMAIL)["errors"]
        assert {
            "addresses.0.email",
            "addresses.0.dkim_status",
            "addresses.0.department_id",
            "default_reply_address",
        } <= set(errors)

    def test_addresses_are_required(self, admin_client):
        post_json(admin_client, EMAIL, {"default_reply_address": "a@example.com"})
        assert setting("default_reply_address") is None
        assert "addresses" in props(admin_client, EMAIL)["errors"]
