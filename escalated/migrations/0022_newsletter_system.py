"""Adds the newsletter system tables + marketing_opt_out_at column on contacts.

Mirrors the design shipped in escalated-laravel PR #103 and companion
PRs for the other backends. The Newsletter feature is opt-in via
`ESCALATED["enable_newsletters"]` in Django settings; tables exist
regardless so re-enabling is a no-op migration.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0021_backfill_contact_id_on_tickets"),
    ]

    operations = [
        migrations.AddField(
            model_name="contact",
            name="marketing_opt_out_at",
            field=models.DateTimeField(blank=True, null=True, db_index=True),
        ),
        migrations.CreateModel(
            name="NewsletterList",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, null=True)),
                ("kind", models.CharField(max_length=16, db_index=True)),
                ("filter_json", models.JSONField(blank=True, null=True)),
                ("created_by", models.PositiveIntegerField(blank=True, null=True, db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "escalated_newsletter_lists"},
        ),
        migrations.CreateModel(
            name="NewsletterListMember",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("list_id", models.PositiveIntegerField()),
                ("contact_id", models.PositiveIntegerField(db_index=True)),
                ("added_at", models.DateTimeField(auto_now_add=True)),
                ("added_by", models.PositiveIntegerField(blank=True, null=True)),
            ],
            options={
                "db_table": "escalated_newsletter_list_members",
                "unique_together": {("list_id", "contact_id")},
            },
        ),
        migrations.CreateModel(
            name="NewsletterTemplate",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("theme", models.CharField(max_length=64, default="default", db_index=True)),
                ("subject_template", models.CharField(max_length=998, blank=True, null=True)),
                ("body_markdown", models.TextField()),
                ("merge_fields_schema", models.JSONField(blank=True, null=True)),
                ("created_by", models.PositiveIntegerField(blank=True, null=True, db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "escalated_newsletter_templates"},
        ),
        migrations.CreateModel(
            name="Newsletter",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("subject", models.CharField(max_length=998)),
                ("from_email", models.CharField(max_length=320)),
                ("from_name", models.CharField(max_length=255, blank=True, null=True)),
                ("reply_to", models.CharField(max_length=320, blank=True, null=True)),
                ("target_list_id", models.PositiveIntegerField()),
                ("template_id", models.PositiveIntegerField(blank=True, null=True)),
                ("theme", models.CharField(max_length=64, blank=True, null=True)),
                ("body_markdown", models.TextField(blank=True, null=True)),
                ("status", models.CharField(max_length=16, default="draft", db_index=True)),
                ("scheduled_at", models.DateTimeField(blank=True, null=True, db_index=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.PositiveIntegerField(blank=True, null=True, db_index=True)),
                ("sent_by", models.PositiveIntegerField(blank=True, null=True)),
                ("summary_total", models.PositiveIntegerField(default=0)),
                ("summary_sent", models.PositiveIntegerField(default=0)),
                ("summary_opened", models.PositiveIntegerField(default=0)),
                ("summary_clicked", models.PositiveIntegerField(default=0)),
                ("summary_bounced", models.PositiveIntegerField(default=0)),
                ("summary_complained", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "escalated_newsletters",
                "indexes": [
                    models.Index(fields=["status", "scheduled_at"], name="esc_nl_status_sched_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="NewsletterDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("newsletter_id", models.PositiveIntegerField()),
                ("contact_id", models.PositiveIntegerField(db_index=True)),
                ("email_at_send", models.CharField(max_length=320)),
                ("status", models.CharField(max_length=16, default="pending")),
                ("tracking_token", models.CharField(max_length=40, unique=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("opened_at", models.DateTimeField(blank=True, null=True)),
                ("last_clicked_at", models.DateTimeField(blank=True, null=True)),
                ("clicks_count", models.PositiveIntegerField(default=0)),
                ("bounce_reason", models.TextField(blank=True, null=True)),
                ("failure_reason", models.TextField(blank=True, null=True)),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("is_test", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "escalated_newsletter_deliveries",
                "indexes": [
                    models.Index(fields=["newsletter_id", "status"], name="esc_nl_d_nl_status_idx"),
                    models.Index(fields=["status", "claimed_at"], name="esc_nl_d_status_cl_idx"),
                ],
            },
        ),
    ]
