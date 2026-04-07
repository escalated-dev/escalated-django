"""
Admin views for the platform import wizard.

Route summary
-------------
GET  /admin/import/                       — list all jobs          (import_index)
GET  /admin/import/create/               — step 1: choose platform (import_create)
POST /admin/import/store/                — step 1 submit           (import_store)
POST /admin/import/<uuid>/authenticate/  — step 2: test connection (import_authenticate)
GET  /admin/import/<uuid>/mapping/       — step 3: field mapping UI (import_mapping)
POST /admin/import/<uuid>/mapping/save/  — step 3 submit           (import_mapping_save)
POST /admin/import/<uuid>/run/           — kick off / resume run   (import_run)
POST /admin/import/<uuid>/pause/         — pause a running job     (import_pause)
GET  /admin/import/<uuid>/progress/      — JSON progress endpoint  (import_progress)
GET  /admin/import/<uuid>/               — job detail page         (import_show)
POST /admin/import/<uuid>/delete/        — delete a job            (import_delete)

All views require admin access.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import (
    HttpResponseForbidden,
    HttpResponseNotFound,
    JsonResponse,
)
from django.shortcuts import redirect
from django.utils.translation import gettext as _

from escalated.models import ImportJob
from escalated.permissions import is_admin
from escalated.rendering import render_page
from escalated.services.import_service import ImportService

logger = logging.getLogger("escalated.import")


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


def _require_admin(request):
    if not request.user.is_authenticated:
        return redirect("login")
    if not is_admin(request.user):
        return HttpResponseForbidden(_("Admin access required."))
    return None


def _get_job(job_uuid):
    try:
        return ImportJob.objects.get(pk=job_uuid)
    except (ImportJob.DoesNotExist, ValueError):
        return None


# ---------------------------------------------------------------------------
# Index — list all jobs
# ---------------------------------------------------------------------------


@login_required
def import_index(request):
    """Display a list of all import jobs."""
    check = _require_admin(request)
    if check:
        return check

    service = ImportService()
    adapters = [{"name": a.name(), "display_name": a.display_name()} for a in service.available_adapters()]

    jobs = list(
        ImportJob.objects.order_by("-created_at").values(
            "id",
            "platform",
            "status",
            "started_at",
            "completed_at",
            "created_at",
        )[:100]
    )
    # Coerce UUIDs and datetimes to strings for JSON serialisation
    for job in jobs:
        job["id"] = str(job["id"])
        for ts_field in ("started_at", "completed_at", "created_at"):
            if job[ts_field]:
                job[ts_field] = job[ts_field].isoformat()

    return render_page(
        request,
        "Escalated/Admin/Import/Index",
        props={
            "jobs": jobs,
            "adapters": adapters,
        },
    )


# ---------------------------------------------------------------------------
# Create — choose platform (GET form) / submit (POST)
# ---------------------------------------------------------------------------


@login_required
def import_create(request):
    """Display the platform-selection form."""
    check = _require_admin(request)
    if check:
        return check

    service = ImportService()
    adapters = [
        {
            "name": a.name(),
            "display_name": a.display_name(),
            "credential_fields": a.credential_fields(),
        }
        for a in service.available_adapters()
    ]

    return render_page(
        request,
        "Escalated/Admin/Import/Create",
        props={
            "adapters": adapters,
        },
    )


@login_required
def import_store(request):
    """
    Create a new ImportJob for the chosen platform and store the credentials.

    Expects POST body: ``platform``, plus one key per credential field.
    """
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed."))

    platform = request.POST.get("platform") or (
        request.content_type == "application/json" and __import__("json").loads(request.body or "{}").get("platform")
    )

    service = ImportService()
    adapter = service.resolve_adapter(platform) if platform else None
    if not adapter:
        return redirect("escalated:admin_import_create")

    # Collect credential values from POST
    credentials = {}
    for field_spec in adapter.credential_fields():
        name = field_spec["name"]
        credentials[name] = request.POST.get(name, "")

    job = ImportJob.objects.create(
        platform=platform,
        status="pending",
        credentials=credentials,
    )
    logger.info("ImportJob %s created for platform '%s' by user %s.", job.id, platform, request.user)

    return redirect("escalated:admin_import_authenticate", job_uuid=job.id)


# ---------------------------------------------------------------------------
# Authenticate — test connection and advance to mapping
# ---------------------------------------------------------------------------


@login_required
def import_authenticate(request, job_uuid):
    """Test the stored credentials and advance the job to 'mapping' status."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed."))

    job = _get_job(job_uuid)
    if not job:
        return HttpResponseNotFound(_("Import job not found."))

    service = ImportService()
    job.transition_to("authenticating")

    try:
        ok = service.test_connection(job)
    except Exception as exc:
        job.transition_to("failed")
        logger.error("Connection test failed for job %s: %s", job.id, exc)
        return redirect("escalated:admin_import_show", job_uuid=job.id)

    if not ok:
        job.transition_to("failed")
        return redirect("escalated:admin_import_show", job_uuid=job.id)

    job.transition_to("mapping")
    return redirect("escalated:admin_import_mapping", job_uuid=job.id)


