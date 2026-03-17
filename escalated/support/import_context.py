"""
Import suppression context.

All Escalated signal handlers, SLA timers, automations, and notifications
check ``ImportContext.is_importing()`` and skip their logic while an import
is running, preventing spurious side-effects from flooding the system with
thousands of events during a bulk import.

Usage::

    from escalated.support.import_context import ImportContext

    with ImportContext.suppress_ctx():
        run_the_import()

    # Or via the callable form used by ImportService:
    ImportContext.suppress(lambda: run_the_import())

    # Guard inside a signal handler:
    from escalated.support.import_context import ImportContext

    @receiver(ticket_created)
    def on_ticket_created(sender, ticket, user, **kwargs):
        if ImportContext.is_importing():
            return
        ...
"""

import threading

_local = threading.local()


class ImportContext:
    """Thread-local flag that suppresses Escalated side-effects during import."""

    @staticmethod
    def is_importing() -> bool:
        """Return True if the current thread is inside an active import."""
        return getattr(_local, "importing", False)

    @staticmethod
    def suppress(callback):
        """
        Run *callback* with import suppression active and return its result.

        The flag is always cleared in a ``finally`` block so it can never
        leak even if the callback raises.
        """
        _local.importing = True
        try:
            return callback()
        finally:
            _local.importing = False

    class suppress_ctx:
        """Context-manager alternative to ``ImportContext.suppress()``."""

        def __enter__(self):
            _local.importing = True
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            _local.importing = False
            return False  # never suppress exceptions
