"""
Stored secrets never reach the browser.

Import source credentials, webhook signing secrets, SSO secrets, inbound
email secrets, 2FA seeds and API token hashes are kept server-side so the app
can use them. None of them is shown back to an admin: every page and JSON
response that carries one of these records is checked here, through the real
URL router, for the raw secret anywhere in the body.

Mirrors escalated-laravel's tests/Feature/Admin/SecretsNeverSerializedTest.php.
"""

import json
from unittest.mock import patch

import pytest

from escalated import hooks
from escalated.api_serializers import ApiTokenSerializer
from escalated.models import ApiToken, EscalatedSetting, ImportJob, TwoFactor, Webhook, WebhookDelivery
from escalated.serializers import WebhookSerializer
from escalated.views.import_views import job_json
from tests.fake_import_adapter import FakeImportAdapter

IMPORT_API_KEY = "imp-key-7f3a9c2e5b1d"
IMPORT_PASSWORD = "imp-pass-q8w7e6r5t4"
IMPORT_CREDENTIALS = {"api_token": IMPORT_API_KEY, "password": IMPORT_PASSWORD}
WEBHOOK_SECRET = "whsec-4c8e1a7b9d3f"
JWT_SECRET = "jwt-secret-5e6f7a8b9c"
OAUTH_SECRET = "oauth-secret-1a2b3c4d5e"
TOTP_SECRET = "TOTPSECRETBASE32XX"
RECOVERY_CODE = "rc-aaaa-bbbb"
MASK = "********"

INERTIA = {"HTTP_X_INERTIA": "true"}
PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 443))]
BASE = "/support/admin"


