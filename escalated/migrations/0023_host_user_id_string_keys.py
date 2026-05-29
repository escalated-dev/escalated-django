from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0022_skills_management_routing"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contact",
            name="user_id",
            field=models.CharField(
                blank=True,
                help_text="Linked host-app user id once the contact creates an account",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="ticket",
            name="requester_object_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="ticketactivity",
            name="causer_object_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="satisfactionrating",
            name="rated_by_object_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="apitoken",
            name="tokenable_object_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
