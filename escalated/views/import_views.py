"""
Admin views for the platform import wizard.

The wizard, on escalated-laravel's paths and props (Admin ImportController):

GET  /admin/import/                              Index     (adapters, jobs)
GET  /admin/import/<platform>/connect/           Connect   (credential form)
POST /admin/import/<platform>/test-connection/   JSON {success[, error]}; keeps tested credentials
GET  /admin/import/<platform>/mapping/           Mapping   (defaults + source fields per entity)
POST /admin/import/<platform>/review/            Review    (echo of the choices; writes nothing)
POST /admin/import/<platform>/start/             creates the job and queues the run
GET  /admin/import/progress/<uuid>/              Progress  (job)
GET  /admin/import/status/<uuid>/                JSON poll
POST /admin/import/{pause,resume,cancel}/<uuid>/

Sources come from the ``import.adapters`` filter; core ships none. Tested
credentials wait in the session, encrypted, until the import starts, and are
never sent to the browser.

The earlier job-first routes (``create/``, ``store/``, ``<uuid>/...``) still
answer for existing callers.

All views require admin access.
"""

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import (
    Http404,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
    JsonResponse,
)
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.translation import gettext as _

from escalated.models import EncryptedJSONField, ImportJob
from escalated.permissions import is_admin
from escalated.rendering import render_page
from escalated.request_data import request_data
from escalated.services import import_runner
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
# Serialisation and helpers
# ---------------------------------------------------------------------------


def _iso(value):
    return value.isoformat() if value else None


def job_json(job):
    """The job as the screens read it.

    Laravel sends the model as is. Its credentials are left out here: they are
    a secret, and no screen reads them.
    """
    return {
        "id": str(job.id),
        "user_id": job.user_id,
        "platform": job.platform,
        "status": job.status,
        "field_mappings": job.field_mappings or {},
        "progress": job.progress or {},
        "error_log": job.error_log or [],
        "started_at": _iso(job.started_at),
        "completed_at": _iso(job.completed_at),
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
    }


def _adapter_json(adapter):
    return {
        "name": adapter.name(),
        "display_name": adapter.display_name(),
        "credential_fields": adapter.credential_fields(),
    }


def _adapter_or_404(platform):
    adapter = ImportService().resolve_adapter(platform)
    if adapter is None:
        raise Http404(f"Import adapter not found: {platform}")
    return adapter


def _body(request):
    """The posted fields, structured: Inertia and fetch() post JSON."""
    if request.content_type == "application/json":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return {}
        return body if isinstance(body, dict) else {}
    return request.POST


def _dict(value):
    return value if isinstance(value, dict) else {}


_SEALER = EncryptedJSONField()


def _session_key(platform):
    return f"escalated.import.{platform}.credentials"


def _store_credentials(request, platform, credentials):
    request.session[_session_key(platform)] = _SEALER.get_prep_value(credentials)


def _stored_credentials(request, platform):
    sealed = request.session.get(_session_key(platform))
    if not sealed:
        return None
    try:
        credentials = _SEALER.to_python(sealed)
    except Exception:  # tampered, or sealed under another SECRET_KEY
        return None
    return credentials if isinstance(credentials, dict) else None


def _to_connect(platform):
    return redirect("escalated:admin_import_connect", platform=platform)


def _to_progress(job):
    return redirect("escalated:admin_import_progress_page", job_uuid=job.id)


def _post_only(request):
    return None if request.method == "POST" else HttpResponseNotAllowed(["POST"])


def _job_or_404(job_uuid):
    job = _get_job(job_uuid)
    if job is None:
        raise Http404("Import job not found.")
    return job


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------


@login_required
def import_index(request):
    """Index: the registered sources and the 20 most recent jobs."""
    check = _require_admin(request)
    if check:
        return check

    return render_page(
        request,
        "Escalated/Admin/Import/Index",
        props={
            "adapters": [_adapter_json(a) for a in ImportService().available_adapters()],
            "jobs": [job_json(j) for j in ImportJob.objects.order_by("-created_at")[:20]],
        },
    )


@login_required
def import_connect(request, platform):
    """Connect: the credential form for one source."""
    check = _require_admin(request)
    if check:
        return check

    adapter = _adapter_or_404(platform)
    return render_page(
        request,
        "Escalated/Admin/Import/Connect",
        props={
            "platform": adapter.name(),
            "display_name": adapter.display_name(),
            "credential_fields": adapter.credential_fields(),
        },
    )


@login_required
def import_test_connection(request, platform):
    """Try the credentials; keep them, server side, when they work."""
    check = _require_admin(request) or _post_only(request)
    if check:
        return check

    adapter = _adapter_or_404(platform)
    posted = _dict(_body(request).get("credentials"))
    credentials = {str(k): "" if v is None else str(v) for k, v in posted.items()}

    try:
        success = bool(adapter.test_connection(credentials))
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=422)

    if success:
        _store_credentials(request, adapter.name(), credentials)

    return JsonResponse({"success": success})


def _render_mapping(request, adapter, credentials):
    entity_types = adapter.entity_types()
    return render_page(
        request,
        "Escalated/Admin/Import/Mapping",
        props={
            "platform": adapter.name(),
            "display_name": adapter.display_name(),
            "entity_types": entity_types,
            "mappings": {
                entity_type: {
                    "defaults": adapter.default_field_mappings(entity_type),
                    "source_fields": adapter.available_source_fields(entity_type, credentials),
                }
                for entity_type in entity_types
            },
        },
    )


