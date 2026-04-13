import hashlib
import secrets
import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from escalated.conf import get_table_name

# ---------------------------------------------------------------------------
# Managers / QuerySets
# ---------------------------------------------------------------------------


class TicketQuerySet(models.QuerySet):
    def open(self):
        return self.filter(
            status__in=[
                Ticket.Status.OPEN,
                Ticket.Status.IN_PROGRESS,
                Ticket.Status.WAITING_ON_CUSTOMER,
                Ticket.Status.WAITING_ON_AGENT,
                Ticket.Status.ESCALATED,
                Ticket.Status.REOPENED,
            ]
        )

    def closed(self):
        return self.filter(status__in=[Ticket.Status.RESOLVED, Ticket.Status.CLOSED])

    def unassigned(self):
        return self.filter(assigned_to__isnull=True)

    def assigned_to(self, user_id):
        return self.filter(assigned_to_id=user_id)

    def breached_sla(self):
        return self.filter(Q(sla_first_response_breached=True) | Q(sla_resolution_breached=True))

    def search(self, term):
        return self.filter(Q(subject__icontains=term) | Q(description__icontains=term) | Q(reference__icontains=term))

    def by_department(self, department_id):
        return self.filter(department_id=department_id)

    def by_priority(self, priority):
        return self.filter(priority=priority)

    def by_status(self, status):
        return self.filter(status=status)

    def by_ticket_type(self, ticket_type):
        return self.filter(ticket_type=ticket_type)

    def followed_by(self, user_id):
        """Filter tickets that are followed by a specific user."""
        return self.filter(ticket_followers__user_id=user_id)

    def snoozed(self):
        """Return tickets that are currently snoozed."""
        return self.filter(snoozed_until__isnull=False, snoozed_until__gt=timezone.now())

    def not_snoozed(self):
        """Exclude currently snoozed tickets."""
        return self.exclude(snoozed_until__isnull=False, snoozed_until__gt=timezone.now())

    def snooze_expired(self):
        """Return tickets whose snooze period has expired."""
        return self.filter(snoozed_until__isnull=False, snoozed_until__lte=timezone.now())

    def live_chats(self):
        """Return tickets that are live chat conversations."""
        return self.filter(channel="chat", chat_ended_at__isnull=True).exclude(
            status__in=[Ticket.Status.RESOLVED, Ticket.Status.CLOSED]
        )


