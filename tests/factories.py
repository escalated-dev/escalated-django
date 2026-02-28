import hashlib
import secrets

import factory
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType

from escalated.models import (
    ApiToken,
    Ticket,
    Reply,
    Tag,
    Department,
    SlaPolicy,
    EscalationRule,
    CannedResponse,
    Macro,
    AuditLog,
    TicketStatus,
    BusinessSchedule,
    Holiday,
    Role,
    Permission,
    CustomField,
    CustomFieldValue,
    TicketLink,
    SideConversation,
    SideConversationReply,
    ArticleCategory,
    Article,
    AgentProfile,
    Skill,
    AgentCapacity,
    Webhook,
    WebhookDelivery,
    Automation,
    TwoFactor,
    CustomObject,
    CustomObjectRecord,
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


class MacroFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Macro

    name = factory.Sequence(lambda n: f"Macro {n}")
    description = factory.Faker("sentence")
    actions = factory.LazyFunction(lambda: [{"type": "set_status", "value": "open"}])
    is_shared = True
    order = factory.Sequence(lambda n: n)
    created_by = factory.SubFactory(UserFactory)


class ApiTokenFactory(factory.django.DjangoModelFactory):
    """
    Factory that creates an ApiToken with a known plain-text value.

    Usage:
        token = ApiTokenFactory(user=some_user)
        # token.plain_text is the raw token string
        # token is the ApiToken model instance
    """

    class Meta:
        model = ApiToken
        exclude = ["user", "plain_text"]

    user = factory.SubFactory(UserFactory)
    plain_text = factory.LazyFunction(lambda: secrets.token_hex(32))
    name = factory.Sequence(lambda n: f"Test Token {n}")
    token = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.plain_text.encode()).hexdigest()
    )
    abilities = factory.LazyFunction(lambda: ["*"])
    expires_at = None

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        user = kwargs.pop("user", None)
        plain_text = kwargs.pop("plain_text", secrets.token_hex(32))

        if user:
            ct = ContentType.objects.get_for_model(user)
            kwargs["tokenable_content_type"] = ct
            kwargs["tokenable_object_id"] = user.pk

        kwargs["token"] = hashlib.sha256(plain_text.encode()).hexdigest()

        instance = super()._create(model_class, *args, **kwargs)
        # Attach the plain_text for test usage
        instance.plain_text = plain_text
        return instance


class TicketStatusFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TicketStatus

    label = factory.Sequence(lambda n: f"Status {n}")
    slug = factory.Sequence(lambda n: f"status-{n}")
    category = "open"
    color = "#6b7280"
    description = factory.Faker("sentence")
    position = factory.Sequence(lambda n: n)
    is_default = False


class BusinessScheduleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BusinessSchedule

    name = factory.Sequence(lambda n: f"Schedule {n}")
    timezone = "UTC"
    is_default = False
    schedule = factory.LazyFunction(lambda: {
        "monday": {"start": "09:00", "end": "17:00"},
        "tuesday": {"start": "09:00", "end": "17:00"},
        "wednesday": {"start": "09:00", "end": "17:00"},
        "thursday": {"start": "09:00", "end": "17:00"},
        "friday": {"start": "09:00", "end": "17:00"},
    })


class HolidayFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Holiday

    schedule = factory.SubFactory(BusinessScheduleFactory)
    name = factory.Sequence(lambda n: f"Holiday {n}")
    date = factory.LazyFunction(lambda: __import__('datetime').date(2026, 12, 25))
    recurring = False


class PermissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Permission
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Permission {n}")
    slug = factory.Sequence(lambda n: f"permission-{n}")
    group = "general"
    description = factory.Faker("sentence")


class RoleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Role

    name = factory.Sequence(lambda n: f"Role {n}")
    slug = factory.Sequence(lambda n: f"role-{n}")
    description = factory.Faker("sentence")
    is_system = False


class AuditLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AuditLog

    user = factory.SubFactory(UserFactory)
    action = "created"
    auditable_content_type = factory.LazyAttribute(
        lambda o: ContentType.objects.get_for_model(Ticket)
    )
    auditable_object_id = 1
    old_values = None
    new_values = factory.LazyFunction(lambda: {"status": "open"})
    ip_address = "127.0.0.1"
    user_agent = "TestAgent/1.0"


class CustomFieldFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomField

    name = factory.Sequence(lambda n: f"Field {n}")
    slug = factory.Sequence(lambda n: f"field-{n}")
    type = "text"
    context = "ticket"
    required = False
    position = factory.Sequence(lambda n: n)
    active = True


class CustomFieldValueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomFieldValue

    custom_field = factory.SubFactory(CustomFieldFactory)
    entity_content_type = factory.LazyAttribute(
        lambda o: ContentType.objects.get_for_model(Ticket)
    )
    entity_object_id = 1
    value = factory.Faker("word")


class TicketLinkFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TicketLink

    parent_ticket = factory.SubFactory(TicketFactory)
    child_ticket = factory.SubFactory(TicketFactory)
    link_type = "related"


class SideConversationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SideConversation

    ticket = factory.SubFactory(TicketFactory)
    subject = factory.Sequence(lambda n: f"Side Conversation {n}")
    channel = "internal"
    status = "open"
    created_by = factory.SubFactory(UserFactory)


class SideConversationReplyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SideConversationReply

    side_conversation = factory.SubFactory(SideConversationFactory)
    body = factory.Faker("paragraph")
    author = factory.SubFactory(UserFactory)


class ArticleCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ArticleCategory
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.Sequence(lambda n: f"category-{n}")
    position = factory.Sequence(lambda n: n)
    description = factory.Faker("sentence")


class ArticleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Article

    category = factory.SubFactory(ArticleCategoryFactory)
    title = factory.Sequence(lambda n: f"Article {n}")
    slug = factory.Sequence(lambda n: f"article-{n}")
    body = factory.Faker("paragraph")
    status = "draft"
    author = factory.SubFactory(UserFactory)


class AgentProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AgentProfile

    user = factory.SubFactory(UserFactory)
    agent_type = "full"
    max_tickets = None


class SkillFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Skill
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Skill {n}")
    slug = factory.Sequence(lambda n: f"skill-{n}")


class AgentCapacityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AgentCapacity

    user = factory.SubFactory(UserFactory)
    channel = "default"
    max_concurrent = 10
    current_count = 0


class WebhookFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Webhook

    url = factory.Sequence(lambda n: f"https://example.com/webhook/{n}")
    events = factory.LazyFunction(lambda: ["ticket.created", "ticket.updated"])
    secret = factory.Faker("sha256")
    active = True


class WebhookDeliveryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WebhookDelivery

    webhook = factory.SubFactory(WebhookFactory)
    event = "ticket.created"
    payload = factory.LazyFunction(lambda: {"ticket_id": 1})
    response_code = 200
    attempts = 1


class AutomationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Automation

    name = factory.Sequence(lambda n: f"Automation {n}")
    conditions = factory.LazyFunction(lambda: [{"field": "status", "operator": "=", "value": "open"}])
    actions = factory.LazyFunction(lambda: [{"type": "change_status", "value": "in_progress"}])
    active = True
    position = factory.Sequence(lambda n: n)


class TwoFactorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TwoFactor

    user = factory.SubFactory(UserFactory)
    secret = factory.LazyFunction(lambda: "JBSWY3DPEHPK3PXP")
    recovery_codes = factory.LazyFunction(lambda: ["AAAAAAAA-BBBBBBBB", "CCCCCCCC-DDDDDDDD"])
    confirmed_at = None


class CustomObjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomObject

    name = factory.Sequence(lambda n: f"Object {n}")
    slug = factory.Sequence(lambda n: f"object-{n}")
    fields_schema = factory.LazyFunction(lambda: [{"name": "field1", "type": "text", "required": True}])


class CustomObjectRecordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomObjectRecord

    object = factory.SubFactory(CustomObjectFactory)
    data = factory.LazyFunction(lambda: {"field1": "value1"})
