"""Describe the databases the Database Connection settings page shows.

Escalated's connection is ``ESCALATED["DATABASE"]`` (``None`` = ``default``),
routed by ``escalated.routers.EscalatedRouter``. It is deployed configuration,
so the page is read-only here: it lists every alias in ``settings.DATABASES``,
marks the one Escalated uses, and probes each without ever raising.
"""

from django.conf import settings
from django.db import connections

from escalated.conf import get_setting

HOST_DEFAULT = "default"


def current_connection():
    alias = get_setting("DATABASE")
    return alias if isinstance(alias, str) and alias else HOST_DEFAULT


def configured(alias):
    return alias in settings.DATABASES


def all_connections():
    """Every configured alias, Escalated's own first."""
    current = current_connection()
    names = [current] + [alias for alias in settings.DATABASES if alias != current]
    return [describe(alias) for alias in names]


def _label(config):
    """Where the database is, without credentials."""
    name = str(config.get("NAME") or "")
    host = str(config.get("HOST") or "")
    if "sqlite" in str(config.get("ENGINE", "")):
        return name or None
    if name and host:
        return f"{name} @ {host}"
    return name or host or None


def _probe(alias):
    """``(migrated, ticket_count)`` for one alias. May raise; ``describe`` catches it."""
    from escalated.models import Ticket

    connection = connections[alias]
    table = Ticket._meta.db_table
    with connection.cursor() as cursor:
        if table not in connection.introspection.table_names(cursor):
            return False, None
        cursor.execute(f"SELECT COUNT(*) FROM {connection.ops.quote_name(table)}")
        return True, int(cursor.fetchone()[0])


def describe(alias):
    config = settings.DATABASES.get(alias, {})
    engine = str(config.get("ENGINE", ""))
    description = {
        "name": alias,
        "driver": engine.rsplit(".", 1)[-1] or None,
        "database": _label(config),
        "is_current": alias == current_connection(),
        "is_host_default": alias == HOST_DEFAULT,
        "reachable": False,
        "migrated": False,
        "ticket_count": None,
        "error": None,
    }
    try:
        migrated, count = _probe(alias)
    except Exception as exc:  # noqa: BLE001 - an unreachable database is a status, not a 500
        description["error"] = str(exc) or exc.__class__.__name__
        return description
    description.update(reachable=True, migrated=migrated, ticket_count=count)
    return description
