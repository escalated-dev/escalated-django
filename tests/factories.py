import factory
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType

from escalated.models import (
    Ticket,
    Reply,
    Tag,
    Department,
    SlaPolicy,
    EscalationRule,
    CannedResponse,
)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    is_active = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        manager = cls._get_manager(model_class)
        password = kwargs.pop("password", "testpass123")
        user = manager.create_user(*args, **kwargs)
        user.set_password(password)
        user.save()
        return user


class DepartmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Department
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Department {n}")
    slug = factory.Sequence(lambda n: f"department-{n}")
    description = factory.Faker("sentence")
    is_active = True


class SlaPolicyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SlaPolicy

    name = factory.Sequence(lambda n: f"SLA Policy {n}")
    description = factory.Faker("sentence")
    is_default = False
    first_response_hours = factory.LazyFunction(
        lambda: {
            "low": 24,
            "medium": 8,
            "high": 4,
            "urgent": 1,
            "critical": 0.5,
        }
    )
    resolution_hours = factory.LazyFunction(
        lambda: {
            "low": 72,
            "medium": 24,
            "high": 8,
            "urgent": 4,
            "critical": 2,
        }
    )
    business_hours_only = False
    is_active = True


class TagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tag
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Tag {n}")
    slug = factory.Sequence(lambda n: f"tag-{n}")
    color = "#6b7280"


class TicketFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Ticket

    subject = factory.Faker("sentence", nb_words=6)
    description = factory.Faker("paragraph")
    status = Ticket.Status.OPEN
    priority = Ticket.Priority.MEDIUM
    channel = "web"

    class Params:
        requester = None

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        requester = kwargs.pop("requester", None)
        if requester:
            ct = ContentType.objects.get_for_model(requester)
            kwargs["requester_content_type"] = ct
            kwargs["requester_object_id"] = requester.pk

        return super()._create(model_class, *args, **kwargs)


class ReplyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Reply

    ticket = factory.SubFactory(TicketFactory)
    author = factory.SubFactory(UserFactory)
    body = factory.Faker("paragraph")
    is_internal_note = False
    type = Reply.Type.REPLY


class EscalationRuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EscalationRule

    name = factory.Sequence(lambda n: f"Escalation Rule {n}")
    description = factory.Faker("sentence")
    trigger_type = EscalationRule.TriggerType.SLA_BREACH
    conditions = factory.LazyFunction(lambda: {})
    actions = factory.LazyFunction(lambda: {"escalate": True})
    order = factory.Sequence(lambda n: n)
    is_active = True


class CannedResponseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CannedResponse

    title = factory.Sequence(lambda n: f"Canned Response {n}")
    body = factory.Faker("paragraph")
    category = "general"
    created_by = factory.SubFactory(UserFactory)
    is_shared = True
