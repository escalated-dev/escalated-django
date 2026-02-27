import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("escalated", "0008_platform_parity_phase2"),
    ]

    operations = [
        # AgentProfile
        migrations.CreateModel(
            name="AgentProfile",
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
                ("agent_type", models.CharField(default="full", max_length=20)),
                ("max_tickets", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="escalated_agent_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("agent_profiles"),
            },
        ),
        # Skill
        migrations.CreateModel(
            name="Skill",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("skills"),
            },
        ),
        # AgentSkill (through model)
        migrations.CreateModel(
            name="AgentSkill",
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
                ("proficiency", models.PositiveIntegerField(default=1)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "skill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_skills",
                        to="escalated.skill",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("agent_skill"),
                "unique_together": {("user", "skill")},
            },
        ),
        # Add M2M agents field to Skill via AgentSkill through model
        migrations.AddField(
            model_name="skill",
            name="agents",
            field=models.ManyToManyField(
                blank=True,
                related_name="escalated_skills",
                through="escalated.AgentSkill",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # AgentCapacity
        migrations.CreateModel(
            name="AgentCapacity",
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
                ("channel", models.CharField(default="default", max_length=50)),
                ("max_concurrent", models.PositiveIntegerField(default=10)),
                ("current_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="escalated_agent_capacities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("agent_capacity"),
                "unique_together": {("user", "channel")},
            },
        ),
        # Webhook
        migrations.CreateModel(
            name="Webhook",
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
                ("url", models.URLField(max_length=500)),
                ("events", models.JSONField(default=list)),
                ("secret", models.CharField(blank=True, max_length=255, null=True)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("webhooks"),
            },
        ),
        # WebhookDelivery
        migrations.CreateModel(
            name="WebhookDelivery",
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
                ("event", models.CharField(max_length=100)),
                ("payload", models.JSONField(blank=True, null=True)),
                (
                    "response_code",
                    models.PositiveSmallIntegerField(blank=True, null=True),
                ),
                ("response_body", models.TextField(blank=True, null=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "webhook",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="escalated.webhook",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("webhook_deliveries"),
            },
        ),
        # Automation
        migrations.CreateModel(
            name="Automation",
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
                ("conditions", models.JSONField(default=list)),
                ("actions", models.JSONField(default=list)),
                ("active", models.BooleanField(default=True)),
                ("position", models.PositiveIntegerField(default=0)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("automations"),
            },
        ),
        migrations.AddIndex(
            model_name="automation",
            index=models.Index(
                fields=["active"],
                name="escalated_automation_active_idx",
            ),
        ),
        # TwoFactor
        migrations.CreateModel(
            name="TwoFactor",
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
                ("secret", models.TextField()),
                ("recovery_codes", models.JSONField(blank=True, null=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="escalated_two_factor",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("two_factor"),
            },
        ),
        # CustomObject
        migrations.CreateModel(
            name="CustomObject",
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
                ("fields_schema", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("custom_objects"),
            },
        ),
        # CustomObjectRecord
        migrations.CreateModel(
            name="CustomObjectRecord",
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
                ("data", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "object",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="records",
                        to="escalated.customobject",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("custom_object_records"),
            },
        ),
    ]
