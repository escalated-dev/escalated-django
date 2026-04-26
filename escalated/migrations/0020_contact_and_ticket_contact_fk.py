"""Adds the Contact model + nullable ticket.contact FK (Pattern B convergence).

Mirrors the design shipped in escalated-nestjs PR #17 and companion PRs
for Laravel and Rails. Inline guest_name / guest_email / guest_token
columns on Ticket remain for backwards compatibility; a follow-up
migration backfills contact_id from guest_email.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0019_workflow_log_computed_columns"),
    ]

    operations = [
        migrations.CreateModel(
            name="Contact",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("email", models.EmailField(max_length=320, unique=True)),
                ("name", models.CharField(blank=True, max_length=255, null=True)),
                (
                    "user_id",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Linked host-app user id once the contact creates an account",
                        null=True,
                    ),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "escalated_contacts",
            },
        ),
        migrations.AddIndex(
            model_name="contact",
            index=models.Index(fields=["user_id"], name="escalated_c_user_id_idx"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="contact",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="tickets",
                to="escalated.contact",
            ),
        ),
    ]
