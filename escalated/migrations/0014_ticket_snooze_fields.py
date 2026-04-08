"""
Add snooze fields to the Ticket model: snoozed_until, snoozed_by, status_before_snooze.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("escalated", "0013_plugin_metadata_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="snoozed_until",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="snoozed_by",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name="escalated_snoozed_tickets",
            ),
        ),
        migrations.AddField(
            model_name="ticket",
            name="status_before_snooze",
            field=models.CharField(max_length=30, null=True, blank=True),
        ),
    ]
