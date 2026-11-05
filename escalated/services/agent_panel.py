"""
The agent panel's data (ADR 2026-11-05-agent-panel-data): per-agent unread
markers, customer online status, the agent's own status and the agents'
in-app notifications feed. escalated-laravel is the reference implementation.
"""

import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from escalated.conf import get_setting
from escalated.support.import_context import ImportContext

logger = logging.getLogger("escalated.agent_panel")

AGENT_STATUSES = ("online", "away", "offline")
PRESENCE_THROTTLE_SECONDS = 30
NOTIFICATIONS_PER_PAGE = 20
NOTIFICATIONS_MAX_PER_PAGE = 50
NOTIFICATION_TYPES = ("ticket_assigned", "ticket_reply", "mention", "sla_warning", "sla_breached", "chat_transferred")
# Reply metadata keys that mark a reply written by the system, not a person.
SYSTEM_MARKERS = ("workflow_id", "automation_id", "system_note")


def is_staff_user(user):
    from escalated.permissions import is_admin, is_agent

    return bool(user) and (is_agent(user) or is_admin(user))


# ---------------------------------------------------------------------------
# 1. Unread tracking
# ---------------------------------------------------------------------------


def mark_read(agent, ticket):
    _write_marker(agent, ticket, timezone.now())


def mark_unread(agent, ticket):
    _write_marker(agent, ticket, None)


def _write_marker(agent, ticket, at):
    from escalated.models import TicketRead

    try:
        with transaction.atomic(using=TicketRead.objects.db):
            TicketRead.objects.update_or_create(user_id=agent.pk, ticket_id=ticket.pk, defaults={"last_read_at": at})
    except IntegrityError:
        # Another request created the marker first.
        TicketRead.objects.filter(user_id=agent.pk, ticket_id=ticket.pk).update(last_read_at=at)


def is_unread(activity, has_marker, last_read_at):
    if has_marker and last_read_at is None:
        return True
    if activity is None:
        return False
    if not has_marker:
        return True
    return activity > last_read_at


def unread_flags(agent, tickets):
    """{ticket id: is_unread} for the tickets, from one query."""
    from escalated.models import TicketRead

    tickets = list(tickets)
    markers = {}
    if tickets:
        rows = TicketRead.objects.filter(user_id=agent.pk, ticket_id__in=[t.pk for t in tickets])
        markers = dict(rows.values_list("ticket_id", "last_read_at"))
    return {t.pk: is_unread(t.last_customer_activity_at, t.pk in markers, markers.get(t.pk)) for t in tickets}


def only_unread(queryset, agent):
    """Limit a ticket queryset to the tickets unread for the agent (two EXISTS subqueries)."""
    from escalated.models import TicketRead

    markers = TicketRead.objects.filter(ticket_id=OuterRef("pk"), user_id=agent.pk)
    marked_unread = Exists(markers.filter(last_read_at__isnull=True))
    read_since = Exists(markers.filter(last_read_at__gte=OuterRef("last_customer_activity_at")))
    return queryset.filter(marked_unread | (Q(last_customer_activity_at__isnull=False) & ~read_since))


def is_customer_side(reply):
    """
    A public reply or chat message from the requester, a guest (no author) or
    a host user who is not staff. Agents' replies, notes and replies a
    workflow, automation or the system wrote are not.
    """
    if reply.is_internal_note or reply.type != "reply":
        return False
    metadata = reply.metadata if isinstance(reply.metadata, dict) else {}
    if any(key in metadata for key in SYSTEM_MARKERS):
        return False
    if reply.author_id is None:
        return True
    ticket = reply.ticket
    if ticket.requester_object_id is not None and str(ticket.requester_object_id) == str(reply.author_id):
        return True
    return not is_staff_user(reply.author)


def record_reply_activity(reply):
    """A customer-side public reply is unread activity for agents."""
    from escalated.models import Ticket

    if ImportContext.is_importing() or not is_customer_side(reply):
        return
    Ticket.unrestricted.filter(pk=reply.ticket_id).update(last_customer_activity_at=reply.created_at or timezone.now())


# ---------------------------------------------------------------------------
# 2. Customer presence
# ---------------------------------------------------------------------------


