import django
import django.db.models.deletion
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models

from escalated.conf import get_table_name

_check_kwargs = {"condition": models.Q(proficiency__gte=1, proficiency__lte=5)}
if django.VERSION < (5, 0):
    _check_kwargs = {"check": models.Q(proficiency__gte=1, proficiency__lte=5)}


def backfill_agent_skill_proficiency(apps, schema_editor):
    AgentSkill = apps.get_model("escalated", "AgentSkill")
    AgentSkill.objects.filter(proficiency__lt=1).update(proficiency=3)
    AgentSkill.objects.filter(proficiency__gt=5).update(proficiency=3)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("escalated", "0021_backfill_contact_id_on_tickets"),
    ]

    operations = [
        migrations.AddField(
            model_name="skill",
            name="description",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="SkillRoutingTag",
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
                    "skill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="skill_routing_tag_links",
                        to="escalated.skill",
                    ),
                ),
                (
                    "tag",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="skill_routing_tag_links",
                        to="escalated.tag",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("skill_routing_tags"),
            },
        ),
        migrations.CreateModel(
            name="SkillRoutingDepartment",
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
                    "skill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="skill_routing_department_links",
                        to="escalated.skill",
                    ),
                ),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="skill_routing_department_links",
                        to="escalated.department",
                    ),
                ),
            ],
            options={
                "db_table": get_table_name("skill_routing_departments"),
            },
        ),
        migrations.AddField(
            model_name="skill",
            name="routing_departments",
            field=models.ManyToManyField(
                blank=True,
                related_name="skill_routing_departments",
                through="escalated.SkillRoutingDepartment",
                to="escalated.department",
            ),
        ),
        migrations.AddField(
            model_name="skill",
            name="routing_tags",
            field=models.ManyToManyField(
                blank=True,
                related_name="skill_routing_tags",
                through="escalated.SkillRoutingTag",
                to="escalated.tag",
            ),
        ),
        migrations.AddConstraint(
            model_name="skillroutingdepartment",
            constraint=models.UniqueConstraint(
                fields=("skill", "department"),
                name="escalated_skill_routing_dept_skill_dept_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="skillroutingtag",
            constraint=models.UniqueConstraint(
                fields=("skill", "tag"),
                name="escalated_skill_routing_tag_skill_tag_uniq",
            ),
        ),
        migrations.AlterField(
            model_name="agentskill",
            name="proficiency",
            field=models.PositiveIntegerField(
                default=3,
                validators=[MinValueValidator(1), MaxValueValidator(5)],
            ),
        ),
        migrations.RunPython(backfill_agent_skill_proficiency, noop_reverse),
        migrations.AddConstraint(
            model_name="agentskill",
            constraint=models.CheckConstraint(
                **_check_kwargs,
                name="escalated_agentskill_proficiency_1_5",
            ),
        ),
    ]