class TicketManager(models.Manager):
    def get_queryset(self):
        return TicketQuerySet(self.model, using=self._db)

    def open(self):
        return self.get_queryset().open()

    def closed(self):
        return self.get_queryset().closed()

    def unassigned(self):
        return self.get_queryset().unassigned()

    def assigned_to(self, user_id):
        return self.get_queryset().assigned_to(user_id)

    def breached_sla(self):
        return self.get_queryset().breached_sla()

    def search(self, term):
        return self.get_queryset().search(term)

    def live_chats(self):
        return self.get_queryset().live_chats()

    def snoozed(self):
        return self.get_queryset().snoozed()

    def not_snoozed(self):
        return self.get_queryset().not_snoozed()

    def snooze_expired(self):
        return self.get_queryset().snooze_expired()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Department(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    agents = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="escalated_departments",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("departments")
        ordering = ["name"]

    def __str__(self):
        return self.name


class SlaPolicy(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    is_default = models.BooleanField(default=False)
    first_response_hours = models.JSONField(
        default=dict,
        help_text=_('Map of priority to hours, e.g. {"low": 24, "medium": 8, "high": 4, "urgent": 1, "critical": 0.5}'),
    )
    resolution_hours = models.JSONField(
        default=dict,
        help_text=_('Map of priority to hours, e.g. {"low": 72, "medium": 24, "high": 8, "urgent": 4, "critical": 2}'),
    )
    business_hours_only = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("sla_policies")
        verbose_name = _("SLA Policy")
        verbose_name_plural = _("SLA Policies")

    def __str__(self):
        return self.name

    def get_first_response_hours(self, priority):
        return self.first_response_hours.get(priority)

    def get_resolution_hours(self, priority):
        return self.resolution_hours.get(priority)


class Tag(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    color = models.CharField(max_length=7, default="#6b7280")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("tags")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Ticket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        IN_PROGRESS = "in_progress", _("In Progress")
        WAITING_ON_CUSTOMER = "waiting_on_customer", _("Waiting on Customer")
        WAITING_ON_AGENT = "waiting_on_agent", _("Waiting on Agent")
        ESCALATED = "escalated", _("Escalated")
        RESOLVED = "resolved", _("Resolved")
        CLOSED = "closed", _("Closed")
        REOPENED = "reopened", _("Reopened")

    class Priority(models.TextChoices):
        LOW = "low", _("Low")
        MEDIUM = "medium", _("Medium")
        HIGH = "high", _("High")
        URGENT = "urgent", _("Urgent")
        CRITICAL = "critical", _("Critical")

    class TicketType(models.TextChoices):
        QUESTION = "question", _("Question")
        PROBLEM = "problem", _("Problem")
        INCIDENT = "incident", _("Incident")
        TASK = "task", _("Task")

    # Requester via GenericForeignKey so any user model works
    requester_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="escalated_requester_tickets",
    )
    requester_object_id = models.PositiveIntegerField(null=True, blank=True)
    requester = GenericForeignKey("requester_content_type", "requester_object_id")

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalated_assigned_tickets",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets",
    )
    sla_policy = models.ForeignKey(
        SlaPolicy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets",
    )

    # Guest ticket fields (for unauthenticated users)
    guest_name = models.CharField(max_length=255, null=True, blank=True)
    guest_email = models.EmailField(null=True, blank=True)
    guest_token = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        help_text=_("Unique token for guest ticket access"),
    )

    subject = models.CharField(max_length=500)
    description = models.TextField()
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    channel = models.CharField(max_length=50, default="web")
    reference = models.CharField(max_length=20, unique=True, editable=False)
    ticket_type = models.CharField(max_length=50, choices=TicketType.choices, default=TicketType.QUESTION)
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_tickets",
    )

    # Live chat fields
    chat_ended_at = models.DateTimeField(null=True, blank=True)
    chat_metadata = models.JSONField(null=True, blank=True)

    # Snooze fields
    snoozed_until = models.DateTimeField(null=True, blank=True)
    snoozed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalated_snoozed_tickets",
    )
    status_before_snooze = models.CharField(max_length=30, null=True, blank=True)

    # SLA tracking fields
    first_response_at = models.DateTimeField(null=True, blank=True)
    first_response_due_at = models.DateTimeField(null=True, blank=True)
    resolution_due_at = models.DateTimeField(null=True, blank=True)
    sla_first_response_breached = models.BooleanField(default=False)
    sla_resolution_breached = models.BooleanField(default=False)

    # Lifecycle timestamps
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    # Extensibility
    metadata = models.JSONField(null=True, blank=True)
    tags = models.ManyToManyField(Tag, related_name="tickets", blank=True)
    followers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="TicketFollower",
        related_name="escalated_following_tickets",
        blank=True,
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Generic relation for attachments
    attachments = GenericRelation(
        "escalated.Attachment",
        content_type_field="content_type",
        object_id_field="object_id",
    )

    objects = TicketManager()

    class Meta:
        db_table = get_table_name("tickets")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["reference"]),
            models.Index(fields=["assigned_to"]),
            models.Index(fields=["ticket_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"[{self.reference}] {self.subject}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self.generate_reference()
        super().save(*args, **kwargs)

    @classmethod
    def generate_reference(cls):
        """Generate a unique ticket reference like ESC-A1B2C3."""
        prefix = EscalatedSetting.get("ticket_reference_prefix", "ESC")
        while True:
            ref = f"{prefix}-{uuid.uuid4().hex[:6].upper()}"
            if not cls.objects.filter(reference=ref).exists():
                return ref

    @property
    def is_open(self):
        return self.status in [
            self.Status.OPEN,
            self.Status.IN_PROGRESS,
            self.Status.WAITING_ON_CUSTOMER,
            self.Status.WAITING_ON_AGENT,
            self.Status.ESCALATED,
            self.Status.REOPENED,
        ]

    @property
    def is_resolved(self):
        return self.status == self.Status.RESOLVED

    @property
    def is_closed(self):
        return self.status == self.Status.CLOSED

    @property
    def is_live_chat(self):
        """Check if this ticket is a live chat conversation."""
        return self.channel == "chat"

    @property
    def is_guest(self):
        """Check if this is a guest ticket (no authenticated requester)."""
        return self.requester_content_type is None and self.guest_token is not None

    @property
    def requester_name(self):
        """Get the requester's name (works for both authenticated and guest)."""
        if self.is_guest:
            return self.guest_name or "Guest"
        try:
            user = self.requester
            if user:
                name = getattr(user, "get_full_name", lambda: str(user))()
                return name or str(user)
        except Exception:
            pass
        return "Unknown"

    @property
    def requester_email(self):
        """Get the requester's email (works for both authenticated and guest)."""
        if self.is_guest:
            return self.guest_email or ""
        try:
            user = self.requester
            if user:
                return getattr(user, "email", "")
        except Exception:
            pass
        return ""

    def is_followed_by(self, user_id):
        """Check if a user is following this ticket."""
        return self.ticket_followers.filter(user_id=user_id).exists()

    def follow(self, user_id):
        """Add a follower to this ticket (idempotent)."""
        TicketFollower.objects.get_or_create(ticket=self, user_id=user_id)

    def unfollow(self, user_id):
        """Remove a follower from this ticket."""
        self.ticket_followers.filter(user_id=user_id).delete()

    @property
    def followers_count(self):
        """Return the number of followers on this ticket."""
        return self.ticket_followers.count()

    @property
    def sla_first_response_remaining(self):
        if not self.first_response_due_at or self.first_response_at:
            return None
        return self.first_response_due_at - timezone.now()

    @property
    def sla_resolution_remaining(self):
        if not self.resolution_due_at or self.resolved_at:
            return None
        return self.resolution_due_at - timezone.now()

    # ----- Snooze helpers -----

    @property
    def last_reply_at(self):
        """Return the timestamp of the latest reply, or None."""
        last = self.replies.filter(is_deleted=False).order_by("-created_at").first()
        return last.created_at if last else None

    @property
    def last_reply_author(self):
        """Return the name of the latest reply's author, or None."""
        last = self.replies.filter(is_deleted=False).order_by("-created_at").first()
        if last is None:
            return None
        author = last.author
        if author is None:
            return None
        name = getattr(author, "get_full_name", lambda: str(author))()
        return name or str(author)

    @property
    def is_snoozed(self):
        """Check if the ticket is currently snoozed."""
        return self.snoozed_until is not None and self.snoozed_until > timezone.now()

    def snooze(self, until, user=None):
        """
        Snooze this ticket until the given datetime.

        Saves the current status so it can be restored on unsnooze.
        """
        self.status_before_snooze = self.status
        self.snoozed_until = until
        self.snoozed_by = user
        self.status = self.Status.CLOSED
        self.save(update_fields=["status", "snoozed_until", "snoozed_by", "status_before_snooze", "updated_at"])

    def unsnooze(self):
        """
        Unsnooze this ticket, restoring its previous status.
        """
        restored_status = self.status_before_snooze or self.Status.OPEN
        self.status = restored_status
        self.snoozed_until = None
        self.snoozed_by = None
        self.status_before_snooze = None
        self.save(update_fields=["status", "snoozed_until", "snoozed_by", "status_before_snooze", "updated_at"])


class Reply(models.Model):
    class Type(models.TextChoices):
        REPLY = "reply", _("Reply")
        NOTE = "note", _("Internal Note")
        SYSTEM = "system", _("System")

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalated_replies",
    )
    body = models.TextField()
    is_internal_note = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.REPLY)
    metadata = models.JSONField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Generic relation for attachments
    attachments = GenericRelation(
        "escalated.Attachment",
        content_type_field="content_type",
        object_id_field="object_id",
    )

    class Meta:
        db_table = get_table_name("replies")
        ordering = ["created_at"]

    def __str__(self):
        return f"Reply on {self.ticket.reference} by {self.author}"

    def soft_delete(self):
        self.is_deleted = True
        self.save(update_fields=["is_deleted", "updated_at"])