# ---------------------------------------------------------------------------
# Mapping — display / save field mappings
# ---------------------------------------------------------------------------


@login_required
def import_mapping(request, job_uuid):
    """Display the field-mapping configuration page."""
    check = _require_admin(request)
    if check:
        return check

    job = _get_job(job_uuid)
    if not job:
        return HttpResponseNotFound(_("Import job not found."))

    service = ImportService()
    adapter = service.resolve_adapter(job.platform)
    if not adapter:
        return HttpResponseNotFound(_("Adapter not found for this job."))

    entity_types = adapter.entity_types()
    mappings = job.field_mappings or {}

    # Build per-entity default + current mappings for the UI
    mapping_data = {}
    for et in entity_types:
        mapping_data[et] = {
            "default": adapter.default_field_mappings(et),
            "current": mappings.get(et, adapter.default_field_mappings(et)),
        }

    return render_page(
        request,
        "Escalated/Admin/Import/Mapping",
        props={
            "job": {
                "id": str(job.id),
                "platform": job.platform,
                "status": job.status,
            },
            "entity_types": entity_types,
            "mapping_data": mapping_data,
        },
    )


@login_required
def import_mapping_save(request, job_uuid):
    """Save field mappings and ready the job for import."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed."))

    job = _get_job(job_uuid)
    if not job:
        return HttpResponseNotFound(_("Import job not found."))

    import json as _json

    try:
        body = _json.loads(request.body or "{}")
        mappings = body.get("mappings", {})
    except _json.JSONDecodeError:
        mappings = {}

    job.field_mappings = mappings
    job.save(update_fields=["field_mappings", "updated_at"])

    return redirect("escalated:admin_import_show", job_uuid=job.id)


# ---------------------------------------------------------------------------
# Run — kick off or resume an import
# ---------------------------------------------------------------------------


@login_required
def import_run(request, job_uuid):
    """
    Start or resume the import for a job.

    This view triggers the import synchronously in the request/response
    cycle for simplicity.  Production deployments should offload this to
    a background worker (Celery, Django-Q, etc.) and stream progress via
    the ``import_progress`` endpoint.
    """
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed."))

    job = _get_job(job_uuid)
    if not job:
        return HttpResponseNotFound(_("Import job not found."))

    service = ImportService()
    try:
        service.run(job)
    except Exception as exc:
        logger.error("Import run failed for job %s: %s", job.id, exc)

    return redirect("escalated:admin_import_show", job_uuid=job.id)


# ---------------------------------------------------------------------------
# Pause — request a pause between batches
# ---------------------------------------------------------------------------


@login_required
def import_pause(request, job_uuid):
    """Request a graceful pause of a running import."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed."))

    job = _get_job(job_uuid)
    if not job:
        return HttpResponseNotFound(_("Import job not found."))

    if job.status == "importing":
        try:
            job.transition_to("paused")
        except ValueError:
            pass  # Race condition — already completed/failed

    return redirect("escalated:admin_import_show", job_uuid=job.id)


# ---------------------------------------------------------------------------
# Progress — JSON polling endpoint
# ---------------------------------------------------------------------------


@login_required
def import_progress(request, job_uuid):
    """Return current progress as JSON for the UI to poll."""
    check = _require_admin(request)
    if check:
        return check

    job = _get_job(job_uuid)
    if not job:
        return HttpResponseNotFound(_("Import job not found."))

    return JsonResponse(
        {
            "id": str(job.id),
            "status": job.status,
            "progress": job.progress or {},
            "error_count": len(job.error_log or []),
        }
    )


# ---------------------------------------------------------------------------
# Show — job detail page
# ---------------------------------------------------------------------------


@login_required
def import_show(request, job_uuid):
    """Display the detail page for a single import job."""
    check = _require_admin(request)
    if check:
        return check

    job = _get_job(job_uuid)
    if not job:
        return HttpResponseNotFound(_("Import job not found."))

    service = ImportService()
    adapter = service.resolve_adapter(job.platform)
    entity_types = adapter.entity_types() if adapter else []

    return render_page(
        request,
        "Escalated/Admin/Import/Show",
        props={
            "job": {
                "id": str(job.id),
                "platform": job.platform,
                "status": job.status,
                "progress": job.progress or {},
                "error_log": (job.error_log or [])[:100],  # cap for page load
                "field_mappings": job.field_mappings or {},
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "is_resumable": job.is_resumable(),
            },
            "entity_types": entity_types,
        },
    )


# ---------------------------------------------------------------------------
# Delete — remove a job and its source maps
# ---------------------------------------------------------------------------


@login_required
def import_delete(request, job_uuid):
    """Permanently delete an import job and all associated source maps."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed."))

    job = _get_job(job_uuid)
    if not job:
        return HttpResponseNotFound(_("Import job not found."))

    if job.status == "importing":
        # Refuse to delete a job that is actively running
        return redirect("escalated:admin_import_show", job_uuid=job.id)

    job.delete()
    logger.info("ImportJob %s deleted by user %s.", job_uuid, request.user)

    return redirect("escalated:admin_import_index")
