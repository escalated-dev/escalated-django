import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contenttypes", "0002_remove_content_type_name"),
        ("escalated", "0003_inboundemail"),
    ]

    operations = [
        # ---------------------------------------------------------------
        # Macro model
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name="Macro",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                (
                    "description",
                    models.CharField(max_length=500, blank=True, default=""),
                ),
                (
                    "actions",
                    models.JSONField(
                        default=list,
                        help_text='JSON array of actions, e.g. [{"type": "set_status", "value": "open"}]',
                    ),
                ),
                ("is_shared", models.BooleanField(default=True)),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        blank=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escalated_macros",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("macros"),
                "ordering": ["order", "name"],
            },
        ),
        # ---------------------------------------------------------------
        # TicketFollower join table
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name="TicketFollower",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ticket_followers",
                        to="escalated.ticket",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="escalated_followed_tickets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("ticket_followers"),
            },
        ),
        migrations.AddConstraint(
            model_name="ticketfollower",
            constraint=models.UniqueConstraint(
                fields=["ticket", "user"],
                name="escalated_tf_ticket_user_uniq",
            ),
        ),
        # ---------------------------------------------------------------
        # SatisfactionRating model
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name="SatisfactionRating",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "ticket",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="satisfaction_rating",
                        to="escalated.ticket",
                    ),
                ),
                (
                    "rating",
                    models.PositiveSmallIntegerField(
                        help_text="Rating from 1 to 5",
                    ),
                ),
                (
                    "comment",
                    models.TextField(blank=True, null=True),
                ),
                # GenericFK for the user who rated (supports morph-like behavior)
                (
                    "rated_by_content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        null=True,
                        blank=True,
                        related_name="escalated_satisfaction_ratings",
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "rated_by_object_id",
                    models.PositiveIntegerField(null=True, blank=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": get_table_name("satisfaction_ratings"),
                "ordering": ["-created_at"],
            },
        ),
        # ---------------------------------------------------------------
        # Add is_pinned to Reply
        # ---------------------------------------------------------------
        migrations.AddField(
            model_name="reply",
            name="is_pinned",
            field=models.BooleanField(default=False),
        ),
        # ---------------------------------------------------------------
        # Add followers M2M shortcut on Ticket
        # ---------------------------------------------------------------
        migrations.AddField(
            model_name="ticket",
            name="followers",
            field=models.ManyToManyField(
                through="escalated.TicketFollower",
                related_name="escalated_following_tickets",
                to=settings.AUTH_USER_MODEL,
                blank=True,
            ),
        ),
    ]
