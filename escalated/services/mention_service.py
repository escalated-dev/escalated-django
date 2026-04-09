import logging
import re

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger("escalated")

MENTION_REGEX = re.compile(r"@(\w+(?:\.\w+)*)")


class MentionService:
    def process_mentions(self, reply):
        """Extract @mentions from reply body and create mention records + notifications."""
        usernames = self.extract_mentions(reply.body)
        if not usernames:
            return []
        users = self._find_users(usernames)
        mentions = self._create_mentions(reply, users)
        self._notify_mentioned_users(reply, mentions)
        return mentions

    def extract_mentions(self, text):
        """Extract unique usernames from text."""
        if not text:
            return []
        return list(set(MENTION_REGEX.findall(text)))

    def search_agents(self, query, limit=10):
        """Search agents for autocomplete."""
        if not query:
            return []
        User = get_user_model()
        filters = Q(email__icontains=query)
        if hasattr(User, "name"):
            filters = filters | Q(name__icontains=query)
        if hasattr(User, "username"):
            filters = filters | Q(username__icontains=query)
        users = User.objects.filter(filters)[:limit]
        return [
            {
                "id": u.pk,
                "name": getattr(u, "name", u.email if hasattr(u, "email") else str(u)),
                "email": getattr(u, "email", ""),
                "username": self._extract_username(u),
            }
            for u in users
        ]

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

    def _find_users(self, usernames):
        User = get_user_model()
        users = []
        for username in usernames:
            user = None
            if hasattr(User, "username"):
                user = User.objects.filter(username=username).first()
            if not user:
                user = User.objects.filter(email__istartswith=f"{username}@").first()
            if user:
                users.append(user)
        return list(set(users))

    def _create_mentions(self, reply, users):
        from escalated.mention_models import Mention

        mentions = []
        for user in users:
            mention, created = Mention.objects.get_or_create(reply=reply, user=user)
            if created:
                mentions.append(mention)
        return mentions

    def _notify_mentioned_users(self, reply, mentions):
        from escalated.models import TicketActivity

        ticket = reply.ticket
        for mention in mentions:
            TicketActivity.objects.create(
                ticket=ticket,
                activity_type="mention",
                details={
                    "mentioned_user_id": mention.user_id,
                    "reply_id": reply.id,
                    "message": f"You were mentioned in ticket #{ticket.reference}",
                },
            )
            logger.info(f"Escalated mention notification: user={mention.user_id} ticket={ticket.reference}")

    def _extract_username(self, user):
        if hasattr(user, "username") and user.username:
            return user.username
        email = getattr(user, "email", "")
        return email.split("@")[0] if email else str(user.pk)
