"""
ImportService — orchestrates a full platform import.

This service is called both from the management command (CLI) and the
admin web UI.  It is deliberately stateless: callers pass in the
``ImportJob`` they want to run, and optionally an ``on_progress`` callback
that receives live progress updates after every batch.

Adapter discovery
-----------------
Adapters register themselves via the ``import.adapters`` filter hook::

    from escalated.hooks import add_filter
    from myapp.adapters import MyAdapter

    add_filter("import.adapters", lambda adapters: adapters + [MyAdapter()])

Import suppression
------------------
All Escalated signal handlers check ``ImportContext.is_importing()`` and
skip side-effects (notifications, SLA timers, automations, webhooks) while
an import is running.
"""

import logging
from collections.abc import Callable

from django.apps import apps
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify

from escalated.hooks import apply_filters, do_action
from escalated.models import ImportJob, ImportSourceMap
from escalated.support.import_context import ImportContext

logger = logging.getLogger("escalated.import")


class ImportService:
    """Orchestrates discovery, extraction, and persistence for import jobs."""

    # ------------------------------------------------------------------
    # Adapter registry
    # ------------------------------------------------------------------

    def available_adapters(self) -> list:
        """
        Return all registered import adapters.

        Adapters are collected via the ``import.adapters`` filter so that
        plugins can add their own without modifying core code.
        """
        return apply_filters("import.adapters", [])

    def resolve_adapter(self, platform: str):
        """
        Find the adapter whose :py:meth:`name` matches *platform*.

        Returns ``None`` if no matching adapter is registered.
        """
        for adapter in self.available_adapters():
            if adapter.name() == platform:
                return adapter
        return None

    # ------------------------------------------------------------------
    # Connection test (used by the credential step in the UI)
    # ------------------------------------------------------------------

    def test_connection(self, job: ImportJob) -> bool:
        """Test credentials stored on *job* against the live API."""
        adapter = self.resolve_adapter(job.platform)
        if not adapter:
            raise RuntimeError(f"No adapter found for platform '{job.platform}'.")
        return adapter.test_connection(job.credentials)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(
        self,
        job: ImportJob,
        on_progress: Callable[[str, dict], None] | None = None,
    ) -> None:
        """
        Execute (or resume) the import for *job*.

        Args:
            job:         The :class:`~escalated.models.ImportJob` to run.
            on_progress: Optional callback invoked after every batch with
                         ``(entity_type: str, progress_data: dict)``.
                         Useful for streaming progress to the CLI or a
                         WebSocket.

        The method transitions the job status, iterates over entity types,
        delegates extraction and persistence, and marks the job completed
        (or leaves it paused if a pause was requested mid-run).
        """
        adapter = self.resolve_adapter(job.platform)
        if not adapter:
            job.status = "failed"
            job.save(update_fields=["status", "updated_at"])
            raise RuntimeError(f"No adapter found for platform '{job.platform}'.")

        # Support resume: only transition if not already importing
        if job.status != "importing":
            job.transition_to("importing")

        if not job.started_at:
            job.started_at = timezone.now()
            job.save(update_fields=["started_at", "updated_at"])

        # Let the adapter know which job it belongs to (for cross-referencing)
        if hasattr(adapter, "set_job_id"):
            adapter.set_job_id(str(job.id))

        def _do_import():
            for entity_type in adapter.entity_types():
                # Honour pause requests between entity types
                job.refresh_from_db()
                if job.status == "paused":
                    return
                self._import_entity_type(job, adapter, entity_type, on_progress)

        ImportContext.suppress(_do_import)

        job.refresh_from_db()

        if job.status == "paused":
            return  # Paused mid-import — do not mark completed

        job.status = "completed"
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at", "updated_at"])

        job.purge_credentials()

        # Notify listeners (e.g. search re-index)
        do_action("import.completed", job)
        logger.info("Import job %s completed (%s).", job.id, job.platform)

    # ------------------------------------------------------------------
    # Entity-level loop
    # ------------------------------------------------------------------

    def _import_entity_type(
        self,
        job: ImportJob,
        adapter,
        entity_type: str,
        on_progress: Callable | None,
    ) -> None:
        cursor = job.get_entity_cursor(entity_type)
        progress = (job.progress or {}).get(entity_type, {})
        processed = progress.get("processed", 0)
        skipped = progress.get("skipped", 0)
        failed = progress.get("failed", 0)

        while True:
            result = adapter.extract(entity_type, job.credentials, cursor)

            if result.total_count is not None:
                job.update_entity_progress(entity_type, total=result.total_count)

            for record in result.records:
                source_id = record.get("source_id")
                if not source_id:
                    failed += 1
                    continue

                if ImportSourceMap.has_been_imported(job.id, entity_type, source_id):
                    skipped += 1
                    continue

                try:
                    escalated_id = self._persist_record(job, entity_type, record)
                    ImportSourceMap.objects.create(
                        import_job=job,
                        entity_type=entity_type,
                        source_id=source_id,
                        escalated_id=str(escalated_id),
                    )
                    processed += 1
                except Exception as exc:
                    failed += 1
                    job.append_error(entity_type, source_id, str(exc))
                    logger.warning(
                        "Import error [job=%s entity=%s source_id=%s]: %s",
                        job.id,
                        entity_type,
                        source_id,
                        exc,
                    )

            cursor = result.cursor

            job.update_entity_progress(
                entity_type,
                processed=processed,
                skipped=skipped,
                failed=failed,
                cursor=cursor,
            )

            if on_progress:
                on_progress(entity_type, (job.progress or {}).get(entity_type, {}))

            if result.is_exhausted():
                break

            # Honour pause requests between batches
            job.refresh_from_db()
            if job.status == "paused":
                return

    # ------------------------------------------------------------------
    # Persistence — one method per entity type
    # ------------------------------------------------------------------

    def _persist_record(self, job: ImportJob, entity_type: str, record: dict):
        """Dispatch to the correct persist method and return the new PK."""
        mappings = (job.field_mappings or {}).get(entity_type, {})

        dispatch = {
            "agents": self._persist_agent,
            "tags": self._persist_tag,
            "custom_fields": self._persist_custom_field,
            "contacts": self._persist_contact,
            "departments": self._persist_department,
            "tickets": self._persist_ticket,
            "replies": self._persist_reply,
            "attachments": self._persist_attachment,
            "satisfaction_ratings": self._persist_satisfaction_rating,
        }

        handler = dispatch.get(entity_type)
        if not handler:
            raise RuntimeError(f"Unknown entity type: {entity_type}")

        # Ticket and reply handlers need the job for cross-referencing
        if entity_type in ("tickets", "replies", "attachments", "satisfaction_ratings"):
            return handler(job, record, mappings)
        return handler(record, mappings)

    # ------------------------------------------------------------------

    def _persist_tag(self, record: dict, mappings: dict):
        Tag = apps.get_model("escalated", "Tag")
        tag, _ = Tag.objects.get_or_create(
            slug=slugify(record["name"]),
            defaults={"name": record["name"]},
        )
        return tag.pk

    def _persist_agent(self, record: dict, mappings: dict):
        User = get_user_model()
        try:
            user = User.objects.get(email=record["email"])
        except User.DoesNotExist:
            raise RuntimeError(f"Agent with email '{record['email']}' not found in host application.")
        return user.pk

    def _persist_contact(self, record: dict, mappings: dict):
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            email=record["email"],
            defaults={"name": record.get("name", record["email"])},
        )
        return user.pk

    def _persist_department(self, record: dict, mappings: dict):
        Department = apps.get_model("escalated", "Department")
        dept, _ = Department.objects.get_or_create(
            slug=slugify(record["name"]),
            defaults={"name": record["name"], "is_active": True},
        )
        return dept.pk

    def _persist_custom_field(self, record: dict, mappings: dict):
        CustomField = apps.get_model("escalated", "CustomField")
        field, _ = CustomField.objects.get_or_create(
            slug=slugify(record["name"]),
            defaults={
                "name": record["name"],
                "field_type": record.get("type", "text"),
                "options": record.get("options", []),
            },
        )
        return field.pk

    def _persist_ticket(self, job: ImportJob, record: dict, mappings: dict):
        Ticket = apps.get_model("escalated", "Ticket")

        requester_id = None
        if record.get("requester_source_id"):
            requester_id = ImportSourceMap.resolve(job.id, "contacts", record["requester_source_id"])

        assignee_id = None
        if record.get("assignee_source_id"):
            assignee_id = ImportSourceMap.resolve(job.id, "agents", record["assignee_source_id"])

        department_id = None
        if record.get("department_source_id"):
            department_id = ImportSourceMap.resolve(job.id, "departments", record["department_source_id"])

        ticket = Ticket(
            subject=record.get("title") or record.get("subject") or "Imported ticket",
            status=record.get("status", "open"),
            priority=record.get("priority", "medium"),
            assigned_to_id=assignee_id,
            department_id=department_id,
            requester_id=requester_id,
            metadata=record.get("metadata"),
        )

        # Preserve original timestamps
        if record.get("created_at"):
            ticket.created_at = record["created_at"]
        if record.get("updated_at"):
            ticket.updated_at = record["updated_at"]

        # Bypass auto_now fields by using update_fields trickery after save
        ticket.save()

        if record.get("created_at") or record.get("updated_at"):
            update_fields = ["updated_at"]
            if record.get("created_at"):
                update_fields.append("created_at")
            Ticket.objects.filter(pk=ticket.pk).update(
                **{k: record[k[:-3] if k.endswith("_at") else k] for k in update_fields if record.get(k)}
            )

        # Attach tags
        if record.get("tag_source_ids"):
            apps.get_model("escalated", "Tag")
            tag_ids = [ImportSourceMap.resolve(job.id, "tags", sid) for sid in record["tag_source_ids"]]
            tag_ids = [tid for tid in tag_ids if tid]
            if tag_ids:
                ticket.tags.set(tag_ids)

        return ticket.pk

    def _persist_reply(self, job: ImportJob, record: dict, mappings: dict):
        Reply = apps.get_model("escalated", "Reply")

        ticket_id = ImportSourceMap.resolve(job.id, "tickets", record.get("ticket_source_id", ""))
        if not ticket_id:
            raise RuntimeError("Parent ticket not found for reply.")

        author_id = None
        if record.get("author_source_id"):
            author_id = ImportSourceMap.resolve(
                job.id, "agents", record["author_source_id"]
            ) or ImportSourceMap.resolve(job.id, "contacts", record["author_source_id"])

        reply = Reply(
            ticket_id=ticket_id,
            body=record.get("body", ""),
            is_internal_note=record.get("is_internal_note", False),
            author_id=author_id,
        )
        reply.save()

        if record.get("created_at") or record.get("updated_at"):
            update = {}
            if record.get("created_at"):
                update["created_at"] = record["created_at"]
            if record.get("updated_at"):
                update["updated_at"] = record["updated_at"]
            Reply.objects.filter(pk=reply.pk).update(**update)

        return reply.pk

    def _persist_attachment(self, job: ImportJob, record: dict, mappings: dict):
        Attachment = apps.get_model("escalated", "Attachment")
        from django.contrib.contenttypes.models import ContentType

        parent_type = record.get("parent_type", "reply")
        parent_source_id = record.get("parent_source_id", "")
        entity_key = "tickets" if parent_type == "ticket" else "replies"

        parent_id = ImportSourceMap.resolve(job.id, entity_key, parent_source_id)
        if not parent_id:
            raise RuntimeError(f"Parent {parent_type} not found for attachment.")

        if parent_type == "ticket":
            parent_model = apps.get_model("escalated", "Ticket")
        else:
            parent_model = apps.get_model("escalated", "Reply")

        ct = ContentType.objects.get_for_model(parent_model)
        attachment = Attachment.objects.create(
            content_type=ct,
            object_id=parent_id,
            filename=record.get("filename", "unknown"),
            mime_type=record.get("mime_type", "application/octet-stream"),
            size=record.get("size", 0),
            path=record.get("path", ""),
            disk=record.get("disk", "local"),
        )
        return attachment.pk

    def _persist_satisfaction_rating(self, job: ImportJob, record: dict, mappings: dict):
        SatisfactionRating = apps.get_model("escalated", "SatisfactionRating")

        ticket_id = ImportSourceMap.resolve(job.id, "tickets", record.get("ticket_source_id", ""))
        if not ticket_id:
            raise RuntimeError("Ticket not found for satisfaction rating.")

        rating = SatisfactionRating(
            ticket_id=ticket_id,
            rating=record.get("rating") or record.get("score"),
            comment=record.get("comment"),
        )
        if record.get("created_at"):
            rating.created_at = record["created_at"]
        rating.save()

        if record.get("created_at"):
            SatisfactionRating.objects.filter(pk=rating.pk).update(created_at=record["created_at"])

        return rating.pk
