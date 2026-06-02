"""Make newsletter user-id columns UUID-safe.

created_by/added_by/sent_by were PositiveIntegerField (integer-only), which
breaks UUID/string-keyed hosts. Switch to CharField (matching Contact.user_id,
the package's host-user-id storage pattern). The fields are nullable and not
currently populated, so this is a safe in-place column type change.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0025_merge_newsletter_ticket_subjects"),
    ]

    operations = [
        migrations.AlterField(
            model_name="newsletter",
            name="created_by",
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="newsletter",
            name="sent_by",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="newsletterlist",
            name="created_by",
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="newsletterlistmember",
            name="added_by",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="newslettertemplate",
            name="created_by",
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
    ]
