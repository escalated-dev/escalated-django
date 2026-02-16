import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contenttypes", "0002_remove_content_type_name"),
        ("escalated", "0004_v040_advanced_features"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApiToken",
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
                    "tokenable_content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        null=True,
                        blank=True,
                        related_name="escalated_api_tokens",
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "tokenable_object_id",
                    models.PositiveIntegerField(null=True, blank=True),
                ),
                ("name", models.CharField(max_length=255)),
                (
                    "token",
                    models.CharField(max_length=64, unique=True, db_index=True),
                ),
                (
                    "abilities",
                    models.JSONField(default=list),
                ),
                (
                    "last_used_at",
                    models.DateTimeField(null=True, blank=True),
                ),
                (
                    "last_used_ip",
                    models.CharField(max_length=45, null=True, blank=True),
                ),
                (
                    "expires_at",
                    models.DateTimeField(null=True, blank=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("api_tokens"),
                "ordering": ["-created_at"],
            },
        ),
    ]
