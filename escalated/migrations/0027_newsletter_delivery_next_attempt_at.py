from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0026_newsletter_uuid_user_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="newsletterdelivery",
            name="next_attempt_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
