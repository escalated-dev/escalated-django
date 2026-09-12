"""Database routing for Escalated's own tables.

Every Escalated model resolved the host project's ``default`` database with no
way to change it, which made the app unusable in any host that partitions its
data: a schema shared with a legacy system, a multi-tenant split, a separate
reporting store, or simply a host that would rather keep support tables out of
its primary database.

Django has no per-model connection setting -- routing is the mechanism -- so
this router is what ``ESCALATED["DATABASE"]`` is wired through. Add it to
``DATABASE_ROUTERS`` and Escalated's reads, writes and migrations follow the
named alias while everything else in the project carries on untouched.

The host's user model deliberately stays where the host put it. Escalated asks
the router about its own models only, so a ``User`` lookup falls through to
whatever routes it today -- which is how a ticket on one database can still
resolve its assignee on another.
"""

from .conf import get_setting

#: The app label Escalated's models live under.
ESCALATED_APP_LABEL = "escalated"


def _escalated_database():
    """The configured alias, or ``None`` to leave routing entirely alone."""
    alias = get_setting("DATABASE")

    return alias if isinstance(alias, str) and alias else None


def _is_escalated(model_or_label):
    if isinstance(model_or_label, str):
        return model_or_label == ESCALATED_APP_LABEL

    return getattr(model_or_label._meta, "app_label", None) == ESCALATED_APP_LABEL


class EscalatedRouter:
    """Routes the ``escalated`` app to ``ESCALATED["DATABASE"]``.

    Returning ``None`` from a router method means "no opinion", which lets the
    next router -- or Django's default -- decide. Every method here returns
    ``None`` for models that are not Escalated's, and for every model at all
    when no database is configured, so adding this router to a project that has
    not set one changes nothing.
    """

    def db_for_read(self, model, **hints):
        if _is_escalated(model):
            return _escalated_database()

        return None

    def db_for_write(self, model, **hints):
        if _is_escalated(model):
            return _escalated_database()

        return None

    def allow_relation(self, obj1, obj2, **hints):
        """Permit a relation when either side is one of Escalated's.

        Django refuses relations between objects on different databases unless
        a router says otherwise. A ticket's assignee, a follower's user and an
        audit log's causer are all host objects, and the whole point of the
        setting is that they need not live in the same place.

        This governs single-object traversal, which Django resolves with a
        second query and which therefore works across databases. It cannot make
        a JOIN span two connections -- nothing can. See ``escalated.db`` for how
        the app avoids emitting those.
        """
        database = _escalated_database()

        if database is None:
            return None

        if _is_escalated(obj1.__class__) or _is_escalated(obj2.__class__):
            return True

        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Keep Escalated's tables on its own database, and only there.

        Both directions matter. Without the second clause the tables would be
        created on the configured database *and* left behind on ``default``,
        where the app would never read them again.
        """
        database = _escalated_database()

        if database is None:
            return None

        if _is_escalated(app_label):
            return db == database

        if db == database:
            return False

        return None
