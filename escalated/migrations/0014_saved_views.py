"""
Add SavedView model for custom ticket queues / saved filters.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("escalated", "0013_plugin_metadata_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="SavedView",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("filters", models.JSONField(default=dict)),
                (
                    "user",
                    models.ForeignKey(
                        to=settings.AUTH_USER_MODEL,
                        on_delete=django.db.models.deletion.CASCADE,
                        null=True,
                        blank=True,
                        related_name="escalated_saved_views",
                    ),
                ),
                ("is_shared", models.BooleanField(default=False)),
                ("is_default", models.BooleanField(default=False)),
                ("position", models.IntegerField(default=0)),
                ("icon", models.CharField(max_length=100, blank=True, default="")),
                ("color", models.CharField(max_length=20, blank=True, default="#6b7280")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("saved_views"),
                "ordering": ["position", "name"],
            },
        ),
    ]
