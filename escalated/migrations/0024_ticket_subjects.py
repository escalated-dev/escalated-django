import django.db.models.deletion
from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("escalated", "0023_host_user_id_string_keys"),
    ]

    operations = [
        migrations.CreateModel(
            name="TicketSubject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("object_id", models.CharField(max_length=255)),
                ("role", models.CharField(blank=True, max_length=255, null=True)),
                ("position", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "content_type",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="contenttypes.contenttype"),
                ),
                (
                    "ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subjects",
                        to="escalated.ticket",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("ticket_subjects"),
                "ordering": ["position", "id"],
                "indexes": [
                    models.Index(fields=["content_type", "object_id"], name="escalated_ts_ct_obj_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("ticket", "content_type", "object_id"),
                        name="escalated_ticket_subject_unique",
                    ),
                ],
            },
        ),
    ]
