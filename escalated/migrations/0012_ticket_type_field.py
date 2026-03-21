from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("escalated", "0011_plugin_bridge_store"),
    ]

    operations = [
        # Rename the 'type' column (added in 0008) to 'ticket_type'
        migrations.RenameField(
            model_name="ticket",
            old_name="type",
            new_name="ticket_type",
        ),
    ]
