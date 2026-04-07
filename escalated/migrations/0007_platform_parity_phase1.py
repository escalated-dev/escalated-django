import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("escalated", "0006_merge_api_tokens_and_plugins"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        # AuditLog
        migrations.CreateModel(
            name="AuditLog",
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
                ("action", models.CharField(max_length=50)),
                ("auditable_object_id", models.PositiveIntegerField()),
                ("old_values", models.JSONField(blank=True, null=True)),
                ("new_values", models.JSONField(blank=True, null=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                (
                    "user_agent",
                    models.CharField(blank=True, max_length=500, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escalated_audit_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "auditable_content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="escalated_audit_logs",
                        to="contenttypes.contenttype",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("audit_logs"),
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["auditable_content_type", "auditable_object_id"],
                name="escalated_al_auditable_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["user"],
                name="escalated_al_user_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["action"],
                name="escalated_al_action_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["created_at"],
                name="escalated_al_created_idx",
            ),
        ),
        # TicketStatus
        migrations.CreateModel(
            name="TicketStatus",
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
                ("label", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=255, unique=True)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("open", "Open"),
                            ("pending", "Pending"),
                            ("on_hold", "On Hold"),
                            ("solved", "Solved"),
                        ],
                        max_length=20,
                    ),
                ),
                ("color", models.CharField(default="#6b7280", max_length=20)),
                ("description", models.TextField(blank=True, default="")),
                ("position", models.IntegerField(default=0)),
                ("is_default", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("ticket_statuses"),
                "ordering": ["category", "position"],
            },
        ),
        # BusinessSchedule
        migrations.CreateModel(
            name="BusinessSchedule",
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
                ("timezone", models.CharField(default="UTC", max_length=100)),
                ("is_default", models.BooleanField(default=False)),
                (
                    "schedule",
                    models.JSONField(
                        default=dict,
                        help_text='Day schedules, e.g. {"monday": {"start": "09:00", "end": "17:00"}}',
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("business_schedules"),
            },
        ),
        # Holiday
        migrations.CreateModel(
            name="Holiday",
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
                ("date", models.DateField()),
                ("recurring", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "schedule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="holidays",
                        to="escalated.businessschedule",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("holidays"),
            },
        ),
        # Permission
        migrations.CreateModel(
            name="Permission",
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
                ("group", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True, default="")),
            ],
            options={
                "db_table": get_table_name("permissions"),
                "ordering": ["group", "name"],
            },
        ),
        # Role
        migrations.CreateModel(
            name="Role",
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
                ("is_system", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "permissions",
                    models.ManyToManyField(
                        blank=True,
                        db_table=get_table_name("role_permission"),
                        related_name="roles",
                        to="escalated.permission",
                    ),
                ),
                (
                    "users",
                    models.ManyToManyField(
                        blank=True,
                        db_table=get_table_name("role_user"),
                        related_name="escalated_roles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("roles"),
            },
        ),
    ]
