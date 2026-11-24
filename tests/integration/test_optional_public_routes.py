"""Optional public routes are registered only while their feature is on
(B2, ecom-core 2026-11-24): the guest portal and the widget behind their
switches, the cloud webhook behind its signing secret. Slack inbound does not
exist in this package."""

import importlib

import pytest
from django.test import override_settings
from django.urls import Resolver404, clear_url_caches, resolve

from escalated import conf


def _reload_urls():
    import escalated.urls
    import tests.urls

    importlib.reload(escalated.urls)
    importlib.reload(tests.urls)
    clear_url_caches()


@pytest.fixture
def routes_with(settings):
    """Rebuild the URL conf under extra ESCALATED settings; restore it afterwards."""
    base = dict(settings.ESCALATED)

    def build(**escalated):
        settings.ESCALATED = {**base, **escalated}
        _reload_urls()

    yield build
    settings.ESCALATED = base
    _reload_urls()


GUEST_PATHS = [
    "/support/guest/create/",
    "/support/guest/store/",
    "/support/guest/verification",
    "/support/guest/lookup",
    "/support/guest/abc/",
    "/support/guest/abc/reply/",
    "/support/guest/abc/rate/",
    "/support/api/v1/mobile/guest/tickets",
    "/support/api/v1/mobile/guest/verification",
]

WIDGET_PATHS = [
    "/support/widget/embed.js",
    "/support/widget/config",
    "/support/widget/config/",
    "/support/widget/articles",
    "/support/widget/tickets",
    "/support/widget/tickets/create/",
    "/support/widget/verification",
    "/support/widget/chat/start",
    "/support/widget/chat/start/",
    "/support/widget/chat/abc/messages",
]

CLOUD_WEBHOOK = "/support/cloud/webhook/"


def _registered(path):
    try:
        resolve(path)
    except Resolver404:
        return False
    return True


def test_defaults_register_guest_and_widget_routes_but_no_cloud_webhook(routes_with):
    routes_with()
    assert all(_registered(path) for path in GUEST_PATHS + WIDGET_PATHS)
    assert not _registered(CLOUD_WEBHOOK)


def test_guest_routes_switch_off_registers_no_guest_route(routes_with):
    routes_with(GUEST_ROUTES_ENABLED=False)
    assert [path for path in GUEST_PATHS if _registered(path)] == []
    # Nothing else goes with them.
    assert all(_registered(path) for path in WIDGET_PATHS)
    assert _registered("/support/tickets/")


def test_widget_switch_off_registers_no_widget_route(routes_with):
    routes_with(WIDGET_ENABLED=False)
    assert [path for path in WIDGET_PATHS if _registered(path)] == []
    assert all(_registered(path) for path in GUEST_PATHS)


def test_cloud_webhook_is_registered_once_its_signing_secret_is_set(routes_with):
    routes_with(HOSTED_SIGNING_SECRET="whsec_site")
    assert resolve(CLOUD_WEBHOOK).url_name == "cloud_webhook"


def test_guest_runtime_setting_still_answers_404_while_the_routes_are_on(routes_with, client, db):
    from escalated.models import EscalatedSetting

    routes_with()
    EscalatedSetting.set("guest_tickets_enabled", "0")
    assert client.get("/support/guest/create/").status_code == 404


@pytest.mark.parametrize(
    ("variable", "key"),
    [("ESCALATED_GUEST_ROUTES", "GUEST_ROUTES_ENABLED"), ("ESCALATED_WIDGET_ENABLED", "WIDGET_ENABLED")],
)
def test_switches_default_from_their_environment_variable(monkeypatch, variable, key):
    try:
        with override_settings(ESCALATED={}):
            monkeypatch.setenv(variable, "false")
            importlib.reload(conf)
            assert conf.get_setting(key) is False

            monkeypatch.setenv(variable, "")
            importlib.reload(conf)
            assert conf.get_setting(key) is True

            monkeypatch.delenv(variable)
            importlib.reload(conf)
            assert conf.get_setting(key) is True
    finally:
        monkeypatch.delenv(variable, raising=False)
        importlib.reload(conf)
