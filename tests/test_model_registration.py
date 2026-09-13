"""
Every Escalated model must be registered by django.setup() alone.

Django registers a model when its module is imported, and during setup it
imports only the app's ``models`` module. Workflow, WorkflowLog, DelayedAction
(workflow_models), Mention (mention_models), PluginStoreRecord
(bridge.plugin_store_record) and EscalatedPlugin (plugin_models) live in
their own modules, which were imported only as a side effect of loading the
URL conf or of plugin loading.

In a process that never loads the URL conf (a Celery worker, ``manage.py
shell``, a management command) those models did not exist. Deleting a ticket
there skipped the workflow_logs rows that point at it, and the database
refused the delete with a foreign-key error. ``makemigrations`` also saw the
unregistered models as deleted.

These tests run in subprocesses because the test process itself has already
loaded the URL conf.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

SEPARATE_MODULE_MODELS = [
    "Workflow",
    "WorkflowLog",
    "DelayedAction",
    "Mention",
    "PluginStoreRecord",
    "EscalatedPlugin",
]


def _run(code, settings_module="tests.settings", extra_path=None, extra_env=None):
    python_path = [str(REPO_ROOT)]
    if extra_path:
        python_path.insert(0, str(extra_path))
    if os.environ.get("PYTHONPATH"):
        python_path.append(os.environ["PYTHONPATH"])
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": settings_module,
        "PYTHONPATH": os.pathsep.join(python_path),
        **(extra_env or {}),
    }
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=300,
    )


@pytest.fixture
def sqlite_settings(tmp_path):
    """A settings module whose SQLite database is a file two processes can share."""
    database = tmp_path / "registration.sqlite3"
    (tmp_path / "registration_settings.py").write_text(
        "from tests.settings import *  # noqa: F401,F403\n"
        "\n"
        "DATABASES = {\n"
        "    'default': {\n"
        "        'ENGINE': 'django.db.backends.sqlite3',\n"
        f"        'NAME': {str(database)!r},\n"
        "    }\n"
        "}\n"
        "ESCALATED = {**ESCALATED, 'PLUGINS_ENABLED': False}  # noqa: F405\n"
    )
    return tmp_path


def test_every_model_is_registered_by_setup_alone(sqlite_settings):
    # PLUGINS_ENABLED is off in these settings, so plugin loading cannot
    # register EscalatedPlugin as a side effect either.
    result = _run(
        "import django\n"
        "django.setup()\n"
        "from django.apps import apps\n"
        f"for name in {SEPARATE_MODULE_MODELS!r}:\n"
        "    try:\n"
        "        apps.get_model('escalated', name)\n"
        "    except LookupError:\n"
        "        print('MISSING', name)\n",
        settings_module="registration_settings",
        extra_path=sqlite_settings,
    )

    assert result.returncode == 0, result.stderr
    assert [line for line in result.stdout.splitlines() if line.startswith("MISSING")] == []


def test_ticket_with_workflow_logs_deletes_outside_the_url_conf(sqlite_settings):
    # First process: build the schema and a ticket with a workflow log, the way
    # a web process (which has loaded the URL conf) would.
    created = _run(
        "import django\n"
        "django.setup()\n"
        "from django.core.management import call_command\n"
        "call_command('migrate', verbosity=0)\n"
        "import escalated.urls  # noqa: F401\n"
        "from escalated.workflow_models import Workflow, WorkflowLog\n"
        "from tests.factories import TicketFactory\n"
        "ticket = TicketFactory()\n"
        "workflow = Workflow.objects.create(name='w', trigger_event='ticket.created', conditions={}, actions=[])\n"
        "WorkflowLog.objects.create(workflow=workflow, ticket=ticket, trigger_event='ticket.created')\n"
        "print(ticket.pk)\n",
        settings_module="registration_settings",
        extra_path=sqlite_settings,
    )
    assert created.returncode == 0, created.stderr
    ticket_pk = int(created.stdout.strip().splitlines()[-1])

    # Second process: only django.setup(), as in a Celery worker or a shell.
    deleted = _run(
        "import sys\n"
        "import django\n"
        "django.setup()\n"
        "from django.db import connection, transaction\n"
        "from escalated.models import Ticket\n"
        "with transaction.atomic():\n"
        "    Ticket.objects.get(pk=int(sys.argv[-1])).delete()\n"
        "with connection.cursor() as cursor:\n"
        "    cursor.execute('SELECT COUNT(*) FROM escalated_workflow_logs')\n"
        "    print('workflow_logs left:', cursor.fetchone()[0])\n"
        f"# ticket {ticket_pk}\n".replace("sys.argv[-1]", repr(str(ticket_pk))),
        settings_module="registration_settings",
        extra_path=sqlite_settings,
    )

    assert deleted.returncode == 0, deleted.stderr
    assert "workflow_logs left: 0" in deleted.stdout


def test_makemigrations_finds_no_changes():
    # skip_checks=False: call_command() skips system checks by default, but
    # manage.py migrate runs them, so a model that fails one (an index name over
    # 30 characters, say) would stop every host project from migrating.
    result = _run(
        "import sys\n"
        "import django\n"
        "django.setup()\n"
        "from django.core.management import call_command\n"
        "try:\n"
        "    call_command('makemigrations', 'escalated', check=True, dry_run=True, verbosity=1, skip_checks=False)\n"
        "except SystemExit as exc:\n"
        "    sys.exit(exc.code)\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
