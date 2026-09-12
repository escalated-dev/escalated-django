"""The suite runs on the backend it was told to run on.

A CI matrix leg that quietly fell back to SQLite would go green having tested
nothing the matrix exists to test, and the failure mode is invisible: every
assertion in the suite still passes. This is the one test that notices.
"""

import os

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection

from tests import settings as test_settings


def test_runs_against_the_engine_the_environment_asked_for():
    requested = os.environ.get("ESCALATED_TEST_ENGINE", "sqlite")

    assert (
        connection.vendor
        == {
            "sqlite": "sqlite",
            "postgres": "postgresql",
            "mysql": "mysql",
        }[requested]
    ), f"the suite asked for {requested} and connected to {connection.vendor}"


@pytest.mark.django_db
def test_reaches_a_database_it_can_actually_query():
    # connection.vendor reads settings, not a socket. Without this, a leg
    # pointed at a database that never came up would still pass the check above.
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")

        assert cursor.fetchone()[0] == 1


def test_an_unrecognised_engine_is_refused_rather_than_defaulted(monkeypatch):
    # The fallback is the danger, not the typo. A misspelt engine that quietly
    # became SQLite is exactly the silent-green this file exists to prevent.
    import importlib

    monkeypatch.setenv("ESCALATED_TEST_ENGINE", "postgresql")

    with pytest.raises(ImproperlyConfigured, match="postgresql"):
        importlib.reload(test_settings)

    # Reload once more with the real value so the module is left as it was --
    # settings are already bound, so this only restores the module object.
    monkeypatch.delenv("ESCALATED_TEST_ENGINE", raising=False)
    importlib.reload(test_settings)