class Attachment(models.Model):
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="escalated_attachments",
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    file = models.FileField(upload_to="escalated/attachments/%Y/%m/")
    original_filename = models.CharField(max_length=500)
    mime_type = models.CharField(max_length=255, blank=True, default="")
    size = models.PositiveIntegerField(default=0, help_text=_("File size in bytes"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("attachments")
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_filename

    @property
    def size_kb(self):
        return self.size / 1024


class EscalationRule(models.Model):
    class TriggerType(models.TextChoices):
        SLA_BREACH = "sla_breach", _("SLA Breach")
        PRIORITY_CHANGE = "priority_change", _("Priority Change")
        NO_RESPONSE = "no_response", _("No Response")
        CUSTOMER_REPLY = "customer_reply", _("Customer Reply")
        TIME_BASED = "time_based", _("Time Based")

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    trigger_type = models.CharField(max_length=30, choices=TriggerType.choices)
    conditions = models.JSONField(
        default=dict,
        help_text=_("JSON conditions that must be met for the rule to fire"),
    )
    actions = models.JSONField(
        default=dict,
        help_text=_("JSON actions to take when the rule fires (e.g., assign, notify, change priority)"),
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("escalation_rules")
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class CannedResponse(models.Model):
    title = models.CharField(max_length=255)
    body = models.TextField()
    category = models.CharField(max_length=100, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalated_canned_responses",
    )
    is_shared = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("canned_responses")
        ordering = ["category", "title"]

    def __str__(self):
        return self.title


class TicketActivity(models.Model):
    class ActivityType(models.TextChoices):
        CREATED = "created", _("Created")
        STATUS_CHANGED = "status_changed", _("Status Changed")
        PRIORITY_CHANGED = "priority_changed", _("Priority Changed")
        ASSIGNED = "assigned", _("Assigned")
        UNASSIGNED = "unassigned", _("Unassigned")
        REPLY_ADDED = "reply_added", _("Reply Added")
        NOTE_ADDED = "note_added", _("Note Added")
        TAG_ADDED = "tag_added", _("Tag Added")
        TAG_REMOVED = "tag_removed", _("Tag Removed")
        DEPARTMENT_CHANGED = "department_changed", _("Department Changed")
        ESCALATED = "escalated", _("Escalated")
        SLA_BREACHED = "sla_breached", _("SLA Breached")
        ATTACHMENT_ADDED = "attachment_added", _("Attachment Added")
        MERGED = "merged", _("Merged")

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="activities")

    # Causer via GenericForeignKey
    causer_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalated_activities",
    )
    causer_object_id = models.PositiveIntegerField(null=True, blank=True)
    causer = GenericForeignKey("causer_content_type", "causer_object_id")

    type = models.CharField(max_length=30, choices=ActivityType.choices)
    properties = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = get_table_name("activities")
        ordering = ["-created_at"]
        verbose_name_plural = _("Ticket activities")

    def __str__(self):
        return f"{self.type} on {self.ticket.reference}"


class EscalatedSetting(models.Model):
    """Key-value settings store for Escalated configuration."""

    key = models.CharField(max_length=255, unique=True)
    value = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("settings")

    def __str__(self):
        return f"{self.key} = {self.value}"

    @classmethod
    def get(cls, key, default=None):
        """Get a setting value by key."""
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(cls, key, value):
        """Set a setting value by key."""
        obj, _ = cls.objects.update_or_create(key=key, defaults={"value": str(value) if value is not None else None})
        return obj

    @classmethod
    def get_bool(cls, key, default=False):
        """Get a boolean setting."""
        val = cls.get(key)
        if val is None:
            return default
        return val in ("1", "true", "True", "yes")

    @classmethod
    def get_int(cls, key, default=0):
        """Get an integer setting."""
        val = cls.get(key)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    @classmethod
    def guest_tickets_enabled(cls):
        """Check if guest tickets are enabled."""
        return cls.get_bool("guest_tickets_enabled", default=True)


class Macro(models.Model):
    """Reusable sets of actions that can be applied to tickets."""

    name = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True, default="")
    actions = models.JSONField(
        default=list,
        help_text=_('JSON array of actions, e.g. [{"type": "set_status", "value": "open"}]'),
    )
    is_shared = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalated_macros",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("macros")
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class TicketFollower(models.Model):
    """Join table tracking which users follow which tickets."""

    ticket = models.ForeignKey(
        "Ticket",
        on_delete=models.CASCADE,
        related_name="ticket_followers",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="escalated_followed_tickets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("ticket_followers")
        constraints = [
            models.UniqueConstraint(
                fields=["ticket", "user"],
                name="escalated_tf_ticket_user_uniq",
            ),
        ]

    def __str__(self):
        return f"User {self.user_id} follows Ticket {self.ticket_id}"


class SatisfactionRating(models.Model):
    """Customer satisfaction rating for a ticket (one per ticket)."""

    ticket = models.OneToOneField(
        "Ticket",
        on_delete=models.CASCADE,
        related_name="satisfaction_rating",
    )
    rating = models.PositiveSmallIntegerField(
        help_text=_("Rating from 1 to 5"),
    )
    comment = models.TextField(blank=True, null=True)

    # GenericFK for the rater (authenticated user or null for guests)
    rated_by_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="escalated_satisfaction_ratings",
    )
    rated_by_object_id = models.PositiveIntegerField(null=True, blank=True)
    rated_by = GenericForeignKey("rated_by_content_type", "rated_by_object_id")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = get_table_name("satisfaction_ratings")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Rating {self.rating}/5 for {self.ticket}"


