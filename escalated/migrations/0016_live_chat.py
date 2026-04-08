import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("escalated", "0015_merge_0014_saved_views_0014_ticket_snooze_fields"),
    ]

    operations = [
        # ------------------------------------------------------------------
        # Extend Ticket: channel already exists as CharField; add chat fields
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="ticket",
            name="chat_ended_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="chat_metadata",
            field=models.JSONField(null=True, blank=True),
        ),
        # ------------------------------------------------------------------
        # Add chat_status to AgentProfile
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="agentprofile",
            name="chat_status",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("online", "Online"),
                    ("away", "Away"),
                    ("offline", "Offline"),
                ],
                default="offline",
            ),
        ),
        # ------------------------------------------------------------------
        # ChatSession
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="ChatSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_sessions",
                        to="escalated.ticket",
                    ),
                ),
                ("customer_session_id", models.CharField(max_length=255, db_index=True)),
                (
                    "agent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.SET_NULL,
                        null=True,
                        blank=True,
                        related_name="escalated_chat_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        max_length=20,
                        choices=[
                            ("waiting", "Waiting"),
                            ("active", "Active"),
                            ("ended", "Ended"),
                            ("abandoned", "Abandoned"),
                        ],
                        default="waiting",
                        db_index=True,
                    ),
                ),
                ("customer_typing_at", models.DateTimeField(null=True, blank=True)),
                ("agent_typing_at", models.DateTimeField(null=True, blank=True)),
                ("metadata", models.JSONField(null=True, blank=True)),
                ("rating", models.PositiveSmallIntegerField(null=True, blank=True)),
                ("rating_comment", models.TextField(blank=True, default="")),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("ended_at", models.DateTimeField(null=True, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("chat_sessions"),
                "ordering": ["-created_at"],
            },
        ),
        # ------------------------------------------------------------------
        # ChatRoutingRule
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="ChatRoutingRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        null=True,
                        blank=True,
                        related_name="chat_routing_rules",
                        to="escalated.department",
                    ),
                ),
                (
                    "routing_strategy",
                    models.CharField(
                        max_length=30,
                        choices=[
                            ("round_robin", "Round Robin"),
                            ("least_active", "Least Active"),
                            ("random", "Random"),
                        ],
                        default="round_robin",
                    ),
                ),
                (
                    "offline_behavior",
                    models.CharField(
                        max_length=30,
                        choices=[
                            ("queue", "Queue"),
                            ("ticket", "Create Ticket"),
                            ("hide", "Hide Chat"),
                        ],
                        default="ticket",
                    ),
                ),
                ("max_concurrent_chats", models.PositiveIntegerField(default=5)),
                ("welcome_message", models.TextField(blank=True, default="")),
                ("offline_message", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("position", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("chat_routing_rules"),
                "ordering": ["position"],
            },
        ),
    ]
