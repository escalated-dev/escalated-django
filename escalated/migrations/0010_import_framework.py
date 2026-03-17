"""
Migration 0010: Import Framework

Adds the ``ImportJob`` and ``ImportSourceMap`` models used by the
platform-import pipeline.
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):

    dependencies = [
        ("escalated", "0009_platform_parity_phase3_5"),
    ]

    operations = [
        # ------------------------------------------------------------------
        # ImportJob
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="ImportJob",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True,
                        default=uuid.uuid4,
                        editable=False,
                        serialize=False,
                    ),
                ),
                ("platform", models.CharField(max_length=100)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("authenticating", "Authenticating"),
                            ("mapping", "Mapping"),
                            ("importing", "Importing"),
                            ("paused", "Paused"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                # EncryptedJSONField is a subclass of TextField
                ("credentials", models.TextField(blank=True, null=True)),
                ("field_mappings", models.JSONField(blank=True, default=dict)),
                ("progress", models.JSONField(blank=True, default=dict)),
                ("error_log", models.JSONField(blank=True, default=list)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("import_jobs"),
                "ordering": ["-created_at"],
            },
        ),
        # ------------------------------------------------------------------
        # ImportSourceMap
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="ImportSourceMap",
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
                    "import_job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="source_maps",
                        to="escalated.importjob",
                    ),
                ),
                ("entity_type", models.CharField(max_length=100)),
                ("source_id", models.CharField(max_length=255)),
                ("escalated_id", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": get_table_name("import_source_maps"),
            },
        ),
        # Unique constraint on (import_job, entity_type, source_id)
        migrations.AddConstraint(
            model_name="importsourcemap",
            constraint=models.UniqueConstraint(
                fields=["import_job", "entity_type", "source_id"],
                name="unique_import_source_map",
            ),
        ),
        # Lookup index
        migrations.AddIndex(
            model_name="importsourcemap",
            index=models.Index(
                fields=["import_job", "entity_type", "source_id"],
                name="idx_import_source_map_lookup",
            ),
        ),
    ]
