"""
Runs an import outside the request that started it.

escalated-laravel queues ``ImportService::run`` on its job queue. Django has no
queue of its own, so by default the run goes to a daemon thread once the
starting transaction commits. A host with a task queue (Celery, Django-Q, RQ,
...) takes it over by registering the ``import.run_async`` action::

    from escalated.hooks import add_action

    add_action("import.run_async", lambda job: run_import_task.delay(str(job.id)))

and calling :func:`run_job` from its task.

A paused run returns early and is queued again by resume; the source maps make
the second run skip whatever the first one already wrote.
"""

import logging
import threading

from django.db import close_old_connections, transaction

from escalated.hooks import do_action, has_action

logger = logging.getLogger("escalated.import")


def run_job(job_id) -> None:
    """Run (or resume) the import job with this id. Failures mark it failed."""
    from escalated.models import ImportJob
    from escalated.services.import_service import ImportService

    job = ImportJob.objects.filter(pk=job_id).first()
    if job is None or job.status == ImportJob.Status.COMPLETED:
        return

    try:
        ImportService().run(job)
    except Exception:
        logger.exception("Import job %s failed.", job_id)
        ImportJob.objects.filter(pk=job_id).update(status=ImportJob.Status.FAILED)


def _run_in_thread(job_id) -> None:
    try:
        run_job(job_id)
    finally:
        # This thread's connections are its own; leave none open behind it.
        if threading.current_thread() is not threading.main_thread():
            close_old_connections()


def dispatch(job) -> None:
    """Queue *job* to run in the background."""
    if has_action("import.run_async"):
        do_action("import.run_async", job)
        return

    job_id = job.pk
    transaction.on_commit(
        lambda: threading.Thread(
            target=_run_in_thread, args=(job_id,), daemon=True, name=f"escalated-import-{job_id}"
        ).start()
    )