@login_required
def import_platform_mapping(request, platform):
    """Mapping: each entity type's default mappings and source fields."""
    check = _require_admin(request)
    if check:
        return check

    adapter = _adapter_or_404(platform)
    credentials = _stored_credentials(request, adapter.name())
    if credentials is None:
        return _to_connect(adapter.name())

    return _render_mapping(request, adapter, credentials)


@login_required
def import_review(request, platform):
    """Review: the dry run. Shows what will be imported and how; writes nothing."""
    check = _require_admin(request) or _post_only(request)
    if check:
        return check

    body = _body(request)
    if isinstance(body, dict):
        entity_types = body.get("entity_types")
    else:
        entity_types = body.getlist("entity_types")
    return render_page(
        request,
        "Escalated/Admin/Import/Review",
        props={
            "platform": platform,
            "field_mappings": _dict(body.get("field_mappings")),
            "entity_types": [str(t) for t in entity_types or []],
        },
    )


@login_required
def import_start(request, platform):
    """Create the job from the tested credentials and queue the run."""
    check = _require_admin(request) or _post_only(request)
    if check:
        return check

    adapter = _adapter_or_404(platform)
    credentials = _stored_credentials(request, adapter.name())
    if credentials is None:
        return _to_connect(adapter.name())

    job = ImportJob.objects.create(
        user=request.user,
        platform=adapter.name(),
        status=ImportJob.Status.MAPPING,
        credentials=credentials,
        field_mappings=_dict(_body(request).get("field_mappings")),
    )
    # The job holds them now, encrypted.
    request.session.pop(_session_key(adapter.name()), None)

    import_runner.dispatch(job)
    logger.info("ImportJob %s started for platform '%s' by user %s.", job.id, platform, request.user)

    return _to_progress(job)


@login_required
def import_progress_page(request, job_uuid):
    """Progress: the job the screen polls."""
    check = _require_admin(request)
    if check:
        return check

    return render_page(request, "Escalated/Admin/Import/Progress", props={"job": job_json(_job_or_404(job_uuid))})


@login_required
def import_status(request, job_uuid):
    """The Progress screen's poll."""
    check = _require_admin(request)
    if check:
        return check

    job = _job_or_404(job_uuid)
    return JsonResponse(
        {
            "status": job.status,
            "progress": job.progress or {},
            "error_log": (job.error_log or [])[-50:],
            "started_at": _iso(job.started_at),
            "completed_at": _iso(job.completed_at),
        }
    )


@login_required
def import_pause_job(request, job_uuid):
    """Pause an importing job; the run stops between batches."""
    check = _require_admin(request) or _post_only(request)
    if check:
        return check

    job = _job_or_404(job_uuid)
    if job.status == ImportJob.Status.IMPORTING:
        job.status = ImportJob.Status.PAUSED
        job.save(update_fields=["status", "updated_at"])
    return _to_progress(job)


@login_required
def import_resume(request, job_uuid):
    """Queue a paused or failed job again; a failed one goes back through mapping."""
    check = _require_admin(request) or _post_only(request)
    if check:
        return check

    job = _job_or_404(job_uuid)
    if job.is_resumable():
        if job.status == ImportJob.Status.FAILED:
            job.transition_to(ImportJob.Status.MAPPING)
        import_runner.dispatch(job)
    return _to_progress(job)


@login_required
def import_cancel(request, job_uuid):
    """Stop a job for good and drop its credentials."""
    check = _require_admin(request) or _post_only(request)
    if check:
        return check

    job = _job_or_404(job_uuid)
    job.status = ImportJob.Status.FAILED
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "completed_at", "updated_at"])
    job.purge_credentials()
    return _to_progress(job)


# ---------------------------------------------------------------------------
# Create — choose platform (GET form) / submit (POST)
# ---------------------------------------------------------------------------


@login_required
def import_create(request):
    """The earlier platform-selection step: the Index screen lists the sources."""
    return import_index(request)


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

    platform = request_data(request).get("platform") or (
        request.content_type == "application/json" and __import__("json").loads(request.body or "{}").get("platform")
    )

    service = ImportService()
    adapter = service.resolve_adapter(platform) if platform else None
    if not adapter:
        return redirect("escalated:admin_import_index")

    # Collect credential values from POST
    credentials = {}
    for field_spec in adapter.credential_fields():
        name = field_spec["name"]
        credentials[name] = request_data(request).get(name, "")

    job = ImportJob.objects.create(
        user=request.user,
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
    """The earlier job-first mapping step, with the Mapping screen's props."""
    check = _require_admin(request)
    if check:
        return check

    job = _get_job(job_uuid)
    if not job:
        return HttpResponseNotFound(_("Import job not found."))

    adapter = ImportService().resolve_adapter(job.platform)
    if not adapter:
        return HttpResponseNotFound(_("Adapter not found for this job."))

    return _render_mapping(request, adapter, job.credentials or {})


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
    Start or resume the import for a job, in the background (see
    :mod:`escalated.services.import_runner`).
    """
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed."))

    job = _get_job(job_uuid)
    if not job:
        return HttpResponseNotFound(_("Import job not found."))

    import_runner.dispatch(job)

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
    """The earlier job detail route: the Progress screen."""
    return import_progress_page(request, job_uuid)


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
