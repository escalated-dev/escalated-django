from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("escalated", "0011_plugin_bridge_store"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="ticket_type",
            field=models.CharField(
                max_length=50,
                choices=[
                    ("question", "Question"),
                    ("problem", "Problem"),
                    ("incident", "Incident"),
                    ("task", "Task"),
                ],
                default="question",
                db_index=True,
            ),
        ),
    ]
