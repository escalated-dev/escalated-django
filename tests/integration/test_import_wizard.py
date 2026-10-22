"""
The admin Import wizard the shared frontend drives
(src/pages/Admin/Import/{Index,Connect,Mapping,Review,Progress}.vue), on
escalated-laravel's routes and props (Admin\\ImportController, ImportService,
ImportJob, ImportContext).

The source is FakeImportAdapter, registered through the ``import.adapters``
filter the way a plugin registers a Zendesk or Freshdesk adapter.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from django.db import connection

from escalated import hooks
from escalated.models import ImportJob, ImportSourceMap, Reply, SlaPolicy, Ticket
from escalated.services import import_runner
from escalated.services.automation_runner import AutomationRunner
from escalated.services.escalation_service import EscalationService
from escalated.services.sla_service import SlaService
from escalated.support.import_context import ImportContext
from tests.factories import TicketFactory, UserFactory
from tests.fake_import_adapter import (
    CREDENTIAL_FIELDS,
    CREDENTIALS,
    TICKET_SOURCE_FIELDS,
    TOKEN,
    FakeImportAdapter,
)

MANIFEST = Path(__file__).resolve().parent.parent / "fixtures" / "escalated-pages.json"
SHARED_PROPS = {"errors", "auth", "current_user", "flash", "escalated", "plugin_ui"}
BASE = "/support/admin/import"
FIELD_MAPPINGS = {"tickets": {"subject": "title", "state": "status"}}


class InlineThread:
    """Runs the background import in the test's own thread and transaction."""

    started = []

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None):
        self.target, self.args, self.kwargs = target, args, kwargs or {}

    def start(self):
        InlineThread.started.append(self.args)
        self.target(*self.args, **self.kwargs)


@pytest.fixture
def adapter():
    instance = FakeImportAdapter()

    def register(adapters):
        return [*adapters, instance]

    hooks.add_filter("import.adapters", register)
    yield instance
    hooks.remove_filter("import.adapters", register)


