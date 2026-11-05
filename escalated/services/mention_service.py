"""
@mentions in replies and internal notes, as escalated-laravel's
MentionService and MentionNotification.

Two forms are recognised: ``@{Full Name}`` (what the composer's mention picker
inserts) and ``@name``. A name matches a staff user (an agent or an admin) by
display name (full name, else username), username or email, ignoring case.
Each mentioned agent gets a ``Mention`` row, a ``mention`` notification in the
agent feed and, while ``email`` is a notification channel, an email.
"""

import logging
import re

from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.utils import timezone

logger = logging.getLogger("escalated")

BRACED = re.compile(r"@\{([^}]+)\}")
SIMPLE = re.compile(r"@([a-zA-Z0-9_.-]+)(?![^{]*\})")


def _has_field(model, name):
    try:
        model._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    return True


def display_name(user):
    """The name the agent lists show, and the picker inserts as ``@{name}``."""
    full = user.get_full_name() if hasattr(user, "get_full_name") else ""
    return (full or "").strip() or getattr(user, "username", "") or getattr(user, "email", "") or str(user.pk)


class MentionService:
    def process_mentions(self, reply):
        """Create mention records for the agents a reply mentions, and notify them."""
        users = self.find_mentioned_users(reply.body)
        author_id = getattr(reply, "author_id", None)
        users = [u for u in users if author_id is None or str(u.pk) != str(author_id)]
        mentions = self._create_mentions(reply, users)
        self._notify_mentioned_users(reply, mentions)
        return mentions

    def extract_mentions(self, text):
        """The names mentioned in ``text``, braced and simple, trimmed and unique, in order."""
        if not text:
            return []
        names = [n.strip() for n in BRACED.findall(text) + SIMPLE.findall(text)]
        return list(dict.fromkeys(n for n in names if n))

    def find_mentioned_users(self, text):
        """The staff users ``text`` mentions."""
        from escalated.services.agent_panel import is_staff_user

        names = self.extract_mentions(text)
        if not names:
            return []
        User = get_user_model()
        users = User.objects.filter(is_active=True) if _has_field(User, "is_active") else User.objects.all()
        query = Q()
        for name in names:
            if _has_field(User, "username"):
                query |= Q(username__iexact=name)
            if _has_field(User, "email"):
                query |= Q(email__iexact=name)
            if _has_field(User, "name"):
                query |= Q(name__iexact=name)
        if _has_field(User, "first_name") and _has_field(User, "last_name"):
            users = users.annotate(_escalated_full_name=Concat("first_name", Value(" "), "last_name"))
            for name in names:
                query |= Q(_escalated_full_name__iexact=name)
        return [u for u in users.filter(query).order_by("pk") if is_staff_user(u)]

    def search_agents(self, query, limit=10):
        """The mention picker: staff whose name, username or email contains ``query``."""
        from escalated.services.agent_panel import is_staff_user

        query = (query or "").strip()
        if not query:
            return []
        User = get_user_model()
        filters = Q()
        for field in ("email", "username", "name", "first_name", "last_name"):
            if _has_field(User, field):
                filters |= Q(**{f"{field}__icontains": query})
        users = User.objects.filter(filters)
        if _has_field(User, "is_active"):
            users = users.filter(is_active=True)
        found = []
        for user in users.order_by("pk")[:200]:
            if is_staff_user(user):
                found.append({"id": user.pk, "name": display_name(user), "email": getattr(user, "email", None)})
            if len(found) >= limit:
                break
        return found

    def unread_mentions(self, user_id):
        """Get unread mentions for a user."""
        from escalated.mention_models import Mention

        return (
            Mention.objects.filter(user_id=user_id, read_at__isnull=True)
            .select_related("reply", "reply__ticket")
            .order_by("-created_at")
        )

    def mark_as_read(self, mention_ids, user_id):
        """Mark specified mentions as read."""
        from escalated.mention_models import Mention

        Mention.objects.filter(id__in=mention_ids, user_id=user_id).update(read_at=timezone.now())

    def _create_mentions(self, reply, users):
        from escalated.mention_models import Mention

        mentions = []
        for user in users:
            mention, created = Mention.objects.get_or_create(reply=reply, user=user)
            if created:
                mentions.append(mention)
        return mentions

    def _notify_mentioned_users(self, reply, mentions):
        from escalated.services import agent_panel
        from escalated.services.notification_service import NotificationService

        ticket = reply.ticket
        author = reply.author if reply.author_id else None
        mentioned_by = display_name(author) if author else "Someone"
        for mention in mentions:
            agent_panel.notify(
                mention.user_id,
                "mention",
                ticket,
                {"reply_id": reply.pk, "mentioned_by": mentioned_by},
                causer_id=reply.author_id,
            )
            NotificationService.notify_mentioned(ticket, mention.user, mentioned_by)
            logger.info(f"Escalated mention notification: user={mention.user_id} ticket={ticket.reference}")
