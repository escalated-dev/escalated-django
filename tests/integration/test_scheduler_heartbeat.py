"""The recurring-jobs heartbeat and the admin warning (B4, ecom-core
2026-11-24): check_sla records when it ran; while that is missing or older
than 15 minutes the admin Settings and Reports pages send a ``scheduler`` prop
with healthy=False, the message and the commands to schedule, and a warning is
logged."""

import io
import logging
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from escalated import scheduler
from escalated.models import EscalatedSetting

pytestmark = pytest.mark.django_db

ADMIN_PAGES = ["escalated:admin_settings", "escalated:admin_reports", "escalated:admin_reports_dashboard"]


def _props(client, user, url_name):
    client.force_login(user)
    response = client.get(reverse(url_name), HTTP_X_INERTIA="true")
    assert response.status_code == 200, response.content[:500]
    return response.json()["props"]


def test_check_sla_records_the_heartbeat():
    assert scheduler.last_run_at() is None
    before = timezone.now()
    call_command("check_sla", stdout=io.StringIO())
    assert scheduler.last_run_at() >= before.replace(microsecond=0)
    assert scheduler.status()["healthy"] is True


def test_missing_heartbeat_is_unhealthy_and_names_the_commands():
    status = scheduler.status()
    assert status["healthy"] is False
    assert status["last_run_at"] is None
    commands = [entry["command"] for entry in status["commands"]]
    for needed in (
        "check_sla",
        "evaluate_escalations",
        "run_automations",
        "wake_snoozed_tickets",
        "process_delayed_actions",
    ):
        assert f"python manage.py {needed}" in commands
        assert f"python manage.py {needed}" in status["message"]
    assert all(set(entry) == {"command", "interval"} for entry in status["commands"])
    assert "not running" in status["message"]


def test_process_delayed_actions_runs_the_due_ones_only():
    from escalated.workflow_models import DelayedAction, Workflow
    from tests.factories import TicketFactory

    ticket = TicketFactory(priority="low")
    workflow = Workflow.objects.create(name="Bump later", trigger_event="ticket.created", is_active=True)
    due = DelayedAction.objects.create(
        workflow=workflow,
        ticket=ticket,
        action_data={"type": "change_priority", "value": "urgent"},
        execute_at=timezone.now() - timedelta(minutes=1),
    )
    later = DelayedAction.objects.create(
        workflow=workflow,
        ticket=ticket,
        action_data={"type": "change_status", "value": "closed"},
        execute_at=timezone.now() + timedelta(hours=1),
    )

    out = io.StringIO()
    call_command("process_delayed_actions", stdout=out)

    ticket.refresh_from_db()
    due.refresh_from_db()
    later.refresh_from_db()
    assert ticket.priority == "urgent"
    assert ticket.status != "closed"
    assert due.executed is True
    assert later.executed is False
    assert "Processed 1 delayed actions." in out.getvalue()

    # Run again: nothing is due twice.
    out = io.StringIO()
    call_command("process_delayed_actions", stdout=out)
    assert "Processed 0 delayed actions." in out.getvalue()


def test_heartbeat_older_than_15_minutes_is_unhealthy():
    now = timezone.now()
    scheduler.record_heartbeat(now - timedelta(minutes=16))
    status = scheduler.status(now)
    assert status["healthy"] is False
    assert status["last_run_at"] == (now - timedelta(minutes=16)).isoformat()

    scheduler.record_heartbeat(now - timedelta(minutes=14))
    assert scheduler.status(now)["healthy"] is True


def test_optional_jobs_are_listed_only_when_their_feature_is_on(settings):
    commands = [entry["command"] for entry in scheduler.commands()]
    assert "python manage.py escalated_plugin_cron" not in commands
    assert "python manage.py close_idle_chats" not in commands

    settings.ESCALATED = {**settings.ESCALATED, "SDK_ENABLED": True}
    EscalatedSetting.set("chat_enabled", "1")
    commands = [entry["command"] for entry in scheduler.commands()]
    assert "python manage.py escalated_plugin_cron" in commands
    assert "python manage.py close_idle_chats" in commands


@pytest.mark.parametrize("url_name", ADMIN_PAGES)
def test_admin_pages_warn_while_the_jobs_are_not_running(client, admin_user, caplog, url_name):
    with caplog.at_level(logging.WARNING, logger="escalated.scheduler"):
        prop = _props(client, admin_user, url_name)["scheduler"]
    assert prop["healthy"] is False
    assert prop["last_run_at"] is None
    assert "python manage.py check_sla" in prop["message"]
    assert {"command": "python manage.py check_sla", "interval": "every minute"} in prop["commands"]
    assert any("recurring jobs are not running" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("url_name", ADMIN_PAGES)
def test_admin_pages_report_healthy_after_a_recent_run(client, admin_user, caplog, url_name):
    scheduler.record_heartbeat()
    with caplog.at_level(logging.WARNING, logger="escalated.scheduler"):
        prop = _props(client, admin_user, url_name)["scheduler"]
    assert prop["healthy"] is True
    assert prop["last_run_at"] is not None
    assert not [record for record in caplog.records if record.name == "escalated.scheduler"]


def test_heartbeat_is_not_shown_as_an_editable_setting(client, admin_user):
    scheduler.record_heartbeat()
    assert scheduler.HEARTBEAT_KEY not in _props(client, admin_user, "escalated:admin_settings")["settings"]


def test_database_system_check_reports_the_stale_heartbeat():
    from escalated.setup_checks import check_setup_data

    messages = [warning.msg for warning in check_setup_data(None, databases=["default"])]
    assert any("recurring jobs are not running" in message for message in messages)
    assert check_setup_data(None, databases=None) == []
