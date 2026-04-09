"""Mention model for @mentions in replies."""

from django.conf import settings
from django.db import models
from django.utils import timezone

from escalated.conf import get_table_name


class Mention(models.Model):
    reply = models.ForeignKey(
        "escalated.Reply",
        on_delete=models.CASCADE,
        related_name="mentions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="escalated_mentions",
    )
    read_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = get_table_name("mentions")
        unique_together = [("reply", "user")]

    def __str__(self):
        return f"Mention {self.id}: user={self.user_id} reply={self.reply_id}"

    @property
    def is_read(self):
        return self.read_at is not None

    def mark_as_read(self):
        if not self.is_read:
            self.read_at = timezone.now()
            self.save()
