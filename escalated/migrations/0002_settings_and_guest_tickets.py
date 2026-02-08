from django.db import migrations, models

from escalated.conf import get_table_name


def seed_default_settings(apps, schema_editor):
    """Seed default settings values."""
    EscalatedSetting = apps.get_model("escalated", "EscalatedSetting")
    defaults = [
        ("guest_tickets_enabled", "1"),
        ("allow_customer_close", "1"),
        ("auto_close_resolved_after_days", "7"),
        ("max_attachments_per_reply", "5"),
        ("max_attachment_size_kb", "10240"),
    ]
    for key, value in defaults:
        EscalatedSetting.objects.get_or_create(key=key, defaults={"value": value})


class Migration(migrations.Migration):

    dependencies = [
        ("escalated", "0001_initial"),
    ]

    operations = [
        # Create EscalatedSetting model
        migrations.CreateModel(
            name="EscalatedSetting",
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
                ("key", models.CharField(max_length=255, unique=True)),
                ("value", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("settings"),
            },
        ),
        # Seed default settings
        migrations.RunPython(seed_default_settings, migrations.RunPython.noop),
        # Add guest ticket fields to Ticket model
        migrations.AddField(
            model_name="ticket",
            name="guest_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="guest_email",
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="guest_token",
            field=models.CharField(
                blank=True,
                help_text="Unique token for guest ticket access",
                max_length=64,
                null=True,
                unique=True,
            ),
        ),
    ]
