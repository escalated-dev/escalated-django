from datetime import timedelta

import django.core.serializers.json
from django.db import migrations, models
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

# Existing installs had the widget and its live chat on by default. The
# default is now off (as in the other hosts), so an install that already
# existed before this migration keeps them on unless an admin chose otherwise.
# A fresh install, migrated from scratch in one go, starts with both off.
_KEPT_ON = ("widget_enabled", "chat_enabled")
_FRESH_INSTALL_WINDOW = timedelta(hours=1)


def _is_existing_install(apps, schema_editor):
    alias = schema_editor.connection.alias
    for model in ("Ticket", "Department", "Article", "ChatSession"):
        if apps.get_model("escalated", model).objects.using(alias).exists():
            return True
    initial = (
        MigrationRecorder(schema_editor.connection)
        .migration_qs.filter(app="escalated", name="0001_initial")
        .values_list("applied", flat=True)
        .first()
    )
    return initial is not None and initial < timezone.now() - _FRESH_INSTALL_WINDOW


def keep_widget_on_for_existing_installs(apps, schema_editor):
    if not _is_existing_install(apps, schema_editor):
        return
    EscalatedSetting = apps.get_model("escalated", "EscalatedSetting")
    alias = schema_editor.connection.alias
    for key in _KEPT_ON:
        EscalatedSetting.objects.using(alias).get_or_create(key=key, defaults={"value": "1"})


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0030_ticket_accounts_and_sla_targets"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ticketactivity",
            name="properties",
            field=models.JSONField(default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder),
        ),
        migrations.RunPython(keep_widget_on_for_existing_installs, migrations.RunPython.noop),
    ]
