"""
Bring the migration state in line with the models.

Until the models module imported workflow_models, mention_models,
plugin_models and bridge.plugin_store_record, makemigrations could not see
several models and nobody noticed the rest of the drift. This migration is
what is left once those models are registered. It is deliberately
conservative.

Three real schema changes, none touching table data:

* The index on tickets.ticket_type. The model has always declared it, but no
  migration ever created it. It is additive.

* escalated_automation_active_idx is renamed to escalated_auto_active_idx.
  Migration 0009 gave it a 31-character name, and Django's system checks
  reject an index name longer than 30 characters on a model (models.E034), so
  the model cannot declare the original. PostgreSQL and MySQL rename an index
  without rebuilding it; SQLite drops and recreates it.

* mentions.user_id loses its database foreign key to the host user table, as
  every other such key did in 0028. Mention was not registered when 0028 was
  written, so it was missed. on_delete=CASCADE still applies: Django's
  deletion collector implements it, not the database.

Everything else is state only (SeparateDatabaseAndState with no database
operations), because the database already matches:

* contacts, newsletter_lists, newsletter_list_members, newsletter_templates and
  newsletters were created with 32-bit AutoField ids. The app's
  default_auto_field is BigAutoField, so their models claimed bigint ids.
  Changing an existing primary key's type rewrites the table and every column
  that references it (tickets.contact_id among them), so the models now
  declare AutoField instead.
* newsletter_deliveries.id was already a BigAutoField; the model declares it
  explicitly, which differs from the implicit field in state only.
* import_jobs.credentials was created as a TextField. EncryptedJSONField is a
  TextField subclass with the same column type.
* The choices on newsletters.status, newsletter_deliveries.status,
  newsletter_lists.kind and workflows.trigger_event changed without a
  migration. Choices never reach the database.

The agentskill proficiency check constraint and the other fourteen index names
created by earlier migrations are unchanged: the models now declare them under
the names those migrations used, instead of expecting Django's generated
names.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import escalated.models


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0028_drop_host_user_fk_constraints"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddIndex(
            model_name="ticket",
            index=models.Index(fields=["ticket_type"], name="escalated_t_type_idx"),
        ),
        migrations.RenameIndex(
            model_name="automation",
            new_name="escalated_auto_active_idx",
            old_name="escalated_automation_active_idx",
        ),
        migrations.AlterField(
            model_name="mention",
            name="user",
            field=models.ForeignKey(
                db_constraint=False,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="escalated_mentions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="contact",
                    name="id",
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name="newsletterlist",
                    name="id",
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name="newsletterlistmember",
                    name="id",
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name="newslettertemplate",
                    name="id",
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name="newsletter",
                    name="id",
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name="newsletterdelivery",
                    name="id",
                    field=models.BigAutoField(primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name="importjob",
                    name="credentials",
                    field=escalated.models.EncryptedJSONField(blank=True, null=True),
                ),
                migrations.AlterField(
                    model_name="newsletter",
                    name="status",
                    field=models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("scheduled", "Scheduled"),
                            ("sending", "Sending"),
                            ("sent", "Sent"),
                            ("paused", "Paused"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=16,
                    ),
                ),
                migrations.AlterField(
                    model_name="newsletterdelivery",
                    name="status",
                    field=models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("queued", "Queued"),
                            ("sent", "Sent"),
                            ("bounced", "Bounced"),
                            ("complained", "Complained"),
                            ("suppressed", "Suppressed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                migrations.AlterField(
                    model_name="newsletterlist",
                    name="kind",
                    field=models.CharField(
                        choices=[("static", "Static"), ("dynamic", "Dynamic")],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                migrations.AlterField(
                    model_name="workflow",
                    name="trigger_event",
                    field=models.CharField(
                        choices=[
                            ("ticket.created", "Ticket Created"),
                            ("ticket.updated", "Ticket Updated"),
                            ("ticket.status_changed", "Status Changed"),
                            ("ticket.assigned", "Ticket Assigned"),
                            ("ticket.priority_changed", "Priority Changed"),
                            ("ticket.escalated", "Ticket Escalated"),
                            ("reply.created", "Reply Created"),
                            ("sla.warning", "SLA Warning"),
                            ("sla.breached", "SLA Breached"),
                        ],
                        max_length=100,
                    ),
                ),
            ],
        ),
    ]
