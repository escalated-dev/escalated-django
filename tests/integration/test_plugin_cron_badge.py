"""SDK plugin cron schedules and widget badges (plugin contract, Cron and Badges).

The bridge talks to a stand-in runtime: a fake JSON-RPC client that answers
``cron`` by storing the schedule through ``ctx.store.insert`` and ``badge`` by
asking ``ctx.currentUser``, exactly as the real runtime calls back into the
host while the host waits.
"""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from escalated.bridge.plugin_bridge import PluginBridge
from escalated.bridge.plugin_store_record import PluginStoreRecord
from escalated.plugin_ui_service import plugin_ui
from tests.factories import UserFactory
from tests.integration.test_plugin_contract import shared_plugins

NAME = "@acme/plugin-crm"


class FakeRuntime:
    """Answers the host's calls the way @escalated-dev/plugin-runtime does."""

    def __init__(self):
        self.calls = []

    def call(self, method, params, timeout_seconds, ctx_handler):
        self.calls.append((method, params, timeout_seconds))
        if method == "cron":
            ctx_handler(
                "ctx.store.insert",
                {"plugin": params["plugin"], "collection": "cron", "data": {"schedule": params["schedule"]}},
            )
            return None
        if method == "badge":
            component = params["component"]
            if component == "CrmInbox":
                user = ctx_handler("ctx.currentUser", {"plugin": params["plugin"]})
                return f"for {user['id']}" if user else "for nobody"
            if component == "CrmCount":
                return 7
            if component == "CrmObject":
                return {"not": "a badge"}
            raise RuntimeError("badge failed")
        return None

    def sent(self, method):
        return [params for (m, params, _t) in self.calls if m == method]


@pytest.fixture
def runtime():
    fake = FakeRuntime()
    bridge = PluginBridge()
    bridge._rpc = fake
    bridge._booted = True
    bridge._manifests = {
        NAME: {
            "name": NAME,
            "widgets": [
                {"component": "CrmWidget", "label": "Deals", "order": 1, "hasBadge": False},
                {"component": "CrmInbox", "label": "Inbox", "order": 2, "hasBadge": True},
                {"component": "CrmCount", "label": "Count", "order": 3, "hasBadge": True},
                {"component": "CrmBroken", "label": "Broken", "order": 4, "hasBadge": True},
                {"component": "CrmObject", "label": "Object", "order": 5, "hasBadge": True},
            ],
            "cronSchedules": ["* * * * *", "0 9 * * *", "not a schedule"],
        }
    }
    with (
        patch.object(PluginBridge, "_ensure_alive", return_value=True),
        # A plugin that throws answers with a JSON-RPC error; the runtime stays up.
        patch.object(PluginBridge, "_is_process_alive", return_value=True),
        patch("escalated.bridge.plugin_bridge.get_bridge", return_value=bridge),
    ):
        yield fake
    plugin_ui.clear()


@pytest.mark.django_db
def test_sdk_widget_badges_are_asked_as_the_viewer(runtime):
    admin = UserFactory(username="badge_admin", is_staff=True, is_superuser=True)

    widgets = {w["component"]: w for w in shared_plugins(admin)["dashboardWidgets"]}

    assert widgets["CrmInbox"]["badge"] == f"for {admin.pk}"
    assert widgets["CrmCount"]["badge"] == 7
    assert "badge" in widgets["CrmBroken"] and widgets["CrmBroken"]["badge"] is None
    assert widgets["CrmObject"]["badge"] is None
    assert "badge" not in widgets["CrmWidget"]
    assert [(p["plugin"], p["component"]) for p in runtime.sent("badge")] == [
        (NAME, "CrmInbox"),
        (NAME, "CrmCount"),
        (NAME, "CrmBroken"),
        (NAME, "CrmObject"),
    ]
    assert {t for (m, _p, t) in runtime.calls if m == "badge"} == {5}


@pytest.mark.django_db
def test_badges_are_not_asked_for_widgets_the_viewer_cannot_see(runtime):
    agent = UserFactory(username="badge_agent", is_staff=True)
    from escalated.bridge import plugin_bridge

    plugin_bridge.get_bridge()._manifests[NAME]["widgets"] = [
        {"component": "CrmInbox", "hasBadge": True, "capability": "nobody-has-this"}
    ]

    with patch("escalated.middleware.is_admin", return_value=False):
        assert shared_plugins(agent) == {}
    assert runtime.sent("badge") == []


@pytest.mark.django_db
def test_due_cron_schedules_run_once_for_the_minute_as_no_user(runtime):
    with override_settings(ESCALATED={"SDK_ENABLED": True}):
        call_command("escalated_plugin_cron", at="2026-10-29T09:00:20Z", stdout=StringIO())

    assert sorted(p["schedule"] for p in runtime.sent("cron")) == ["* * * * *", "0 9 * * *"]
    assert {p["plugin"] for p in runtime.sent("cron")} == {NAME}
    assert {t for (m, _p, t) in runtime.calls if m == "cron"} == {30}
    rows = PluginStoreRecord.objects.filter(plugin=NAME, collection="cron")
    assert sorted(r.data["schedule"] for r in rows) == ["* * * * *", "0 9 * * *"]

    with override_settings(ESCALATED={"SDK_ENABLED": True}):
        call_command("escalated_plugin_cron", at="2026-10-29T09:01:00Z", stdout=StringIO())
    assert [p["schedule"] for p in runtime.sent("cron")][2:] == ["* * * * *"]


@pytest.mark.django_db
def test_cron_acts_for_no_user_and_a_failing_schedule_does_not_stop_the_others(runtime):
    seen = []

    def call(method, params, timeout_seconds, ctx_handler):
        runtime.calls.append((method, params, timeout_seconds))
        seen.append(ctx_handler("ctx.currentUser", {}))
        if params["schedule"] == "* * * * *":
            raise RuntimeError("schedule threw")

    runtime.call = call
    with override_settings(ESCALATED={"SDK_ENABLED": True}):
        call_command("escalated_plugin_cron", at="2026-10-29T09:00:00Z", stdout=StringIO())

    assert sorted(p["schedule"] for p in runtime.sent("cron")) == ["* * * * *", "0 9 * * *"]
    assert seen == [None, None]


@pytest.mark.django_db
def test_no_cron_runs_when_sdk_plugins_are_off(runtime):
    with override_settings(ESCALATED={"SDK_ENABLED": False}):
        call_command("escalated_plugin_cron", at="2026-10-29T09:00:00Z", stdout=StringIO())

    assert runtime.sent("cron") == []
