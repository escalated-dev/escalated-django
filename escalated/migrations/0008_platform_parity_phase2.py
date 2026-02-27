import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from escalated.conf import get_table_name


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("escalated", "0007_platform_parity_phase1"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        # CustomField
        migrations.CreateModel(
            name="CustomField",
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
                ("slug", models.SlugField(max_length=255, unique=True)),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("text", "Text"),
                            ("textarea", "Textarea"),
                            ("select", "Select"),
                            ("multi_select", "Multi Select"),
                            ("checkbox", "Checkbox"),
                            ("date", "Date"),
                            ("number", "Number"),
                        ],
                        max_length=50,
                    ),
                ),
                (
                    "context",
                    models.CharField(
                        choices=[
                            ("ticket", "Ticket"),
                            ("user", "User"),
                            ("organization", "Organization"),
                        ],
                        default="ticket",
                        max_length=50,
                    ),
                ),
                ("options", models.JSONField(blank=True, null=True)),
                ("required", models.BooleanField(default=False)),
                (
                    "placeholder",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                ("description", models.TextField(blank=True, default="")),
                ("validation_rules", models.JSONField(blank=True, null=True)),
                ("conditions", models.JSONField(blank=True, null=True)),
                ("position", models.IntegerField(default=0)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": get_table_name("custom_fields"),
                "ordering": ["position"],
            },
        ),
        # CustomFieldValue
        migrations.CreateModel(
            name="CustomFieldValue",
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
                ("entity_object_id", models.PositiveIntegerField()),
                ("value", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "custom_field",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="values",
                        to="escalated.customfield",
                    ),
                ),
                (
                    "entity_content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="contenttypes.contenttype",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("custom_field_values"),
            },
        ),
        # TicketLink
        migrations.CreateModel(
            name="TicketLink",
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
                    "link_type",
                    models.CharField(
                        choices=[
                            ("problem_incident", "Problem / Incident"),
                            ("parent_child", "Parent / Child"),
                            ("related", "Related"),
                        ],
                        max_length=50,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "parent_ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="links_as_parent",
                        to="escalated.ticket",
                    ),
                ),
                (
                    "child_ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="links_as_child",
                        to="escalated.ticket",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("ticket_links"),
                "unique_together": {("parent_ticket", "child_ticket", "link_type")},
            },
        ),
        # SideConversation
        migrations.CreateModel(
            name="SideConversation",
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
                ("subject", models.CharField(max_length=255)),
                (
                    "channel",
                    models.CharField(
                        choices=[
                            ("internal", "Internal"),
                            ("email", "Email"),
                        ],
                        default="internal",
                        max_length=50,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("closed", "Closed"),
                        ],
                        default="open",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="side_conversations",
                        to="escalated.ticket",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escalated_side_conversations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("side_conversations"),
            },
        ),
        # SideConversationReply
        migrations.CreateModel(
            name="SideConversationReply",
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
                ("body", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "side_conversation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="replies",
                        to="escalated.sideconversation",
                    ),
                ),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escalated_side_conversation_replies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("side_conversation_replies"),
            },
        ),
        # ArticleCategory
        migrations.CreateModel(
            name="ArticleCategory",
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
                ("slug", models.SlugField(max_length=255, unique=True)),
                ("position", models.IntegerField(default=0)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="children",
                        to="escalated.articlecategory",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("article_categories"),
                "verbose_name_plural": "Article categories",
            },
        ),
        # Article
        migrations.CreateModel(
            name="Article",
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
                ("title", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=255, unique=True)),
                ("body", models.TextField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("published", "Published"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("view_count", models.PositiveIntegerField(default=0)),
                ("helpful_count", models.PositiveIntegerField(default=0)),
                ("not_helpful_count", models.PositiveIntegerField(default=0)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="articles",
                        to="escalated.articlecategory",
                    ),
                ),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escalated_articles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("articles"),
                "ordering": ["-created_at"],
            },
        ),
        # Add type and merged_into to Ticket
        migrations.AddField(
            model_name="ticket",
            name="type",
            field=models.CharField(
                choices=[
                    ("question", "Question"),
                    ("problem", "Problem"),
                    ("incident", "Incident"),
                    ("task", "Task"),
                ],
                default="question",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="ticket",
            name="merged_into",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="merged_tickets",
                to="escalated.ticket",
            ),
        ),
    ]
