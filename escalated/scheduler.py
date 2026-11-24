"""
Whether the recurring jobs are running.

Django has no scheduler of its own, so SLA checks, escalation rules,
automations and snooze wake-ups run only when the host schedules the
management commands (cron, Celery beat, systemd timers...). ``check_sla``
records a heartbeat each time it runs; while the heartbeat is missing or more
than 15 minutes old, the admin Settings and Reports pages carry a ``scheduler``
prop the shared frontend shows as a warning, and a warning is logged.

The prop's shape is the one every Escalated backend sends:
``{healthy, last_run_at, message, commands: [{command, interval}]}``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.utils import timezone

from escalated.conf import get_setting

logger = logging.getLogger("escalated.scheduler")

HEARTBEAT_KEY = "scheduler_heartbeat_at"
STALE_AFTER = timedelta(minutes=15)

# Always needed.
CORE_COMMANDS = [
    {"command": "python manage.py check_sla", "interval": "every minute"},
    {"command": "python manage.py wake_snoozed_tickets", "interval": "every minute"},
    {"command": "python manage.py evaluate_escalations", "interval": "every 5 minutes"},
    {"command": "python manage.py run_automations", "interval": "every 5 minutes"},
    {"command": "python manage.py close_resolved", "interval": "daily"},
    {"command": "python manage.py purge_expired_data", "interval": "daily"},
    {"command": "python manage.py purge_activities", "interval": "weekly"},
]


def commands() -> list[dict]:
    """The commands this install needs scheduled, with their intervals."""
    needed = [dict(entry) for entry in CORE_COMMANDS]
    if get_setting("INBOUND_EMAIL_ENABLED") and get_setting("INBOUND_EMAIL_ADAPTER") == "imap":
        needed.append({"command": "python manage.py poll_imap", "interval": "every minute"})
    if _chat_enabled():
        needed.append({"command": "python manage.py close_idle_chats", "interval": "every minute"})
        needed.append({"command": "python manage.py cleanup_abandoned_chats", "interval": "every minute"})
    if get_setting("enable_newsletters"):
        needed.append({"command": "python manage.py dispatch_newsletters", "interval": "every minute"})
    if get_setting("SDK_ENABLED"):
        needed.append({"command": "python manage.py escalated_plugin_cron", "interval": "every minute"})
    return needed


def _chat_enabled() -> bool:
    try:
        from escalated.models import EscalatedSetting

        return EscalatedSetting.get_bool("chat_enabled", default=False)
    except Exception:
        return False


def record_heartbeat(now: datetime | None = None) -> None:
    """Note that the recurring jobs ran (``check_sla`` calls this)."""
    from escalated.models import EscalatedSetting

    EscalatedSetting.set(HEARTBEAT_KEY, (now or timezone.now()).isoformat())


def last_run_at() -> datetime | None:
    from escalated.models import EscalatedSetting

    value = EscalatedSetting.get(HEARTBEAT_KEY)
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, dt_timezone.utc)
    return moment


def status(now: datetime | None = None) -> dict | None:
    """
    The ``scheduler`` prop: ``healthy`` is False while the heartbeat is missing
    or older than 15 minutes. ``None`` when the heartbeat cannot be read.
    """
    try:
        last = last_run_at()
    except Exception:
        return None
    now = now or timezone.now()
    healthy = last is not None and now - last <= STALE_AFTER
    needed = commands()
    if healthy:
        message = "The recurring jobs are running."
    else:
        if last is None:
            since = "check_sla has never run"
        else:
            since = f"check_sla last ran at {last.isoformat()}"
        message = (
            f"The recurring jobs are not running ({since}): SLA checks, escalation rules, automations and "
            "snooze wake-ups do nothing until they are scheduled. Schedule these with cron, Celery beat or "
            "similar: " + "; ".join(f"{entry['command']} ({entry['interval']})" for entry in needed) + "."
        )
    return {
        "healthy": healthy,
        "last_run_at": last.isoformat() if last else None,
        "message": message,
        "commands": needed,
    }


def page_prop() -> dict | None:
    """``status()`` for an admin page, logging a warning while the jobs are not running."""
    current = status()
    if current is not None and not current["healthy"]:
        logger.warning(current["message"])
    return current
