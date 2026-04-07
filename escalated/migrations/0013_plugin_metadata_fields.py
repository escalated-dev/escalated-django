"""
Add metadata and config fields to the EscalatedPlugin model.

These fields cache manifest information (name, version, description, author)
in the database and add a JSON config blob for per-plugin settings.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0012_ticket_type_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="escalatedplugin",
            name="name",
            field=models.CharField(
                max_length=255,
                blank=True,
                default="",
                help_text="Human-readable plugin name (cached from plugin.json).",
            ),
        ),
        migrations.AddField(
            model_name="escalatedplugin",
            name="version",
            field=models.CharField(
                max_length=50,
                blank=True,
                default="",
                help_text="Plugin version string (cached from plugin.json).",
            ),
        ),
        migrations.AddField(
            model_name="escalatedplugin",
            name="description",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Short plugin description (cached from plugin.json).",
            ),
        ),
        migrations.AddField(
            model_name="escalatedplugin",
            name="author",
            field=models.CharField(
                max_length=255,
                blank=True,
                default="",
                help_text="Plugin author (cached from plugin.json).",
            ),
        ),
        migrations.AddField(
            model_name="escalatedplugin",
            name="config",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Per-plugin configuration stored as JSON.",
            ),
        ),
        migrations.AddField(
            model_name="escalatedplugin",
            name="installed_at",
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text="When this plugin was first installed.",
            ),
        ),
    ]