class InboundEmail(models.Model):
    """Tracks inbound emails received via webhook or IMAP polling."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSED = "processed", _("Processed")
        FAILED = "failed", _("Failed")
        SPAM = "spam", _("Spam")

    message_id = models.CharField(max_length=500, unique=True, null=True, blank=True)
    from_email = models.CharField(max_length=500)
    from_name = models.CharField(max_length=500, null=True, blank=True)
    to_email = models.CharField(max_length=500)
    subject = models.CharField(max_length=1000)
    body_text = models.TextField(null=True, blank=True)
    body_html = models.TextField(null=True, blank=True)
    raw_headers = models.TextField(null=True, blank=True)

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inbound_emails",
    )
    reply = models.ForeignKey(
        Reply,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inbound_emails",
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    adapter = models.CharField(max_length=50)
    error_message = models.TextField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("inbound_emails")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["from_email"]),
            models.Index(fields=["message_id"]),
        ]

    def __str__(self):
        return f"InboundEmail({self.from_email} -> {self.to_email}: {self.subject[:50]})"

    def mark_processed(self, ticket, reply=None):
        """Mark this inbound email as successfully processed."""
        self.status = self.Status.PROCESSED
        self.ticket = ticket
        self.reply = reply
        self.processed_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "ticket",
                "reply",
                "processed_at",
                "updated_at",
            ]
        )

    def mark_failed(self, error_message):
        """Mark this inbound email as failed."""
        self.status = self.Status.FAILED
        self.error_message = error_message
        self.save(update_fields=["status", "error_message", "updated_at"])

    def mark_spam(self):
        """Mark this inbound email as spam."""
        self.status = self.Status.SPAM
        self.save(update_fields=["status", "updated_at"])


# ---------------------------------------------------------------------------
# API Token
# ---------------------------------------------------------------------------


class ApiTokenQuerySet(models.QuerySet):
    def active(self):
        """Return tokens that are not expired."""
        return self.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))

    def expired(self):
        """Return tokens that have expired."""
        return self.filter(
            expires_at__isnull=False,
            expires_at__lte=timezone.now(),
        )


class ApiTokenManager(models.Manager):
    def get_queryset(self):
        return ApiTokenQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

    def expired(self):
        return self.get_queryset().expired()


class ApiToken(models.Model):
    """API token for authenticating REST API requests."""

    # Tokenable via GenericForeignKey (like Laravel morphTo)
    tokenable_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="escalated_api_tokens",
    )
    tokenable_object_id = models.PositiveIntegerField(null=True, blank=True)
    tokenable = GenericForeignKey("tokenable_content_type", "tokenable_object_id")

    name = models.CharField(max_length=255)
    token = models.CharField(max_length=64, unique=True, db_index=True)
    abilities = models.JSONField(default=list)
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.CharField(max_length=45, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ApiTokenManager()

    class Meta:
        db_table = get_table_name("api_tokens")
        ordering = ["-created_at"]

    def __str__(self):
        return f"ApiToken({self.name})"

    def has_ability(self, ability):
        """Check if this token has the given ability."""
        abilities = self.abilities or []
        return "*" in abilities or ability in abilities

    @property
    def is_expired(self):
        """Check if this token has expired."""
        if self.expires_at is None:
            return False
        return self.expires_at <= timezone.now()

    @classmethod
    def create_token(cls, user, name, abilities=None, expires_at=None):
        """
        Create a new API token for a user.

        Returns a dict with 'token' (the model instance) and
        'plain_text_token' (the unhashed token string to give to the user).
        """
        if abilities is None:
            abilities = ["*"]

        plain_text = secrets.token_hex(32)
        hashed = hashlib.sha256(plain_text.encode()).hexdigest()

        ct = ContentType.objects.get_for_model(user)
        token = cls.objects.create(
            tokenable_content_type=ct,
            tokenable_object_id=user.pk,
            name=name,
            token=hashed,
            abilities=abilities,
            expires_at=expires_at,
        )

        return {"token": token, "plain_text_token": plain_text}

    @classmethod
    def find_by_plain_text(cls, plain_text):
        """Look up a token by its plain-text value (hashes it first)."""
        hashed = hashlib.sha256(plain_text.encode()).hexdigest()
        try:
            return cls.objects.get(token=hashed)
        except cls.DoesNotExist:
            return None


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalated_audit_logs",
    )
    action = models.CharField(max_length=50)
    auditable_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="escalated_audit_logs",
    )
    auditable_object_id = models.PositiveIntegerField()
    auditable = GenericForeignKey("auditable_content_type", "auditable_object_id")
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = get_table_name("audit_logs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["auditable_content_type", "auditable_object_id"]),
            models.Index(fields=["user"]),
            models.Index(fields=["action"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.action} on {self.auditable_content_type} #{self.auditable_object_id}"


# ---------------------------------------------------------------------------
# Ticket Status
# ---------------------------------------------------------------------------


class TicketStatus(models.Model):
    CATEGORY_CHOICES = [
        ("new", _("New")),
        ("open", _("Open")),
        ("pending", _("Pending")),
        ("on_hold", _("On Hold")),
        ("solved", _("Solved")),
    ]

    label = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    color = models.CharField(max_length=20, default="#6b7280")
    description = models.TextField(blank=True, default="")
    position = models.IntegerField(default=0)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("ticket_statuses")
        ordering = ["category", "position"]

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.label).replace("-", "_")
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Business Schedule & Holiday
# ---------------------------------------------------------------------------


class BusinessSchedule(models.Model):
    name = models.CharField(max_length=255)
    timezone = models.CharField(max_length=100, default="UTC")
    is_default = models.BooleanField(default=False)
    schedule = models.JSONField(
        default=dict,
        help_text=_('Day schedules, e.g. {"monday": {"start": "09:00", "end": "17:00"}}'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("business_schedules")

    def __str__(self):
        return self.name


class Holiday(models.Model):
    schedule = models.ForeignKey(
        BusinessSchedule,
        on_delete=models.CASCADE,
        related_name="holidays",
    )
    name = models.CharField(max_length=255)
    date = models.DateField()
    recurring = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("holidays")

    def __str__(self):
        return f"{self.name} ({self.date})"


# ---------------------------------------------------------------------------
# Role & Permission
# ---------------------------------------------------------------------------


class Permission(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    group = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = get_table_name("permissions")
        ordering = ["group", "name"]

    def __str__(self):
        return self.name


class Role(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(
        "Permission",
        related_name="roles",
        blank=True,
        db_table=get_table_name("role_permission"),
    )
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="escalated_roles",
        blank=True,
        db_table=get_table_name("role_user"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("roles")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.name).replace("-", "_")
        super().save(*args, **kwargs)

    def has_permission(self, slug):
        return self.permissions.filter(slug=slug).exists()


# ---------------------------------------------------------------------------
# Custom Fields
# ---------------------------------------------------------------------------


class CustomField(models.Model):
    class FieldType(models.TextChoices):
        TEXT = "text", _("Text")
        TEXTAREA = "textarea", _("Textarea")
        SELECT = "select", _("Select")
        MULTI_SELECT = "multi_select", _("Multi Select")
        CHECKBOX = "checkbox", _("Checkbox")
        DATE = "date", _("Date")
        NUMBER = "number", _("Number")

    class Context(models.TextChoices):
        TICKET = "ticket", _("Ticket")
        USER = "user", _("User")
        ORGANIZATION = "organization", _("Organization")

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    type = models.CharField(max_length=50, choices=FieldType.choices)
    context = models.CharField(max_length=50, choices=Context.choices, default=Context.TICKET)
    options = models.JSONField(null=True, blank=True)
    required = models.BooleanField(default=False)
    placeholder = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(blank=True, default="")
    validation_rules = models.JSONField(null=True, blank=True)
    conditions = models.JSONField(null=True, blank=True)
    position = models.IntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("custom_fields")
        ordering = ["position"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.name).replace("-", "_")
        super().save(*args, **kwargs)


class CustomFieldValue(models.Model):
    custom_field = models.ForeignKey(
        CustomField,
        on_delete=models.CASCADE,
        related_name="values",
    )
    entity_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
    )
    entity_object_id = models.PositiveIntegerField()
    entity = GenericForeignKey("entity_content_type", "entity_object_id")
    value = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("custom_field_values")

    def __str__(self):
        return f"{self.custom_field.name}: {self.value}"


# ---------------------------------------------------------------------------
# Saved Views
# ---------------------------------------------------------------------------


class SavedView(models.Model):
    """Custom saved filter / queue for tickets."""

    name = models.CharField(max_length=255)
    filters = models.JSONField(default=dict)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="escalated_saved_views",
    )
    is_shared = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    position = models.IntegerField(default=0)
    icon = models.CharField(max_length=100, blank=True, default="")
    color = models.CharField(max_length=20, blank=True, default="#6b7280")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("saved_views")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Ticket Links
# ---------------------------------------------------------------------------


class TicketLink(models.Model):
    class LinkType(models.TextChoices):
        PROBLEM_INCIDENT = "problem_incident", _("Problem / Incident")
        PARENT_CHILD = "parent_child", _("Parent / Child")
        RELATED = "related", _("Related")

    parent_ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="links_as_parent",
    )
    child_ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="links_as_child",
    )
    link_type = models.CharField(max_length=50, choices=LinkType.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("ticket_links")
        unique_together = [("parent_ticket", "child_ticket", "link_type")]

    def __str__(self):
        return f"{self.parent_ticket} -> {self.child_ticket} ({self.link_type})"


# ---------------------------------------------------------------------------
# Side Conversations
# ---------------------------------------------------------------------------


class SideConversationQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status="open")


class SideConversationManager(models.Manager):
    def get_queryset(self):
        return SideConversationQuerySet(self.model, using=self._db)

    def open(self):
        return self.get_queryset().open()


class SideConversation(models.Model):
    class Channel(models.TextChoices):
        INTERNAL = "internal", _("Internal")
        EMAIL = "email", _("Email")

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        CLOSED = "closed", _("Closed")

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="side_conversations",
    )
    subject = models.CharField(max_length=255)
    channel = models.CharField(max_length=50, choices=Channel.choices, default=Channel.INTERNAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalated_side_conversations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SideConversationManager()

    class Meta:
        db_table = get_table_name("side_conversations")

    def __str__(self):
        return f"Side conversation: {self.subject}"


class SideConversationReply(models.Model):
    side_conversation = models.ForeignKey(
        SideConversation,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    body = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalated_side_conversation_replies",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("side_conversation_replies")

    def __str__(self):
        return f"Reply on {self.side_conversation.subject}"


# ---------------------------------------------------------------------------
# Knowledge Base
# ---------------------------------------------------------------------------


class ArticleCategoryQuerySet(models.QuerySet):
    def roots(self):
        return self.filter(parent__isnull=True)

    def ordered(self):
        return self.order_by("position", "name")


class ArticleCategoryManager(models.Manager):
    def get_queryset(self):
        return ArticleCategoryQuerySet(self.model, using=self._db)

    def roots(self):
        return self.get_queryset().roots()

    def ordered(self):
        return self.get_queryset().ordered()


class ArticleCategory(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    position = models.IntegerField(default=0)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ArticleCategoryManager()

    class Meta:
        db_table = get_table_name("article_categories")
        verbose_name_plural = _("Article categories")

    def __str__(self):
        return self.name


class ArticleQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status="published")

    def draft(self):
        return self.filter(status="draft")

    def search(self, term):
        return self.filter(Q(title__icontains=term) | Q(body__icontains=term))


class ArticleManager(models.Manager):
    def get_queryset(self):
        return ArticleQuerySet(self.model, using=self._db)

    def published(self):
        return self.get_queryset().published()

    def draft(self):
        return self.get_queryset().draft()

    def search(self, term):
        return self.get_queryset().search(term)


class Article(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")

    category = models.ForeignKey(
        ArticleCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    body = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalated_articles",
    )
    view_count = models.PositiveIntegerField(default=0)
    helpful_count = models.PositiveIntegerField(default=0)
    not_helpful_count = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ArticleManager()

    class Meta:
        db_table = get_table_name("articles")
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def increment_views(self):
        """Increment the view count by one."""
        self.view_count += 1
        self.save(update_fields=["view_count", "updated_at"])

    def mark_helpful(self):
        """Increment the helpful count by one."""
        self.helpful_count += 1
        self.save(update_fields=["helpful_count", "updated_at"])

    def mark_not_helpful(self):
        """Increment the not-helpful count by one."""
        self.not_helpful_count += 1
        self.save(update_fields=["not_helpful_count", "updated_at"])


# ---------------------------------------------------------------------------
# Phase 3: Agent & Routing
# ---------------------------------------------------------------------------


class AgentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="escalated_agent_profile",
    )

    class ChatStatus(models.TextChoices):
        ONLINE = "online", _("Online")
        AWAY = "away", _("Away")
        OFFLINE = "offline", _("Offline")

    agent_type = models.CharField(max_length=20, default="full")
    max_tickets = models.PositiveIntegerField(null=True, blank=True)
    chat_status = models.CharField(max_length=20, choices=ChatStatus.choices, default=ChatStatus.OFFLINE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("agent_profiles")

    def __str__(self):
        return f"Agent profile for {self.user}"

    def is_chat_online(self) -> bool:
        return self.chat_status == self.ChatStatus.ONLINE

    def is_light_agent(self) -> bool:
        return self.agent_type == "light"

    def is_full_agent(self) -> bool:
        return self.agent_type == "full"

    @classmethod
    def for_user(cls, user_id):
        """Get or create an agent profile for the given user ID."""
        obj, _ = cls.objects.get_or_create(
            user_id=user_id,
            defaults={"agent_type": "full"},
        )
        return obj


class AgentSkill(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    skill = models.ForeignKey(
        "Skill",
        on_delete=models.CASCADE,
        related_name="agent_skills",
    )
    proficiency = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = get_table_name("agent_skill")
        unique_together = [("user", "skill")]

    def __str__(self):
        return f"{self.user} - {self.skill} ({self.proficiency})"


class Skill(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    agents = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="AgentSkill",
        related_name="escalated_skills",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("skills")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class AgentCapacity(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="escalated_agent_capacities",
    )
    channel = models.CharField(max_length=50, default="default")
    max_concurrent = models.PositiveIntegerField(default=10)
    current_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("agent_capacity")
        unique_together = [("user", "channel")]

    def __str__(self):
        return f"{self.user} - {self.channel}"

    def load_percentage(self) -> float:
        if self.max_concurrent <= 0:
            return 100.0
        return round((self.current_count / self.max_concurrent) * 100, 1)

    def has_capacity(self) -> bool:
        return self.current_count < self.max_concurrent


# ---------------------------------------------------------------------------
# Phase 4: Automation & Integration
# ---------------------------------------------------------------------------


class WebhookQuerySet(models.QuerySet):
    def active(self):
        return self.filter(active=True)


class WebhookManager(models.Manager):
    def get_queryset(self):
        return WebhookQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()


class Webhook(models.Model):
    url = models.URLField(max_length=500)
    events = models.JSONField(default=list)
    secret = models.CharField(max_length=255, null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = WebhookManager()

    class Meta:
        db_table = get_table_name("webhooks")

    def __str__(self):
        return self.url

    def subscribed_to(self, event: str) -> bool:
        return event in (self.events or [])


class WebhookDelivery(models.Model):
    webhook = models.ForeignKey(
        Webhook,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    event = models.CharField(max_length=100)
    payload = models.JSONField(null=True, blank=True)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.TextField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("webhook_deliveries")

    def __str__(self):
        return f"Delivery {self.pk} for {self.webhook}"

    def is_success(self) -> bool:
        return self.response_code is not None and 200 <= self.response_code <= 299


class AutomationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(active=True).order_by("position")


class AutomationManager(models.Manager):
    def get_queryset(self):
        return AutomationQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()


class Automation(models.Model):
    name = models.CharField(max_length=255)
    conditions = models.JSONField(default=list)
    actions = models.JSONField(default=list)
    active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AutomationManager()

    class Meta:
        db_table = get_table_name("automations")
        indexes = [
            models.Index(fields=["active"]),
        ]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Phase 5: Security & Enterprise
# ---------------------------------------------------------------------------


class TwoFactor(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="escalated_two_factor",
    )
    secret = models.TextField()
    recovery_codes = models.JSONField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("two_factor")

    def __str__(self):
        return f"2FA for {self.user}"

    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None


class CustomObject(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    fields_schema = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("custom_objects")

    def __str__(self):
        return self.name


class CustomObjectRecord(models.Model):
    object = models.ForeignKey(
        CustomObject,
        on_delete=models.CASCADE,
        related_name="records",
    )
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("custom_object_records")

    def __str__(self):
        return f"Record {self.pk} for {self.object.name}"


# ---------------------------------------------------------------------------
# Import Framework
# ---------------------------------------------------------------------------


class EncryptedJSONField(models.TextField):
    """
    A TextField that transparently encrypts/decrypts a JSON-serialisable
    value using Fernet symmetric encryption derived from Django's SECRET_KEY.

    The encrypted blob is stored as a base64 URL-safe string prefixed with
    ``"enc::"`` so we can tell encrypted values from plain NULL/empty strings.
    """

    PREFIX = "enc::"

    def _get_fernet(self):
        import base64
        import hashlib

        from cryptography.fernet import Fernet
        from django.conf import settings as django_settings

        # Derive a 32-byte key from SECRET_KEY
        raw = hashlib.sha256(django_settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(raw)
        return Fernet(key)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        if isinstance(value, str) and value.startswith(self.PREFIX):
            import json

            fernet = self._get_fernet()
            decrypted = fernet.decrypt(value[len(self.PREFIX) :].encode()).decode()
            return json.loads(decrypted)
        # Legacy plain JSON (shouldn't happen in prod, but handles dev fixtures)
        import json

        try:
            return json.loads(value)
        except Exception:
            return value

    def to_python(self, value):
        if isinstance(value, (dict, list)) or value is None:
            return value
        return self.from_db_value(value, None, None)

    def get_prep_value(self, value):
        if value is None:
            return None
        import json

        fernet = self._get_fernet()
        plaintext = json.dumps(value).encode()
        token = fernet.encrypt(plaintext).decode()
        return self.PREFIX + token


class ImportJob(models.Model):
    """
    Tracks a single platform import run from start to completion.

    State machine
    -------------
    pending → authenticating → mapping → importing → completed
                             ↘ failed ↙              ↘ paused ←→ importing
    failed → mapping  (to allow re-mapping after credential fix)

    Credentials are stored encrypted at rest.  They are purged once the
    import completes successfully.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        AUTHENTICATING = "authenticating", _("Authenticating")
        MAPPING = "mapping", _("Mapping")
        IMPORTING = "importing", _("Importing")
        PAUSED = "paused", _("Paused")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    VALID_TRANSITIONS: dict[str, list[str]] = {
        "pending": ["authenticating"],
        "authenticating": ["mapping", "failed"],
        "mapping": ["importing", "failed"],
        "importing": ["paused", "completed", "failed"],
        "paused": ["importing", "failed"],
        "completed": [],
        "failed": ["mapping"],
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    credentials = EncryptedJSONField(null=True, blank=True)
    field_mappings = models.JSONField(default=dict, blank=True)
    progress = models.JSONField(default=dict, blank=True)
    error_log = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("import_jobs")
        ordering = ["-created_at"]

    def __str__(self):
        return f"ImportJob({self.platform}, {self.status}) [{self.id}]"

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def transition_to(self, new_status: str) -> None:
        """
        Transition to *new_status*, saving immediately.

        Raises ``ValueError`` if the transition is not permitted by the
        state machine.
        """
        current = self.status or "pending"
        allowed = self.VALID_TRANSITIONS.get(current, [])

        if new_status not in allowed:
            raise ValueError(f"Cannot transition ImportJob from '{current}' to '{new_status}'.")

        self.status = new_status
        self.save(update_fields=["status", "updated_at"])

    # ------------------------------------------------------------------
    # Progress helpers
    # ------------------------------------------------------------------

    def update_entity_progress(
        self,
        entity_type: str,
        *,
        processed: int = None,
        total: int = None,
        skipped: int = None,
        failed: int = None,
        cursor: str = None,
    ) -> None:
        """Merge partial progress for a single entity type and save."""
        progress = dict(self.progress or {})
        current = progress.get(
            entity_type,
            {
                "total": 0,
                "processed": 0,
                "skipped": 0,
                "failed": 0,
                "cursor": None,
            },
        )

        if processed is not None:
            current["processed"] = processed
        if total is not None:
            current["total"] = total
        if skipped is not None:
            current["skipped"] = skipped
        if failed is not None:
            current["failed"] = failed
        if cursor is not None:
            current["cursor"] = cursor

        progress[entity_type] = current
        self.progress = progress
        self.save(update_fields=["progress", "updated_at"])

    def get_entity_cursor(self, entity_type: str):
        """Return the saved pagination cursor for *entity_type*, or ``None``."""
        return (self.progress or {}).get(entity_type, {}).get("cursor")

    def append_error(self, entity_type: str, source_id: str, error: str) -> None:
        """Append an error entry to the log (capped at 10 000 entries)."""
        log = list(self.error_log or [])
        if len(log) < 10_000:
            log.append(
                {
                    "entity_type": entity_type,
                    "source_id": source_id,
                    "error": error,
                    "timestamp": timezone.now().isoformat(),
                }
            )
            self.error_log = log
            self.save(update_fields=["error_log", "updated_at"])

    def purge_credentials(self) -> None:
        """Remove stored credentials once the import is complete."""
        self.credentials = None
        self.save(update_fields=["credentials", "updated_at"])

    def is_resumable(self) -> bool:
        """Return True if this job can be resumed (paused or failed)."""
        return self.status in (self.Status.PAUSED, self.Status.FAILED)


class ImportSourceMap(models.Model):
    """
    Maps a source platform ID to an Escalated internal ID.

    Used for:
    - Skip-deduplication (resume after pause/failure).
    - Cross-referencing during import (e.g. linking a reply to its ticket).

    No ``updated_at`` column — records are write-once.
    """

    import_job = models.ForeignKey(
        ImportJob,
        on_delete=models.CASCADE,
        related_name="source_maps",
    )
    entity_type = models.CharField(max_length=100)
    source_id = models.CharField(max_length=255)
    escalated_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = get_table_name("import_source_maps")
        constraints = [
            models.UniqueConstraint(
                fields=["import_job", "entity_type", "source_id"],
                name="unique_import_source_map",
            )
        ]
        indexes = [
            models.Index(
                fields=["import_job", "entity_type", "source_id"],
                name="idx_import_source_map_lookup",
            )
        ]

    def __str__(self):
        return f"ImportSourceMap({self.entity_type} {self.source_id} → {self.escalated_id})"

    # ------------------------------------------------------------------
    # Class-level helpers
    # ------------------------------------------------------------------

    @classmethod
    def resolve(cls, job_id, entity_type: str, source_id: str):
        """
        Return the Escalated ID for a given source ID, or ``None`` if not yet
        imported.
        """
        return (
            cls.objects.filter(
                import_job_id=job_id,
                entity_type=entity_type,
                source_id=source_id,
            )
            .values_list("escalated_id", flat=True)
            .first()
        )

    @classmethod
    def has_been_imported(cls, job_id, entity_type: str, source_id: str) -> bool:
        """Return True if this source record has already been imported."""
        return cls.resolve(job_id, entity_type, source_id) is not None


# ---------------------------------------------------------------------------
# Live Chat Models
# ---------------------------------------------------------------------------


class ChatSessionQuerySet(models.QuerySet):
    def waiting(self):
        return self.filter(status=ChatSession.Status.WAITING)

    def active(self):
        return self.filter(status=ChatSession.Status.ACTIVE)

    def ended(self):
        return self.filter(status=ChatSession.Status.ENDED)

    def abandoned(self):
        return self.filter(status=ChatSession.Status.ABANDONED)

    def for_agent(self, user_id):
        return self.filter(agent_id=user_id)

    def for_customer(self, session_id):
        return self.filter(customer_session_id=session_id)


class ChatSessionManager(models.Manager):
    def get_queryset(self):
        return ChatSessionQuerySet(self.model, using=self._db)

    def waiting(self):
        return self.get_queryset().waiting()

    def active(self):
        return self.get_queryset().active()

    def ended(self):
        return self.get_queryset().ended()

    def for_agent(self, user_id):
        return self.get_queryset().for_agent(user_id)

    def for_customer(self, session_id):
        return self.get_queryset().for_customer(session_id)


class ChatSession(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", _("Waiting")
        ACTIVE = "active", _("Active")
        ENDED = "ended", _("Ended")
        ABANDONED = "abandoned", _("Abandoned")

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="chat_sessions")
    customer_session_id = models.CharField(max_length=255, db_index=True)
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalated_chat_sessions",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING, db_index=True)
    customer_typing_at = models.DateTimeField(null=True, blank=True)
    agent_typing_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_comment = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ChatSessionManager()

    class Meta:
        db_table = get_table_name("chat_sessions")
        ordering = ["-created_at"]

    def __str__(self):
        return f"ChatSession {self.pk} ({self.status})"

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    @property
    def is_waiting(self):
        return self.status == self.Status.WAITING


class ChatRoutingRuleQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def for_department(self, department_id):
        return self.filter(Q(department_id=department_id) | Q(department__isnull=True))


class ChatRoutingRuleManager(models.Manager):
    def get_queryset(self):
        return ChatRoutingRuleQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

    def for_department(self, department_id):
        return self.get_queryset().for_department(department_id)


class ChatRoutingRule(models.Model):
    class RoutingStrategy(models.TextChoices):
        ROUND_ROBIN = "round_robin", _("Round Robin")
        LEAST_ACTIVE = "least_active", _("Least Active")
        RANDOM = "random", _("Random")

    class OfflineBehavior(models.TextChoices):
        QUEUE = "queue", _("Queue")
        TICKET = "ticket", _("Create Ticket")
        HIDE = "hide", _("Hide Chat")

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="chat_routing_rules",
    )
    routing_strategy = models.CharField(
        max_length=30,
        choices=RoutingStrategy.choices,
        default=RoutingStrategy.ROUND_ROBIN,
    )
    offline_behavior = models.CharField(
        max_length=30,
        choices=OfflineBehavior.choices,
        default=OfflineBehavior.TICKET,
    )
    max_concurrent_chats = models.PositiveIntegerField(default=5)
    welcome_message = models.TextField(blank=True, default="")
    offline_message = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ChatRoutingRuleManager()

    class Meta:
        db_table = get_table_name("chat_routing_rules")
        ordering = ["position"]

    def __str__(self):
        dept = self.department.name if self.department else "Global"
        return f"ChatRoutingRule: {dept} ({self.routing_strategy})"