def presence_window():
    try:
        seconds = int(get_setting("PRESENCE_ONLINE_WINDOW_SECONDS") or 120)
    except (TypeError, ValueError):
        seconds = 120
    return max(1, seconds)


def presence_subject(ticket):
    """A ticket's customer: its requester, its contact for a guest, else the ticket itself."""
    if ticket.requester_content_type_id and ticket.requester_object_id:
        from django.contrib.contenttypes.models import ContentType

        model = ContentType.objects.get_for_id(ticket.requester_content_type_id)
        return (model.app_label + "." + model.model, str(ticket.requester_object_id))
    if ticket.contact_id:
        return ("escalated.contact", str(ticket.contact_id))
    if ticket.pk:
        return ("escalated.ticket", str(ticket.pk))
    return None


def see_user(user):
    """A signed-in customer-portal user. Staff browsing the portal are not customers."""
    if not user or not user.is_authenticated or is_staff_user(user):
        return
    _see((user._meta.app_label + "." + user._meta.model_name, str(user.pk)))


def see_ticket_customer(ticket):
    subject = presence_subject(ticket) if ticket else None
    if subject:
        _see(subject)


def quietly(work, *args):
    """Presence is a hint: it never fails the request it rides on."""
    try:
        work(*args)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Customer presence was not recorded: %s", exc)


def record_customer_presence(view):
    """A customer-portal view that records the signed-in customer as seen (staff are skipped)."""
    import functools

    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        quietly(see_user, getattr(request, "user", None))
        return view(request, *args, **kwargs)

    return wrapped


def _see(subject):
    """Throttled in the database: a row is written only when its last write is 30 seconds old."""
    from escalated.models import CustomerPresence

    subject_type, subject_id = subject
    now = timezone.now()
    rows = CustomerPresence.objects.filter(subject_type=subject_type, subject_id=subject_id)
    if rows.filter(last_seen_at__lte=now - timedelta(seconds=PRESENCE_THROTTLE_SECONDS)).update(
        last_seen_at=now, updated_at=now
    ):
        return
    if rows.exists():
        return
    try:
        with transaction.atomic(using=CustomerPresence.objects.db):
            CustomerPresence.objects.create(subject_type=subject_type, subject_id=subject_id, last_seen_at=now)
    except IntegrityError:
        pass  # Another request recorded them first.


def presence_lookup(tickets):
    """{ticket id: {requester_online, requester_last_seen_at}}, from one query. Staff pages only."""
    from escalated.models import CustomerPresence

    tickets = list(tickets)
    subjects = {t.pk: presence_subject(t) for t in tickets}
    wanted = {s for s in subjects.values() if s}
    seen = {}
    if wanted:
        condition = Q()
        for subject_type, subject_id in wanted:
            condition |= Q(subject_type=subject_type, subject_id=subject_id)
        for row in CustomerPresence.objects.filter(condition):
            seen[(row.subject_type, row.subject_id)] = row.last_seen_at
    since = timezone.now() - timedelta(seconds=presence_window())
    result = {}
    for ticket in tickets:
        last = seen.get(subjects[ticket.pk]) if subjects[ticket.pk] else None
        result[ticket.pk] = {
            "requester_online": last is not None and last >= since,
            "requester_last_seen_at": last.isoformat() if last else None,
        }
    return result


def row_fields(agent, tickets):
    """``is_unread``, ``requester_online`` and ``requester_last_seen_at`` for agent rows."""
    tickets = list(tickets)
    flags = unread_flags(agent, tickets)
    presence = presence_lookup(tickets)
    return {t.pk: {"is_unread": flags[t.pk], **presence[t.pk]} for t in tickets}


# ---------------------------------------------------------------------------
# 3. The agent's own status
# ---------------------------------------------------------------------------


def agent_status(user):
    from escalated.models import AgentProfile

    profile = AgentProfile.objects.filter(user_id=user.pk).only("chat_status").first()
    return profile.chat_status if profile and profile.chat_status in AGENT_STATUSES else "offline"


def set_agent_status(user, status):
    """The agent profile's chat_status, the field live-chat routing reads."""
    from escalated.models import AgentProfile

    profile, _created = AgentProfile.objects.get_or_create(user=user, defaults={"agent_type": "full"})
    profile.chat_status = status
    profile.save(update_fields=["chat_status", "updated_at"])


