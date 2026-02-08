import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        # Department
        migrations.CreateModel(
            name="Department",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=255, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "agents",
                    models.ManyToManyField(
                        blank=True,
                        related_name="escalated_departments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("departments"),
                "ordering": ["name"],
            },
        ),
        # SlaPolicy
        migrations.CreateModel(
            name="SlaPolicy",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("is_default", models.BooleanField(default=False)),
                (
                    "first_response_hours",
                    models.JSONField(
                        default=dict,
                        help_text='Map of priority to hours, e.g. {"low": 24, "medium": 8, "high": 4, "urgent": 1, "critical": 0.5}',
                    ),
                ),
                (
                    "resolution_hours",
                    models.JSONField(
                        default=dict,
                        help_text='Map of priority to hours, e.g. {"low": 72, "medium": 24, "high": 8, "urgent": 4, "critical": 2}',
                    ),
                ),
                ("business_hours_only", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("sla_policies"),
                "verbose_name": "SLA Policy",
                "verbose_name_plural": "SLA Policies",
            },
        ),
        # Tag
        migrations.CreateModel(
            name="Tag",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=100, unique=True)),
                ("color", models.CharField(default="#6b7280", max_length=7)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("tags"),
                "ordering": ["name"],
            },
        ),
        # Ticket
        migrations.CreateModel(
            name="Ticket",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "requester_object_id",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("subject", models.CharField(max_length=500)),
                ("description", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("in_progress", "In Progress"),
                            ("waiting_on_customer", "Waiting on Customer"),
                            ("waiting_on_agent", "Waiting on Agent"),
                            ("escalated", "Escalated"),
                            ("resolved", "Resolved"),
                            ("closed", "Closed"),
                            ("reopened", "Reopened"),
                        ],
                        default="open",
                        max_length=30,
                    ),
                ),
                (
                    "priority",
                    models.CharField(
                        choices=[
                            ("low", "Low"),
                            ("medium", "Medium"),
                            ("high", "High"),
                            ("urgent", "Urgent"),
                            ("critical", "Critical"),
                        ],
                        default="medium",
                        max_length=20,
                    ),
                ),
                ("channel", models.CharField(default="web", max_length=50)),
                (
                    "reference",
                    models.CharField(editable=False, max_length=20, unique=True),
                ),
                (
                    "first_response_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "first_response_due_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "resolution_due_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "sla_first_response_breached",
                    models.BooleanField(default=False),
                ),
                (
                    "sla_resolution_breached",
                    models.BooleanField(default=False),
                ),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escalated_assigned_tickets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "department",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tickets",
                        to="escalated.department",
                    ),
                ),
                (
                    "requester_content_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="escalated_requester_tickets",
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "sla_policy",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tickets",
                        to="escalated.slapolicy",
                    ),
                ),
                (
                    "tags",
                    models.ManyToManyField(
                        blank=True, related_name="tickets", to="escalated.tag"
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("tickets"),
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="ticket",
            index=models.Index(
                fields=["status"], name="escalated_t_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="ticket",
            index=models.Index(
                fields=["priority"], name="escalated_t_priority_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="ticket",
            index=models.Index(
                fields=["reference"], name="escalated_t_reference_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="ticket",
            index=models.Index(
                fields=["assigned_to"], name="escalated_t_assigned_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="ticket",
            index=models.Index(
                fields=["created_at"], name="escalated_t_created_idx"
            ),
        ),
        # Reply
        migrations.CreateModel(
            name="Reply",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("body", models.TextField()),
                ("is_internal_note", models.BooleanField(default=False)),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("reply", "Reply"),
                            ("note", "Internal Note"),
                            ("system", "System"),
                        ],
                        default="reply",
                        max_length=20,
                    ),
                ),
                ("metadata", models.JSONField(blank=True, null=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escalated_replies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="replies",
                        to="escalated.ticket",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("replies"),
                "ordering": ["created_at"],
            },
        ),
        # Attachment
        migrations.CreateModel(
            name="Attachment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("object_id", models.PositiveIntegerField()),
                (
                    "file",
                    models.FileField(upload_to="escalated/attachments/%Y/%m/"),
                ),
                ("original_filename", models.CharField(max_length=500)),
                (
                    "mime_type",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "size",
                    models.PositiveIntegerField(
                        default=0, help_text="File size in bytes"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="escalated_attachments",
                        to="contenttypes.contenttype",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("attachments"),
                "ordering": ["-created_at"],
            },
        ),
        # EscalationRule
        migrations.CreateModel(
            name="EscalationRule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "trigger_type",
                    models.CharField(
                        choices=[
                            ("sla_breach", "SLA Breach"),
                            ("priority_change", "Priority Change"),
                            ("no_response", "No Response"),
                            ("customer_reply", "Customer Reply"),
                            ("time_based", "Time Based"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "conditions",
                    models.JSONField(
                        default=dict,
                        help_text="JSON conditions that must be met for the rule to fire",
                    ),
                ),
                (
                    "actions",
                    models.JSONField(
                        default=dict,
                        help_text="JSON actions to take when the rule fires (e.g., assign, notify, change priority)",
                    ),
                ),
                ("order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("escalation_rules"),
                "ordering": ["order", "name"],
            },
        ),
        # CannedResponse
        migrations.CreateModel(
            name="CannedResponse",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("body", models.TextField()),
                ("category", models.CharField(blank=True, default="", max_length=100)),
                ("is_shared", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escalated_canned_responses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("canned_responses"),
                "ordering": ["category", "title"],
            },
        ),
        # TicketActivity
        migrations.CreateModel(
            name="TicketActivity",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "causer_object_id",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("status_changed", "Status Changed"),
                            ("priority_changed", "Priority Changed"),
                            ("assigned", "Assigned"),
                            ("unassigned", "Unassigned"),
                            ("reply_added", "Reply Added"),
                            ("note_added", "Note Added"),
                            ("tag_added", "Tag Added"),
                            ("tag_removed", "Tag Removed"),
                            ("department_changed", "Department Changed"),
                            ("escalated", "Escalated"),
                            ("sla_breached", "SLA Breached"),
                            ("attachment_added", "Attachment Added"),
                            ("merged", "Merged"),
                        ],
                        max_length=30,
                    ),
                ),
                ("properties", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "causer_content_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escalated_activities",
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activities",
                        to="escalated.ticket",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("activities"),
                "ordering": ["-created_at"],
                "verbose_name_plural": "Ticket activities",
            },
        ),
    ]