@pytest.fixture
def admin_client(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def adapter():
    """FakeDesk accepts the credentials this file seeds."""
    instance = FakeImportAdapter()
    instance.test_connection = lambda credentials: credentials.get("api_token") == IMPORT_API_KEY

    def register(adapters):
        return [*adapters, instance]

    hooks.add_filter("import.adapters", register)
    yield instance
    hooks.remove_filter("import.adapters", register)


@pytest.fixture(autouse=True)
def public_dns():
    """Webhook saves check the URL resolves publicly; keep that off the network."""
    with patch("escalated.outbound_security.socket.getaddrinfo", return_value=PUBLIC_ADDRINFO):
        yield


def body_of(response):
    assert response.status_code == 200, f"answered {response.status_code}"
    return response.content.decode("utf-8")


def assert_has_no_secrets(response, secrets):
    body = body_of(response)
    for secret in secrets:
        assert secret not in body, f"{secret!r} was sent to the browser"


def props_of(response):
    return json.loads(body_of(response))["props"]


def post_json(client, path, body):
    return client.post(path, data=json.dumps(body), content_type="application/json", **INERTIA)


def import_job_with_credentials():
    return ImportJob.objects.create(
        platform="fakedesk",
        status="importing",
        credentials=IMPORT_CREDENTIALS,
        progress={"tickets": {"total": 10, "processed": 4, "skipped": 0, "failed": 0, "cursor": None}},
        error_log=[{"entity_type": "tickets", "source_id": str(n), "error": "bad"} for n in range(60)],
    )


def webhook_with_secret():
    return Webhook.objects.create(
        url="https://hooks.example.com/escalated",
        events=["ticket.created"],
        secret=WEBHOOK_SECRET,
        active=True,
    )


# --- Import ------------------------------------------------------------------


@pytest.mark.django_db
class TestImport:
    def test_index_page(self, admin_client, adapter):
        job = import_job_with_credentials()
        response = admin_client.get(f"{BASE}/import/", **INERTIA)
        assert_has_no_secrets(response, [IMPORT_API_KEY, IMPORT_PASSWORD])
        [sent] = props_of(response)["jobs"]
        assert sent["id"] == str(job.id)
        assert sent["platform"] == "fakedesk"
        assert sent["status"] == "importing"
        assert "created_at" in sent
        assert "credentials" not in sent

    def test_progress_page(self, admin_client, adapter):
        job = import_job_with_credentials()
        for path in (f"{BASE}/import/progress/{job.id}/", f"{BASE}/import/{job.id}/"):
            response = admin_client.get(path, **INERTIA)
            assert_has_no_secrets(response, [IMPORT_API_KEY, IMPORT_PASSWORD])
            sent = props_of(response)["job"]
            assert sent["id"] == str(job.id)
            assert sent["progress"]["tickets"]["processed"] == 4
            assert len(sent["error_log"]) == 50
            assert sent["error_log"][-1]["source_id"] == "59"
            assert "credentials" not in sent

    def test_status_and_progress_json(self, admin_client, adapter):
        job = import_job_with_credentials()
        status = admin_client.get(f"{BASE}/import/status/{job.id}/")
        assert_has_no_secrets(status, [IMPORT_API_KEY, IMPORT_PASSWORD])
        assert json.loads(status.content)["status"] == "importing"
        progress = admin_client.get(f"{BASE}/import/{job.id}/progress/")
        assert_has_no_secrets(progress, [IMPORT_API_KEY, IMPORT_PASSWORD])

    def test_connect_test_connection_mapping_and_review_steps(self, admin_client, adapter):
        connect = admin_client.get(f"{BASE}/import/fakedesk/connect/", **INERTIA)
        assert_has_no_secrets(connect, [IMPORT_API_KEY, IMPORT_PASSWORD])

        tested = admin_client.post(
            f"{BASE}/import/fakedesk/test-connection/",
            data=json.dumps({"credentials": IMPORT_CREDENTIALS}),
            content_type="application/json",
        )
        assert_has_no_secrets(tested, [IMPORT_API_KEY, IMPORT_PASSWORD])
        assert json.loads(tested.content) == {"success": True}

        mapping = admin_client.get(f"{BASE}/import/fakedesk/mapping/", **INERTIA)
        assert_has_no_secrets(mapping, [IMPORT_API_KEY, IMPORT_PASSWORD])

        review = post_json(admin_client, f"{BASE}/import/fakedesk/review/", {"field_mappings": {}})
        assert_has_no_secrets(review, [IMPORT_API_KEY, IMPORT_PASSWORD])

    def test_the_import_run_still_reads_the_credentials_server_side(self):
        job = import_job_with_credentials()
        assert ImportJob.objects.get(pk=job.pk).credentials == IMPORT_CREDENTIALS
        assert "credentials" not in job_json(job)
        assert IMPORT_API_KEY not in json.dumps(job_json(job))


# --- Webhooks ----------------------------------------------------------------


@pytest.mark.django_db
class TestWebhooks:
    def test_index_edit_and_delivery_log_pages(self, admin_client):
        webhook = webhook_with_secret()
        WebhookDelivery.objects.create(
            webhook=webhook, event="ticket.created", payload={"ok": True}, response_code=200, attempts=1
        )

        index = admin_client.get(f"{BASE}/webhooks/", **INERTIA)
        assert_has_no_secrets(index, [WEBHOOK_SECRET])
        [listed] = props_of(index)["webhooks"]
        assert listed["has_secret"] is True
        assert "secret" not in listed

        edit = admin_client.get(f"{BASE}/webhooks/{webhook.pk}/edit/", **INERTIA)
        assert_has_no_secrets(edit, [WEBHOOK_SECRET])
        sent = props_of(edit)["webhook"]
        assert sent["has_secret"] is True
        assert sent["url"] == "https://hooks.example.com/escalated"
        assert "secret" not in sent

        log = admin_client.get(f"{BASE}/webhooks/{webhook.pk}/deliveries/", **INERTIA)
        assert_has_no_secrets(log, [WEBHOOK_SECRET])
        assert props_of(log)["webhook"]["has_secret"] is True

    def test_has_secret_is_false_without_one(self, admin_client):
        Webhook.objects.create(url="https://hooks.example.com/plain", events=["ticket.created"], secret=None)
        [listed] = props_of(admin_client.get(f"{BASE}/webhooks/", **INERTIA))["webhooks"]
        assert listed["has_secret"] is False

    def test_a_blank_secret_keeps_the_stored_one(self, admin_client):
        webhook = webhook_with_secret()
        post_json(
            admin_client,
            f"{BASE}/webhooks/{webhook.pk}/edit/",
            {
                "url": "https://hooks.example.com/escalated",
                "events": ["ticket.created", "ticket.updated"],
                "secret": "",
                "clear_secret": False,
                "active": True,
            },
        )
        webhook.refresh_from_db()
        assert webhook.secret == WEBHOOK_SECRET
        assert webhook.events == ["ticket.created", "ticket.updated"]

    def test_a_missing_secret_keeps_the_stored_one(self, admin_client):
        webhook = webhook_with_secret()
        admin_client.post(
            f"{BASE}/webhooks/{webhook.pk}/edit/",
            {"url": "https://hooks.example.com/escalated", "events": '["ticket.created"]', "active": "true"},
        )
        webhook.refresh_from_db()
        assert webhook.secret == WEBHOOK_SECRET

    def test_a_new_secret_replaces_and_clear_secret_clears(self, admin_client):
        webhook = webhook_with_secret()
        payload = {"url": "https://hooks.example.com/escalated", "events": ["ticket.created"], "active": True}

        post_json(admin_client, f"{BASE}/webhooks/{webhook.pk}/edit/", {**payload, "secret": "whsec-new"})
        webhook.refresh_from_db()
        assert webhook.secret == "whsec-new"

        post_json(admin_client, f"{BASE}/webhooks/{webhook.pk}/edit/", {**payload, "secret": "", "clear_secret": True})
        webhook.refresh_from_db()
        assert webhook.secret is None

    def test_create_still_stores_the_secret(self, admin_client):
        post_json(
            admin_client,
            f"{BASE}/webhooks/create/",
            {"url": "https://hooks.example.com/new", "events": ["ticket.created"], "secret": WEBHOOK_SECRET},
        )
        assert Webhook.objects.get().secret == WEBHOOK_SECRET


# --- SSO ---------------------------------------------------------------------


@pytest.mark.django_db
class TestSso:
    def seed(self):
        EscalatedSetting.set("sso_provider", "jwt")
        EscalatedSetting.set("sso_jwt_secret", JWT_SECRET)
        EscalatedSetting.set("sso_oauth_client_secret", OAUTH_SECRET)
        EscalatedSetting.set("sso_entity_id", "entity-public")

    def test_the_sso_page_shows_the_secrets_as_a_mask(self, admin_client):
        self.seed()
        response = admin_client.get(f"{BASE}/settings/sso/", **INERTIA)
        assert_has_no_secrets(response, [JWT_SECRET, OAUTH_SECRET, "secret-"])
        settings = props_of(response)["settings"]
        assert settings["sso_jwt_secret"] == MASK
        assert settings["sso_entity_id"] == "entity-public"

    def test_an_unset_secret_is_an_empty_string(self, admin_client):
        settings = props_of(admin_client.get(f"{BASE}/settings/sso/", **INERTIA))["settings"]
        assert settings["sso_jwt_secret"] == ""

    def test_the_mask_posted_back_keeps_the_stored_secret(self, admin_client):
        self.seed()
        settings = props_of(admin_client.get(f"{BASE}/settings/sso/", **INERTIA))["settings"]

        post_json(admin_client, f"{BASE}/settings/sso/", {**settings, "sso_url": "https://id.example.com/jwt"})
        assert EscalatedSetting.get("sso_jwt_secret") == JWT_SECRET
        assert EscalatedSetting.get("sso_url") == "https://id.example.com/jwt"

        # The older "abc*****" mask is recognised too.
        post_json(admin_client, f"{BASE}/settings/sso/", {**settings, "sso_jwt_secret": "jwt*********"})
        assert EscalatedSetting.get("sso_jwt_secret") == JWT_SECRET

    def test_a_new_secret_replaces_the_stored_one(self, admin_client):
        self.seed()
        settings = props_of(admin_client.get(f"{BASE}/settings/sso/", **INERTIA))["settings"]
        post_json(admin_client, f"{BASE}/settings/sso/", {**settings, "sso_jwt_secret": "jwt-secret-rotated"})
        assert EscalatedSetting.get("sso_jwt_secret") == "jwt-secret-rotated"

    def test_the_general_settings_page_does_not_carry_the_sso_secrets(self, admin_client):
        self.seed()
        response = admin_client.get(f"{BASE}/settings/", **INERTIA)
        assert_has_no_secrets(response, [JWT_SECRET, OAUTH_SECRET])


# --- General settings (inbound email secrets) --------------------------------


@pytest.mark.django_db
class TestInboundEmailSecrets:
    SECRETS = {
        "mailgun_signing_key": "mgk-9d8c7b6a5f4e",
        "postmark_inbound_token": "pmt-1a2b3c4d5e6f",
        "imap_password": "imp-8f7e6d5c4b",
    }

    def test_fully_masked_on_the_settings_page(self, admin_client):
        for key, value in self.SECRETS.items():
            EscalatedSetting.set(key, value)
        response = admin_client.get(f"{BASE}/settings/", **INERTIA)
        settings = props_of(response)["settings"]
        for key in self.SECRETS:
            assert settings[key] == MASK
        # Not even the first characters.
        assert_has_no_secrets(response, [*self.SECRETS.values(), "mgk", "pmt-", "imp-"])

    def test_the_mask_posted_back_keeps_them_and_a_new_value_replaces(self, admin_client):
        for key, value in self.SECRETS.items():
            EscalatedSetting.set(key, value)
        post_json(
            admin_client,
            f"{BASE}/settings/update/",
            {"mailgun_signing_key": MASK, "postmark_inbound_token": "mgk*****", "imap_password": "new-imap-pass"},
        )
        assert EscalatedSetting.get("mailgun_signing_key") == self.SECRETS["mailgun_signing_key"]
        assert EscalatedSetting.get("postmark_inbound_token") == self.SECRETS["postmark_inbound_token"]
        assert EscalatedSetting.get("imap_password") == "new-imap-pass"


# --- 2FA and API tokens ------------------------------------------------------


@pytest.mark.django_db
class TestTwoFactorAndApiTokens:
    def test_two_factor_status_page_carries_no_secret(self, admin_client, admin_user):
        TwoFactor.objects.create(user=admin_user, secret=TOTP_SECRET, recovery_codes=[RECOVERY_CODE])
        response = admin_client.get(f"{BASE}/settings/two-factor/", **INERTIA)
        assert_has_no_secrets(response, [TOTP_SECRET, RECOVERY_CODE])

    def test_api_token_pages_carry_only_the_one_time_plaintext(self, admin_client, admin_user):
        existing = ApiToken.create_token(user=admin_user, name="CI")
        stored_hash = existing["token"].token

        index = admin_client.get(f"{BASE}/api-tokens/", **INERTIA)
        assert_has_no_secrets(index, [stored_hash, existing["plain_text_token"]])

        created = admin_client.post(
            f"{BASE}/api-tokens/create/",
            data=json.dumps({"name": "Deploy", "user_id": admin_user.pk}),
            content_type="application/json",
        )
        assert created.status_code == 201
        payload = json.loads(created.content)
        new_hash = ApiToken.objects.get(name="Deploy").token
        # Only the one-time plaintext is handed back, never the stored hash.
        assert payload["plain_text_token"]
        assert new_hash not in created.content.decode("utf-8")

        updated = admin_client.post(
            f"{BASE}/api-tokens/{existing['token'].pk}/update/",
            data=json.dumps({"name": "CI renamed"}),
            content_type="application/json",
        )
        assert_has_no_secrets(updated, [stored_hash])


# --- Serializers never carry the secrets -------------------------------------


@pytest.mark.django_db
def test_serializers_leave_out_every_stored_secret(admin_user):
    webhook = webhook_with_secret()
    job = import_job_with_credentials()
    token = ApiToken.create_token(user=admin_user, name="CI")["token"]

    webhook_data = WebhookSerializer.serialize(webhook)
    assert "secret" not in webhook_data
    assert webhook_data["has_secret"] is True
    assert "credentials" not in job_json(job)
    assert "token" not in ApiTokenSerializer.serialize(token)
    assert token.token not in json.dumps(ApiTokenSerializer.serialize(token))