# ---------------------------------------------------------------------------
# 4. Notifications
# ---------------------------------------------------------------------------


def notifications_available():
    return get_setting("AGENT_NOTIFICATIONS") is not False


def notify(agent_id, notification_type, ticket, data=None, causer_id=None):
    """Stores a notification for an agent, unless they caused it, and broadcasts it."""
    from escalated.models import AgentNotification

    if not notifications_available() or not agent_id or ImportContext.is_importing():
        return None
    if causer_id is not None and str(causer_id) == str(agent_id):
        return None
    row = AgentNotification.objects.create(
        user_id=agent_id,
        type=notification_type,
        data={
            **(data or {}),
            "ticket_id": ticket.pk if ticket else None,
            "reference": ticket.reference if ticket else None,
        },
    )
    _broadcast(agent_id, row)
    return row


def unread_count(user):
    from escalated.models import AgentNotification

    return AgentNotification.objects.filter(user_id=user.pk, read_at__isnull=True).count()


def present(rows, user):
    """Feed items for ``user``; a ticket they can no longer see redacts the item."""
    from escalated.models import Ticket
    from escalated.ticket_access import scope_tickets

    rows = list(rows)
    ids = {row.data.get("ticket_id") for row in rows if isinstance(row.data, dict) and row.data.get("ticket_id")}
    tickets = {}
    if ids:
        visible = scope_tickets(Ticket.unrestricted.filter(pk__in=ids), user).only("id", "reference", "subject")
        tickets = {t.pk: t for t in visible}
    return [item(row, tickets) for row in rows]


def item(row, tickets):
    data = row.data if isinstance(row.data, dict) else {}
    ticket_id = data.get("ticket_id")
    ticket = tickets.get(int(ticket_id)) if ticket_id else None
    base = {
        "id": str(row.pk),
        "type": row.type,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }
    if ticket_id and ticket is None:
        return {**base, "title": _("A ticket you can no longer view"), "body": None, "ticket": None, "url": None}
    reference = ticket.reference if ticket else str(data.get("reference") or "")
    return {
        **base,
        "title": _title(row.type, reference, data),
        "body": ticket.subject if ticket else None,
        "ticket": {"id": ticket.pk, "reference": ticket.reference, "subject": ticket.subject} if ticket else None,
        "url": _ticket_url(ticket) if ticket else None,
    }


def _title(notification_type, reference, data):
    titles = {
        "ticket_assigned": _("%(reference)s was assigned to you"),
        "ticket_reply": _("New reply on %(reference)s"),
        "mention": _("%(name)s mentioned you on %(reference)s"),
        "sla_warning": _("SLA due soon on %(reference)s"),
        "sla_breached": _("SLA breached on %(reference)s"),
        "chat_transferred": _("A chat was transferred to you (%(reference)s)"),
    }
    template = titles.get(notification_type, _("Update on %(reference)s"))
    return template % {"reference": reference, "name": data.get("mentioned_by") or ""}


def _ticket_url(ticket):
    from django.urls import NoReverseMatch, reverse

    try:
        return reverse("escalated:agent_ticket_show", args=[ticket.reference])
    except NoReverseMatch:
        try:
            return reverse("escalated:agent_ticket_show", args=[ticket.pk])
        except NoReverseMatch:
            return None


def agent_channel(agent_id):
    return f"escalated.agents.{agent_id}"


def _broadcast(agent_id, row):
    from django.contrib.auth import get_user_model

    from escalated.broadcasting import broadcast_event, broadcasting_enabled
    from escalated.models import Ticket
    from escalated.ticket_access import scope_tickets

    if not broadcasting_enabled():
        return
    user = get_user_model().objects.filter(pk=agent_id).first()
    if user is None:
        return
    tickets = {}
    ticket_id = row.data.get("ticket_id") if isinstance(row.data, dict) else None
    if ticket_id:
        tickets = {t.pk: t for t in scope_tickets(Ticket.unrestricted.filter(pk=ticket_id), user)}
    broadcast_event("notification.created", agent_channel(agent_id), item(row, tickets))


def kb_url(request, article):
    from django.urls import NoReverseMatch, reverse

    try:
        return request.build_absolute_uri(reverse("escalated:customer_kb_show", args=[article.slug]))
    except NoReverseMatch:
        return None
