from datetime import timedelta

from django.db import migrations
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

# knowledge_base_public now defaults on (as in escalated-laravel). An install
# that already existed before this migration had a private knowledge base by
# default, so it keeps it private unless an admin had already stored a value.
# A fresh install, migrated from scratch in one go, gets the new default.
_FRESH_INSTALL_WINDOW = timedelta(hours=1)


def _is_existing_install(apps, schema_editor):
    # Settings rows are no signal: migration 0002 seeds them on every install.
    alias = schema_editor.connection.alias
    for model in ("Ticket", "Department", "Article", "ArticleCategory", "ChatSession"):
        if apps.get_model("escalated", model).objects.using(alias).exists():
            return True
    initial = (
        MigrationRecorder(schema_editor.connection)
        .migration_qs.filter(app="escalated", name="0001_initial")
        .values_list("applied", flat=True)
        .first()
    )
    return initial is not None and initial < timezone.now() - _FRESH_INSTALL_WINDOW


def keep_knowledge_base_private_for_existing_installs(apps, schema_editor):
    if not _is_existing_install(apps, schema_editor):
        return
    EscalatedSetting = apps.get_model("escalated", "EscalatedSetting")
    alias = schema_editor.connection.alias
    EscalatedSetting.objects.using(alias).get_or_create(key="knowledge_base_public", defaults={"value": "0"})


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0035_chat_token_expiry"),
    ]

    operations = [
        migrations.RunPython(keep_knowledge_base_private_for_existing_installs, migrations.RunPython.noop),
    ]
