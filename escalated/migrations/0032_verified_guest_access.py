# Verified guest access: email codes and expiring hashed grants.

from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0031_widget_chat_defaults_and_activity_encoder"),
    ]

    operations = [
        migrations.CreateModel(
            name="GuestVerification",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("email_digest", models.CharField(max_length=64)),
                ("purpose", models.CharField(max_length=16)),
                ("code_hash", models.CharField(max_length=64)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": get_table_name("guest_verifications"),
            },
        ),
        migrations.AddField(
            model_name="ticket",
            name="guest_access_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="guest_access_hash",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="guest_email_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="guest_verified_email",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AlterField(
            model_name="ticket",
            name="guest_token",
            field=models.CharField(
                blank=True,
                help_text="Legacy permanent guest link token; new tickets use expiring grants",
                max_length=64,
                null=True,
                unique=True,
            ),
        ),
    ]
