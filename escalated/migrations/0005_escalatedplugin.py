"""
Migration to create the EscalatedPlugin table for the plugin system.
"""

from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):

    dependencies = [
        ("escalated", "0004_v040_advanced_features"),
    ]

    operations = [
        migrations.CreateModel(
            name="EscalatedPlugin",
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
                    "slug",
                    models.SlugField(
                        max_length=255,
                        unique=True,
                        help_text="Unique identifier matching the plugin directory name.",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this plugin is currently active.",
                    ),
                ),
                (
                    "activated_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "deactivated_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
            ],
            options={
                "db_table": get_table_name("plugins"),
                "ordering": ["slug"],
                "verbose_name": "Plugin",
                "verbose_name_plural": "Plugins",
            },
        ),
    ]
