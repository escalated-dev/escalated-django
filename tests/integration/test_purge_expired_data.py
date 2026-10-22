"""``purge_expired_data`` honours the Data Retention settings.

Every retention setting defaults to ``never``, and ``never`` must leave data
alone: hosts that already schedule this command for its token and delivery
cleanup must not start losing tickets on upgrade.
"""

from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from escalated.models import Attachment, AuditLog, EscalatedSetting, Reply, Ticket
from tests.factories import ReplyFactory, TicketFactory


def make_closed_ticket(days_ago, status=Ticket.Status.CLOSED):
    ticket = TicketFactory(status=status)
    Ticket.unrestricted.filter(pk=ticket.pk).update(closed_at=timezone.now() - timedelta(days=days_ago))
    return ticket


def make_attachment(days_ago, owner=None, content=None):
    owner = owner or TicketFactory()
    attachment = Attachment(
        content_type=ContentType.objects.get_for_model(owner),
        object_id=owner.pk,
        original_filename="note.txt",
        mime_type="text/plain",
        size=4,
    )
    if content is not None:
        attachment.file.save("note.txt", ContentFile(content), save=False)
    else:
        attachment.file.name = "escalated/attachments/missing.txt"
    attachment.save()
    Attachment.objects.filter(pk=attachment.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
    return attachment


def make_audit_log(days_ago):
    ticket = TicketFactory()
    log = AuditLog.objects.create(
        action="updated",
        auditable_content_type=ContentType.objects.get_for_model(ticket),
        auditable_object_id=ticket.pk,
    )
    AuditLog.objects.filter(pk=log.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
    return log


def purge(*args):
    out = StringIO()
    call_command("purge_expired_data", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def media_root(tmp_path):
    with override_settings(MEDIA_ROOT=str(tmp_path)):
        yield tmp_path


@pytest.mark.django_db
class TestRetentionPurge:
    def test_never_leaves_everything_alone(self):
        old = make_closed_ticket(days_ago=4000)
        attachment = make_attachment(days_ago=4000)
        log = make_audit_log(days_ago=4000)

        purge()

        assert Ticket.unrestricted.filter(pk=old.pk).exists()
        assert Attachment.objects.filter(pk=attachment.pk).exists()
        assert AuditLog.objects.filter(pk=log.pk).exists()

    def test_old_closed_ticket_is_purged_and_recent_or_open_kept(self, media_root):
        EscalatedSetting.set("retention_closed_tickets", "1_year")
        old = make_closed_ticket(days_ago=400)
        reply = ReplyFactory(ticket=old)
        ticket_file = make_attachment(days_ago=1, owner=old, content=b"data")
        reply_file = make_attachment(days_ago=1, owner=reply, content=b"data")
        recent = make_closed_ticket(days_ago=30)
        resolved = make_closed_ticket(days_ago=400, status=Ticket.Status.RESOLVED)
        still_open = TicketFactory(status=Ticket.Status.OPEN)
        stored = [media_root / ticket_file.file.name, media_root / reply_file.file.name]
        assert all(path.exists() for path in stored)

        output = purge()

        assert not Ticket.unrestricted.filter(pk=old.pk).exists()
        assert not Reply.objects.filter(pk=reply.pk).exists()
        assert not Attachment.objects.filter(pk__in=[ticket_file.pk, reply_file.pk]).exists()
        assert not any(path.exists() for path in stored)
        assert Ticket.unrestricted.filter(pk__in=[recent.pk, resolved.pk, still_open.pk]).count() == 3
        assert "closed tickets" in output.lower()

    def test_old_attachments_are_deleted_with_their_files(self, media_root):
        EscalatedSetting.set("retention_attachments", "1_year")
        old = make_attachment(days_ago=400, content=b"data")
        recent = make_attachment(days_ago=10, content=b"data")
        old_path = media_root / old.file.name

        purge()

        assert not Attachment.objects.filter(pk=old.pk).exists()
        assert not old_path.exists()
        assert Attachment.objects.filter(pk=recent.pk).exists()
        assert (media_root / recent.file.name).exists()

    def test_old_audit_logs_are_deleted(self):
        EscalatedSetting.set("retention_audit_logs", "90_days")
        old = make_audit_log(days_ago=100)
        recent = make_audit_log(days_ago=10)

        purge()

        assert not AuditLog.objects.filter(pk=old.pk).exists()
        assert AuditLog.objects.filter(pk=recent.pk).exists()

    def test_dry_run_deletes_nothing(self):
        EscalatedSetting.set("retention_closed_tickets", "1_year")
        EscalatedSetting.set("retention_attachments", "1_year")
        EscalatedSetting.set("retention_audit_logs", "90_days")
        ticket = make_closed_ticket(days_ago=400)
        attachment = make_attachment(days_ago=400)
        log = make_audit_log(days_ago=100)

        output = purge("--dry-run")

        assert Ticket.unrestricted.filter(pk=ticket.pk).exists()
        assert Attachment.objects.filter(pk=attachment.pk).exists()
        assert AuditLog.objects.filter(pk=log.pk).exists()
        assert "1 closed tickets" in output
        assert "1 attachments" in output
        assert "1 audit log" in output

    def test_an_unknown_stored_value_reads_as_never(self):
        EscalatedSetting.set("retention_closed_tickets", "10_minutes")
        ticket = make_closed_ticket(days_ago=4000)

        purge()

        assert Ticket.unrestricted.filter(pk=ticket.pk).exists()
