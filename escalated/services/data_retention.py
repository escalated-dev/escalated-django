"""Data retention: what the Data Retention settings page stores, and the purge it drives.

Four settings in the key/value store (``EscalatedSetting``):

- ``retention_closed_tickets``: never | 1_year | 2_years | 3_years | 5_years
- ``retention_attachments``: the same choices
- ``retention_audit_logs``: never | 90_days | 180_days | 365_days
- ``retention_user_data_gdpr``: "1" / "0" (stored only; nothing acts on it yet)

All default to ``never``, which purges nothing. ``purge_expired_data`` applies
them. Tickets have no soft delete in this package, so a purged ticket is deleted
outright together with its replies, its attachments and their stored files.
"""

import logging
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

logger = logging.getLogger(__name__)

RETENTION_DAYS = {
    "never": None,
    "90_days": 90,
    "180_days": 180,
    "365_days": 365,
    "1_year": 365,
    "2_years": 730,
    "3_years": 1095,
    "5_years": 1825,
}

RECORD_CHOICES = ("never", "1_year", "2_years", "3_years", "5_years")
AUDIT_LOG_CHOICES = ("never", "90_days", "180_days", "365_days")

DEFAULTS = {
    "retention_closed_tickets": "never",
    "retention_attachments": "never",
    "retention_audit_logs": "never",
}

_BATCH = 500


def retention_days(key):
    """Days kept for one retention setting, or ``None`` for never (or an unknown value)."""
    from escalated.models import EscalatedSetting

    return RETENTION_DAYS.get(EscalatedSetting.get(key, DEFAULTS[key]) or "never")


def _cutoff(key, now):
    days = retention_days(key)
    return None if days is None else now - timedelta(days=days)


def expired_tickets(now=None):
    """Closed tickets past their retention, or ``None`` when tickets are kept forever."""
    from escalated.models import Ticket

    cutoff = _cutoff("retention_closed_tickets", now or timezone.now())
    if cutoff is None:
        return None
    return Ticket.unrestricted.filter(status=Ticket.Status.CLOSED, closed_at__lt=cutoff)


def expired_attachments(now=None):
    from escalated.models import Attachment

    cutoff = _cutoff("retention_attachments", now or timezone.now())
    if cutoff is None:
        return None
    return Attachment.objects.filter(created_at__lt=cutoff)


def expired_audit_logs(now=None):
    from escalated.models import AuditLog

    cutoff = _cutoff("retention_audit_logs", now or timezone.now())
    if cutoff is None:
        return None
    return AuditLog.objects.filter(created_at__lt=cutoff)


def _count(queryset):
    return 0 if queryset is None else queryset.count()


def preview(now=None):
    """What a purge would remove right now. Never raises: the settings page must render."""
    now = now or timezone.now()
    try:
        return {
            "tickets": _count(expired_tickets(now)),
            "attachments": _count(expired_attachments(now)),
            "audit_logs": _count(expired_audit_logs(now)),
        }
    except Exception:  # noqa: BLE001 - a broken count must not take the page down
        logger.exception("Could not compute the data retention purge preview")
        return {"tickets": 0, "attachments": 0, "audit_logs": 0}


def _delete_attachments(queryset):
    """Delete attachment rows and their stored files. Returns the number of rows."""
    deleted = 0
    while True:
        batch = list(queryset.order_by("pk")[:_BATCH])
        if not batch:
            return deleted
        for attachment in batch:
            if attachment.file:
                try:
                    attachment.file.delete(save=False)
                except Exception:  # noqa: BLE001 - a missing file must not stop the purge
                    logger.warning("Could not delete stored file for attachment #%s", attachment.pk)
        type(batch[0]).objects.filter(pk__in=[a.pk for a in batch]).delete()
        deleted += len(batch)


def _delete_tickets(queryset):
    """Delete tickets with their replies' and their own attachments (files included)."""
    from escalated.models import Attachment, Reply, Ticket

    ticket_type = ContentType.objects.get_for_model(Ticket)
    reply_type = ContentType.objects.get_for_model(Reply)
    deleted = 0
    while True:
        ids = list(queryset.order_by("pk").values_list("pk", flat=True)[:_BATCH])
        if not ids:
            return deleted
        reply_ids = list(Reply._base_manager.filter(ticket_id__in=ids).values_list("pk", flat=True))
        _delete_attachments(Attachment.objects.filter(content_type=ticket_type, object_id__in=ids))
        if reply_ids:
            _delete_attachments(Attachment.objects.filter(content_type=reply_type, object_id__in=reply_ids))
        Ticket.unrestricted.filter(pk__in=ids).delete()
        deleted += len(ids)


def purge(dry_run=False, write=None, now=None):
    """Apply every retention setting.

    Returns ``{"tickets", "attachments", "audit_logs"}``: the rows removed, or
    on a dry run the rows that would be.
    """
    now = now or timezone.now()
    write = write or (lambda message: None)
    counts = {}

    for name, label, key, queryset, delete in (
        ("tickets", "closed tickets", "retention_closed_tickets", expired_tickets(now), _delete_tickets),
        ("attachments", "attachments", "retention_attachments", expired_attachments(now), _delete_attachments),
        ("audit_logs", "audit log entries", "retention_audit_logs", expired_audit_logs(now), None),
    ):
        counts[name] = 0
        if queryset is None:
            write(f"Retention: {label} kept forever (never), skipping.")
            continue
        days = retention_days(key)
        found = queryset.count()
        if dry_run:
            counts[name] = found
            write(f"Retention: {found} {label} older than {days} days would be purged.")
            continue
        if found and delete:
            counts[name] = delete(queryset)
        elif found:
            queryset.delete()
            counts[name] = found
        write(f"Retention: purged {counts[name]} {label} older than {days} days.")

    return counts
