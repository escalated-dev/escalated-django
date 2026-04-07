"""
Migration 0011: Plugin Bridge Store

Adds the ``escalated_plugin_store`` table used by the SDK plugin bridge to
persist per-plugin key/value data (ctx.store.* and ctx.config.*).
"""

from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0010_import_framework"),
    ]

    operations = [
        migrations.CreateModel(
            name="PluginStoreRecord",
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
                ("plugin", models.CharField(db_index=True, max_length=255)),
                ("collection", models.CharField(db_index=True, max_length=255)),
                (
                    "key",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    "data",
                    models.JSONField(blank=True, default=None, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Plugin Store Record",
                "verbose_name_plural": "Plugin Store Records",
                "db_table": get_table_name("plugin_store"),
                "ordering": ["id"],
            },
        ),
        migrations.AddIndex(
            model_name="pluginstorerecord",
            index=models.Index(
                fields=["plugin", "collection", "key"],
                name="idx_plugin_store_lookup",
            ),
        ),
    ]
