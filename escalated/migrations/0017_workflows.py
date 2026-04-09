import django.db.models.deletion
from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0016_live_chat"),
    ]

    operations = [
        migrations.CreateModel(
            name="Workflow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("trigger_event", models.CharField(max_length=100)),
                ("conditions", models.JSONField(default=dict)),
                ("actions", models.JSONField(default=list)),
                ("is_active", models.BooleanField(default=True)),
                ("position", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": get_table_name("workflows"), "ordering": ["position", "name"]},
        ),
        migrations.CreateModel(
            name="WorkflowLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("trigger_event", models.CharField(max_length=100)),
                ("status", models.CharField(max_length=20, default="success")),
                ("actions_executed", models.JSONField(default=list)),
                ("error_message", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "workflow",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logs",
                        to="escalated.workflow",
                    ),
                ),
                (
                    "ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workflow_logs",
                        to="escalated.ticket",
                    ),
                ),
            ],
            options={"db_table": get_table_name("workflow_logs"), "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="DelayedAction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action_data", models.JSONField()),
                ("execute_at", models.DateTimeField()),
                ("executed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "workflow",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="delayed_actions",
                        to="escalated.workflow",
                    ),
                ),
                (
                    "ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="delayed_actions",
                        to="escalated.ticket",
                    ),
                ),
            ],
            options={"db_table": get_table_name("delayed_actions")},
        ),
    ]
