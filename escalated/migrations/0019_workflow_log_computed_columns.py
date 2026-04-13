from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("escalated", "0018_merge_mentions_workflows"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowlog",
            name="conditions_matched",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="workflowlog",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workflowlog",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
