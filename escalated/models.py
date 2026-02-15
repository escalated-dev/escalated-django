import uuid
from datetime import timedelta

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
        return self.filter(
            Q(sla_first_response_breached=True) | Q(sla_resolution_breached=True)
        )

    def search(self, term):
        return self.filter(
            Q(subject__icontains=term)
            | Q(description__icontains=term)
            | Q(reference__icontains=term)
        )

    def by_department(self, department_id):
        return self.filter(department_id=department_id)

    def by_priority(self, priority):
        return self.filter(priority=priority)

    def by_status(self, status):
        return self.filter(status=status)

    def followed_by(self, user_id):
        """Filter tickets that are followed by a specific user."""
        return self.filter(ticket_followers__user_id=user_id)


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
        max_length=64, null=True, blank=True, unique=True,
        help_text=_("Unique token for guest ticket access"),
    )

    subject = models.CharField(max_length=500)
    description = models.TextField()
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.OPEN
    )
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.MEDIUM
    )
    channel = models.CharField(max_length=50, default="web")
    reference = models.CharField(max_length=20, unique=True, editable=False)

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


class Reply(models.Model):
    class Type(models.TextChoices):
        REPLY = "reply", _("Reply")
        NOTE = "note", _("Internal Note")
        SYSTEM = "system", _("System")

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="replies"
    )
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
    size = models.PositiveIntegerField(
        default=0, help_text=_("File size in bytes")
    )
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

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="activities"
    )

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
        obj, _ = cls.objects.update_or_create(
            key=key, defaults={"value": str(value) if value is not None else None}
        )
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

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
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
        self.save(update_fields=[
            "status", "ticket", "reply", "processed_at", "updated_at",
        ])

    def mark_failed(self, error_message):
        """Mark this inbound email as failed."""
        self.status = self.Status.FAILED
        self.error_message = error_message
        self.save(update_fields=["status", "error_message", "updated_at"])

    def mark_spam(self):
        """Mark this inbound email as spam."""
        self.status = self.Status.SPAM
        self.save(update_fields=["status", "updated_at"])