@pytest.fixture
def admin_client(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def inline_runs(monkeypatch, django_capture_on_commit_callbacks):
    """Run queued imports inline: the thread runs on start, after commit."""
    InlineThread.started = []
    monkeypatch.setattr(import_runner.threading, "Thread", InlineThread)

    class Runner:
        def __call__(self, fn):
            with django_capture_on_commit_callbacks(execute=True):
                return fn()

    return Runner()


def declared(component):
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["props"][component]["props"]


def inertia_get(client, path):
    response = client.get(path, HTTP_X_INERTIA="true")
    assert response.status_code == 200, f"{path} answered {response.status_code}"
    return json.loads(response.content)


def inertia_post(client, path, body=None):
    return client.post(path, data=json.dumps(body or {}), content_type="application/json", HTTP_X_INERTIA="true")


def expect_screen(client, path, component):
    page = inertia_get(client, path)
    assert page["component"] == component
    sent = set(page["props"]) - SHARED_PROPS
    assert sorted(set(declared(component)) - sent) == []
    assert sorted(sent - set(declared(component))) == []
    return page


def connect(client, credentials=CREDENTIALS):
    return client.post(
        f"{BASE}/fakedesk/test-connection/",
        data=json.dumps({"credentials": credentials}),
        content_type="application/json",
    )


def start(client):
    assert json.loads(connect(client).content) == {"success": True}
    response = inertia_post(client, f"{BASE}/fakedesk/start/", {"field_mappings": FIELD_MAPPINGS})
    return response, ImportJob.objects.order_by("-created_at").first()


@pytest.mark.django_db
class TestIndex:
    def test_lists_the_registered_adapters_and_recent_jobs(self, admin_client, adapter):
        job = ImportJob.objects.create(platform="fakedesk", status="completed", credentials=CREDENTIALS)

        page = expect_screen(admin_client, f"{BASE}/", "Escalated/Admin/Import/Index")

        assert page["props"]["adapters"] == [
            {"name": "fakedesk", "display_name": "FakeDesk", "credential_fields": CREDENTIAL_FIELDS}
        ]
        (row,) = page["props"]["jobs"]
        assert row["id"] == str(job.id)
        assert row["platform"] == "fakedesk"
        assert row["status"] == "completed"
        assert row["created_at"]
        assert "credentials" not in row

    def test_is_admin_only(self, client, adapter):
        client.force_login(UserFactory(username="not-admin"))

        response = client.get(f"{BASE}/")

        assert response.status_code == 403


@pytest.mark.django_db
class TestConnect:
    def test_renders_the_credential_form(self, admin_client, adapter):
        page = expect_screen(admin_client, f"{BASE}/fakedesk/connect/", "Escalated/Admin/Import/Connect")

        assert page["props"]["platform"] == "fakedesk"
        assert page["props"]["display_name"] == "FakeDesk"
        assert page["props"]["credential_fields"] == CREDENTIAL_FIELDS

    def test_unknown_platform_is_404(self, admin_client, adapter):
        assert admin_client.get(f"{BASE}/nowhere/connect/").status_code == 404

    def test_refused_credentials_answer_success_false(self, admin_client, adapter):
        response = connect(admin_client, {**CREDENTIALS, "api_token": "wrong"})

        assert response.status_code == 200
        assert json.loads(response.content) == {"success": False}

    def test_a_source_error_answers_422_with_the_message(self, admin_client, adapter):
        response = connect(admin_client, {**CREDENTIALS, "subdomain": "down"})

        assert response.status_code == 422
        assert json.loads(response.content) == {"success": False, "error": "FakeDesk is unreachable"}


@pytest.mark.django_db
class TestMapping:
    def test_sends_the_visitor_back_to_connect_until_a_connection_is_tested(self, admin_client, adapter):
        response = admin_client.get(f"{BASE}/fakedesk/mapping/")

        assert response.status_code == 302
        assert response["Location"] == f"{BASE}/fakedesk/connect/"

    def test_renders_defaults_and_source_fields_read_with_the_stored_credentials(self, admin_client, adapter):
        connect(admin_client)

        page = inertia_get(admin_client, f"{BASE}/fakedesk/mapping/")

        assert page["component"] == "Escalated/Admin/Import/Mapping"
        props = page["props"]
        assert props["platform"] == "fakedesk"
        assert props["display_name"] == "FakeDesk"
        assert props["entity_types"] == ["contacts", "tags", "tickets", "replies"]
        assert props["mappings"]["tickets"] == {
            "defaults": {"subject": "title", "state": "status"},
            "source_fields": TICKET_SOURCE_FIELDS,
        }
        assert props["mappings"]["contacts"] == {"defaults": {}, "source_fields": []}
        assert adapter.source_field_credentials == CREDENTIALS
        # The credentials stay on the server: Laravel never round-trips them.
        assert "credentials" not in props
        assert TOKEN not in json.dumps(page)


@pytest.mark.django_db
class TestReview:
    def test_echoes_the_choices_and_writes_nothing(self, admin_client, adapter):
        response = inertia_post(
            admin_client,
            f"{BASE}/fakedesk/review/",
            {"field_mappings": FIELD_MAPPINGS, "entity_types": ["tickets", "replies"]},
        )

        page = json.loads(response.content)
        assert page["component"] == "Escalated/Admin/Import/Review"
        assert page["props"]["platform"] == "fakedesk"
        assert page["props"]["field_mappings"] == FIELD_MAPPINGS
        assert page["props"]["entity_types"] == ["tickets", "replies"]
        assert ImportJob.objects.count() == 0
        assert Ticket.objects.count() == 0


@pytest.mark.django_db
class TestStart:
    def test_refuses_to_start_without_a_tested_connection(self, admin_client, adapter):
        response = inertia_post(admin_client, f"{BASE}/fakedesk/start/", {"field_mappings": FIELD_MAPPINGS})

        assert response.status_code == 302
        assert response["Location"] == f"{BASE}/fakedesk/connect/"
        assert ImportJob.objects.count() == 0

    def test_creates_the_job_moves_the_credentials_and_queues_the_run(
        self, admin_client, admin_user, adapter, monkeypatch
    ):
        queued = []
        monkeypatch.setattr(import_runner, "dispatch", lambda job: queued.append(job.id))

        response, job = start(admin_client)

        assert response.status_code == 302
        assert response["Location"] == f"{BASE}/progress/{job.id}/"
        assert job.platform == "fakedesk"
        assert job.status == "mapping"
        assert job.user_id == admin_user.pk
        assert job.field_mappings == FIELD_MAPPINGS
        assert job.credentials == CREDENTIALS
        assert queued == [job.id]

        table = connection.ops.quote_name(ImportJob._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT credentials FROM {table}")
            (stored,) = cursor.fetchone()
        assert TOKEN not in stored

        # The session copy is gone once the job holds them.
        assert admin_client.get(f"{BASE}/fakedesk/mapping/").status_code == 302


@pytest.mark.django_db
class TestEndToEnd:
    @pytest.fixture
    def imported(self, admin_client, adapter, inline_runs):
        SlaPolicy.objects.create(
            name="Default",
            is_default=True,
            first_response_hours={"high": 1, "urgent": 1},
            resolution_hours={"high": 8, "urgent": 8},
        )
        importing = []
        adapter.on_extract = lambda *_: importing.append(ImportContext.is_importing())

        _, job = inline_runs(lambda: start(admin_client))
        job.refresh_from_db()
        return job, importing

    def test_completes_the_job_and_drops_its_credentials(self, imported):
        job, _ = imported

        assert job.status == "completed"
        assert job.completed_at is not None
        assert job.credentials is None
        assert job.error_log == []
        assert job.progress["tickets"] == {
            "total": 3,
            "processed": 3,
            "skipped": 0,
            "failed": 0,
            "cursor": "2",
        }
        assert set(job.progress) == {"contacts", "tags", "tickets", "replies"}
        assert ImportSourceMap.objects.filter(import_job=job, entity_type="tickets").count() == 3

    def test_imports_the_tickets(self, imported):
        tickets = list(Ticket.objects.order_by("pk"))

        assert [t.subject for t in tickets] == ["Refund please", "Login broken", "Feature idea"]
        assert [t.status for t in tickets] == ["open", "resolved", "open"]
        assert [t.priority for t in tickets] == ["high", "urgent", "medium"]

        refund = tickets[0]
        assert refund.requester.email == "ada@customer.test"
        assert [tag.name for tag in refund.tags.all()] == ["Billing"]
        assert refund.created_at == datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        assert [r.body for r in refund.replies.all()] == ["Looking into it"]
        assert Reply.objects.filter(is_internal_note=True).count() == 1

    def test_runs_in_import_mode(self, imported):
        _, importing = imported

        assert importing and all(importing)
        assert ImportContext.is_importing() is False
        assert Ticket.objects.filter(sla_policy__isnull=False).count() == 0


@pytest.mark.django_db
class TestProgress:
    @pytest.fixture
    def job(self):
        return ImportJob.objects.create(
            platform="fakedesk",
            status="importing",
            credentials=CREDENTIALS,
            field_mappings=FIELD_MAPPINGS,
            progress={"tickets": {"total": 3, "processed": 1, "skipped": 0, "failed": 1, "cursor": "2"}},
            error_log=[{"entity_type": "tickets", "source_id": "k9", "error": "boom", "timestamp": "2024-01-01"}],
        )

    def test_renders_the_job_the_screen_polls(self, admin_client, job):
        page = expect_screen(admin_client, f"{BASE}/progress/{job.id}/", "Escalated/Admin/Import/Progress")

        sent = page["props"]["job"]
        assert sent["id"] == str(job.id)
        assert sent["platform"] == "fakedesk"
        assert sent["status"] == "importing"
        assert sent["progress"] == job.progress
        assert sent["error_log"] == job.error_log
        assert sent["field_mappings"] == FIELD_MAPPINGS
        assert "credentials" not in sent
        assert TOKEN not in json.dumps(page)

    def test_answers_the_status_poll(self, admin_client, job):
        body = json.loads(admin_client.get(f"{BASE}/status/{job.id}/").content)

        assert set(body) == {"status", "progress", "error_log", "started_at", "completed_at"}
        assert body["status"] == "importing"
        assert body["progress"] == job.progress
        assert body["error_log"] == job.error_log

    def test_unknown_job_is_404(self, admin_client):
        assert admin_client.get(f"{BASE}/status/00000000-0000-0000-0000-000000000000/").status_code == 404


@pytest.mark.django_db
class TestPauseResumeCancel:
    def test_pauses_mid_run_and_resumes_without_importing_twice(self, admin_client, adapter, inline_runs):
        def pause_on_second_ticket_page(entity_type, cursor):
            if entity_type == "tickets" and cursor == "2":
                ImportJob.objects.update(status="paused")

        adapter.on_extract = pause_on_second_ticket_page
        _, job = inline_runs(lambda: start(admin_client))
        job.refresh_from_db()

        assert job.status == "paused"
        assert Ticket.objects.count() == 3
        assert "replies" not in job.progress
        assert job.credentials == CREDENTIALS

        adapter.on_extract = None
        adapter.extract_calls.clear()
        response = inline_runs(lambda: inertia_post(admin_client, f"{BASE}/resume/{job.id}/"))

        assert response.status_code == 302
        assert response["Location"] == f"{BASE}/progress/{job.id}/"
        job.refresh_from_db()
        assert job.status == "completed"
        assert Ticket.objects.count() == 3
        assert Reply.objects.count() == 2
        # The run picked tickets up from its saved cursor, not from the start.
        assert ("tickets", None) not in adapter.extract_calls
        assert ("tickets", "2") in adapter.extract_calls

    def test_pauses_an_importing_job(self, admin_client):
        job = ImportJob.objects.create(platform="fakedesk", status="importing", credentials=CREDENTIALS)

        response = inertia_post(admin_client, f"{BASE}/pause/{job.id}/")

        assert response["Location"] == f"{BASE}/progress/{job.id}/"
        job.refresh_from_db()
        assert job.status == "paused"

    def test_resumes_a_failed_job_through_mapping(self, admin_client, adapter, inline_runs):
        job = ImportJob.objects.create(platform="fakedesk", status="failed", credentials=CREDENTIALS)

        inline_runs(lambda: inertia_post(admin_client, f"{BASE}/resume/{job.id}/"))

        job.refresh_from_db()
        assert job.status == "completed"
        assert Ticket.objects.count() == 3

    def test_cancels_a_job_and_drops_its_credentials(self, admin_client):
        job = ImportJob.objects.create(platform="fakedesk", status="paused", credentials=CREDENTIALS)

        response = inertia_post(admin_client, f"{BASE}/cancel/{job.id}/")

        assert response["Location"] == f"{BASE}/progress/{job.id}/"
        job.refresh_from_db()
        assert job.status == "failed"
        assert job.completed_at is not None
        assert job.credentials is None


@pytest.mark.django_db
class TestImportModeGuards:
    """Laravel's ImportContext holds back SLA, escalations and automations."""

    def test_sla_escalations_and_automations_stand_down_while_importing(self):
        SlaPolicy.objects.create(
            name="Default", is_default=True, first_response_hours={"medium": 1}, resolution_hours={"medium": 8}
        )
        ticket = TicketFactory()

        def during_import():
            SlaService.attach_default_policy(ticket)
            return SlaService.check_all_tickets(), EscalationService.evaluate_all(), AutomationRunner().run()

        breaches, escalations, automations = ImportContext.suppress(during_import)

        ticket.refresh_from_db()
        assert ticket.sla_policy_id is None
        assert breaches == (0, 0)
        assert escalations == 0
        assert automations == 0
