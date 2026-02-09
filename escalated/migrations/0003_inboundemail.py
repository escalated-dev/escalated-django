import django.db.models.deletion
from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):

    dependencies = [
        ("escalated", "0002_settings_and_guest_tickets"),
    ]

    operations = [
        migrations.CreateModel(
            name="InboundEmail",
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
                    "message_id",
                    models.CharField(
                        blank=True, max_length=500, null=True, unique=True
                    ),
                ),
                ("from_email", models.CharField(max_length=500)),
                (
                    "from_name",
                    models.CharField(blank=True, max_length=500, null=True),
                ),
                ("to_email", models.CharField(max_length=500)),
                ("subject", models.CharField(max_length=1000)),
                ("body_text", models.TextField(blank=True, null=True)),
                ("body_html", models.TextField(blank=True, null=True)),
                ("raw_headers", models.TextField(blank=True, null=True)),
                (
                    "ticket",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="inbound_emails",
                        to="escalated.ticket",
                    ),
                ),
                (
                    "reply",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="inbound_emails",
                        to="escalated.reply",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processed", "Processed"),
                            ("failed", "Failed"),
                            ("spam", "Spam"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("adapter", models.CharField(max_length=50)),
                ("error_message", models.TextField(blank=True, null=True)),
                (
                    "processed_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("inbound_emails"),
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="inboundemail",
            index=models.Index(
                fields=["status"], name="escalated_ie_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="inboundemail",
            index=models.Index(
                fields=["from_email"], name="escalated_ie_from_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="inboundemail",
            index=models.Index(
                fields=["message_id"], name="escalated_ie_msgid_idx"
            ),
        ),
    ]
