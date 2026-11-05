"""
Where the REST API is mounted.

``escalated.urls`` is included under the route prefix (``path("support/",
include("escalated.urls"))``), so ``API_PREFIX`` is relative to that include.
The default puts the API at ``{include}/api/v1/`` -- ``/support/api/v1/`` --
as escalated-laravel serves it, not ``/support/support/api/v1/``. The doubled
path stays as an alias for one release when ``API_PREFIX`` is not configured.
An explicitly configured ``API_PREFIX`` is mounted where it always was.
"""

from contextlib import contextmanager

import pytest
from django.test import override_settings
from django.urls import Resolver404, resolve, reverse

from escalated.views import api
from tests import settings as test_settings
from tests.embed_host import reload_urls

# The suite's own ESCALATED settings, which the URLconf was built from. The URL
# modules are rebuilt from these afterwards rather than from whatever an
# earlier test may have left in django.conf.settings.
BASELINE = test_settings.ESCALATED


@contextmanager
def escalated_settings(**changes):
    config = {**BASELINE}
    for key, value in changes.items():
        if value is None:
            config.pop(key, None)
        else:
            config[key] = value
    try:
        with override_settings(ESCALATED=config):
            reload_urls()
            yield
    finally:
        with override_settings(ESCALATED=BASELINE):
            reload_urls()


def resolves_to_ticket_list(path):
    try:
        match = resolve(path)
    except Resolver404:
        return False
    return _unwrap(match.func) is _unwrap(api.ticket_list)


def _unwrap(view):
    while getattr(view, "__wrapped__", None) is not None:
        view = view.__wrapped__
    return view


def test_the_default_api_is_mounted_once_under_the_route_prefix():
    with escalated_settings(API_PREFIX=None):
        assert reverse("escalated:escalated_api:ticket_list") == "/support/api/v1/tickets/"
        assert reverse("escalated:escalated_api:auth_login") == "/support/api/v1/auth/login/"
        assert reverse("escalated:escalated_api:mobile_guest_tickets") == "/support/api/v1/mobile/guest/tickets"
        assert resolves_to_ticket_list("/support/api/v1/tickets/")


def test_the_doubled_path_still_resolves_for_one_release():
    with escalated_settings(API_PREFIX=None):
        assert resolves_to_ticket_list("/support/support/api/v1/tickets/")
        # Reversing never produces the old path.
        assert not reverse("escalated:escalated_api:ticket_list").startswith("/support/support/")


@pytest.mark.django_db
def test_the_default_api_answers_over_http(client):
    with escalated_settings(API_PREFIX=None):
        assert client.post("/support/api/v1/auth/login/", {}, content_type="application/json").status_code != 404
        assert (
            client.post("/support/support/api/v1/auth/login/", {}, content_type="application/json").status_code != 404
        )


def test_a_configured_api_prefix_is_mounted_as_before():
    with escalated_settings(API_PREFIX="helpdesk-api/v2"):
        assert reverse("escalated:escalated_api:ticket_list") == "/support/helpdesk-api/v2/tickets/"
        assert resolves_to_ticket_list("/support/helpdesk-api/v2/tickets/")
        # No alias for a configured prefix.
        assert not resolves_to_ticket_list("/support/support/api/v1/tickets/")
        assert not resolves_to_ticket_list("/support/api/v1/tickets/")


def test_a_configured_prefix_equal_to_the_old_default_keeps_its_url():
    with escalated_settings(API_PREFIX="support/api/v1"):
        assert reverse("escalated:escalated_api:ticket_list") == "/support/support/api/v1/tickets/"
