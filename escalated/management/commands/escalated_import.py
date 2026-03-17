"""
Management command: ``escalated_import``

Run a platform import from the command line.

Usage examples::

    # Start a new Zendesk import (will prompt for credentials)
    python manage.py escalated_import zendesk --token=abc123 --subdomain=acme

    # Resume a paused or failed job
    python manage.py escalated_import zendesk --resume=<job-uuid>

    # List all import jobs
    python manage.py escalated_import --list

    # Inspect current field mappings for a job
    python manage.py escalated_import zendesk --mapping=<job-uuid>

    # Pass credentials as a JSON string (useful in scripts)
    python manage.py escalated_import zendesk --credentials='{"token":"abc","subdomain":"acme"}'
"""

import json
import sys

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.translation import gettext as _

from escalated.models import ImportJob
from escalated.services.import_service import ImportService


class Command(BaseCommand):
    help = "Run or resume a platform import job."

    def add_arguments(self, parser):
        parser.add_argument(
            "platform",
            nargs="?",
            default=None,
            help=_("Platform slug to import from, e.g. 'zendesk', 'freshdesk'."),
        )
        parser.add_argument(
            "--resume",
            metavar="JOB_UUID",
            default=None,
            help=_("UUID of a paused or failed ImportJob to resume."),
        )
        parser.add_argument(
            "--list",
            action="store_true",
            default=False,
            help=_("List all import jobs and their current status."),
        )
        parser.add_argument(
            "--mapping",
            metavar="JOB_UUID",
            default=None,
            help=_("Show the field mappings stored on a specific job."),
        )
        parser.add_argument(
            "--credentials",
            metavar="JSON",
            default=None,
            help=_(
                "Credentials as a JSON string, e.g. "
                '\'{"token":"abc","subdomain":"acme"}\'. '
                "If omitted, any named --<key>=<value> flags are used."
            ),
        )

    def handle(self, *args, **options):
        service = ImportService()

        # ------------------------------------------------------------------
        # --list
        # ------------------------------------------------------------------
        if options["list"]:
            self._list_jobs()
            return

        # ------------------------------------------------------------------
        # --mapping
        # ------------------------------------------------------------------
        if options["mapping"]:
            self._show_mapping(options["mapping"])
            return

        # ------------------------------------------------------------------
        # --resume
        # ------------------------------------------------------------------
        if options["resume"]:
            self._resume_job(service, options["resume"])
            return

        # ------------------------------------------------------------------
        # New import
        # ------------------------------------------------------------------
        platform = options.get("platform")
        if not platform:
            raise CommandError(
                _("Please provide a platform slug, e.g.: escalated_import zendesk")
            )

        adapter = service.resolve_adapter(platform)
        if not adapter:
            available = [a.name() for a in service.available_adapters()]
            raise CommandError(
                _(
                    "No adapter found for platform '%(platform)s'. "
                    "Available: %(available)s"
                )
                % {"platform": platform, "available": ", ".join(available) or "(none)"}
            )

        credentials = self._parse_credentials(options, adapter)

        job = ImportJob.objects.create(
            platform=platform,
            status="pending",
            credentials=credentials,
        )
        self.stdout.write(
            self.style.SUCCESS(_("Created import job %(id)s.") % {"id": job.id})
        )

        # Test connection
        job.transition_to("authenticating")
        try:
            ok = service.test_connection(job)
        except Exception as exc:
            job.transition_to("failed")
            raise CommandError(_("Connection test failed: %(err)s") % {"err": exc})

        if not ok:
            job.transition_to("failed")
            raise CommandError(_("Connection test returned False — check credentials."))

        self.stdout.write(self.style.SUCCESS(_("Connection test passed.")))
        job.transition_to("mapping")
        job.transition_to("importing")

        self._run(service, job)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run(self, service: ImportService, job: ImportJob) -> None:
        """Execute the import and stream progress to stdout."""

        def on_progress(entity_type: str, progress_data: dict):
            processed = progress_data.get("processed", 0)
            total = progress_data.get("total", 0)
            skipped = progress_data.get("skipped", 0)
            failed = progress_data.get("failed", 0)
            pct = f"{processed / total * 100:.1f}%" if total else "?"
            self.stdout.write(
                f"  {entity_type}: {processed}/{total} ({pct}) "
                f"skipped={skipped} failed={failed}",
                ending="\r",
            )
            self.stdout.flush()

        self.stdout.write(_("Starting import for job %(id)s…") % {"id": job.id})
        try:
            service.run(job, on_progress=on_progress)
        except Exception as exc:
            raise CommandError(_("Import failed: %(err)s") % {"err": exc})

        job.refresh_from_db()

        if job.status == "paused":
            self.stdout.write(
                self.style.WARNING(
                    _("\nImport paused. Resume with: "
                      "--resume=%(id)s") % {"id": job.id}
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    _("\nImport completed successfully (job %(id)s).") % {"id": job.id}
                )
            )
            for entity_type, progress_data in (job.progress or {}).items():
                self.stdout.write(
                    f"  {entity_type}: "
                    f"processed={progress_data.get('processed', 0)} "
                    f"skipped={progress_data.get('skipped', 0)} "
                    f"failed={progress_data.get('failed', 0)}"
                )

    def _resume_job(self, service: ImportService, job_uuid: str) -> None:
        try:
            job = ImportJob.objects.get(pk=job_uuid)
        except ImportJob.DoesNotExist:
            raise CommandError(_("ImportJob '%(id)s' not found.") % {"id": job_uuid})

        if not job.is_resumable():
            raise CommandError(
                _(
                    "Job %(id)s is not resumable (status: %(status)s). "
                    "Only 'paused' or 'failed' jobs can be resumed."
                )
                % {"id": job_uuid, "status": job.status}
            )

        self.stdout.write(
            _("Resuming job %(id)s (platform: %(platform)s, status: %(status)s)…")
            % {"id": job.id, "platform": job.platform, "status": job.status}
        )
        self._run(service, job)

    def _list_jobs(self) -> None:
        jobs = ImportJob.objects.order_by("-created_at")[:50]
        if not jobs:
            self.stdout.write(_("No import jobs found."))
            return

        self.stdout.write(
            f"{'ID':<38}  {'Platform':<15}  {'Status':<15}  {'Created'}"
        )
        self.stdout.write("-" * 90)
        for job in jobs:
            self.stdout.write(
                f"{str(job.id):<38}  {job.platform:<15}  {job.status:<15}  "
                f"{job.created_at.strftime('%Y-%m-%d %H:%M') if job.created_at else ''}"
            )

    def _show_mapping(self, job_uuid: str) -> None:
        try:
            job = ImportJob.objects.get(pk=job_uuid)
        except ImportJob.DoesNotExist:
            raise CommandError(_("ImportJob '%(id)s' not found.") % {"id": job_uuid})

        self.stdout.write(
            json.dumps(job.field_mappings or {}, indent=2, default=str)
        )

    def _parse_credentials(self, options: dict, adapter) -> dict:
        """
        Build a credentials dict from --credentials JSON or individual
        --<field_name> flags.
        """
        if options.get("credentials"):
            try:
                return json.loads(options["credentials"])
            except json.JSONDecodeError as exc:
                raise CommandError(
                    _("Invalid JSON for --credentials: %(err)s") % {"err": exc}
                )

        # Fall back: prompt interactively for each declared credential field
        creds = {}
        for field_spec in adapter.credential_fields():
            name = field_spec["name"]
            label = field_spec.get("label", name)
            is_secret = field_spec.get("type") == "password"

            if is_secret:
                import getpass
                value = getpass.getpass(f"{label}: ")
            else:
                value = input(f"{label}: ")

            creds[name] = value

        return creds
