import pytest
from tests.factories import (
    UserFactory,
    TicketFactory,
    ReplyFactory,
    TagFactory,
    DepartmentFactory,
    SlaPolicyFactory,
    EscalationRuleFactory,
    CannedResponseFactory,
    MacroFactory,
    ApiTokenFactory,
    TicketStatusFactory,
    BusinessScheduleFactory,
    HolidayFactory,
    PermissionFactory,
    RoleFactory,
    AuditLogFactory,
    CustomFieldFactory,
    CustomFieldValueFactory,
    TicketLinkFactory,
    SideConversationFactory,
    SideConversationReplyFactory,
    ArticleCategoryFactory,
    ArticleFactory,
)

@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def agent_user(db):
    department = DepartmentFactory()
    agent = UserFactory(username="agent")
    department.agents.add(agent)
    return agent


@pytest.fixture
def admin_user(db):
    return UserFactory(username="admin", is_staff=True, is_superuser=True)


@pytest.fixture
def department(db):
    return DepartmentFactory()


@pytest.fixture
def sla_policy(db):
    return SlaPolicyFactory()


@pytest.fixture
def default_sla_policy(db):
    return SlaPolicyFactory(is_default=True)


@pytest.fixture
def tag(db):
    return TagFactory()


@pytest.fixture
def ticket(db, user):
    return TicketFactory(requester=user)


@pytest.fixture
def canned_response(db, agent_user):
    return CannedResponseFactory(created_by=agent_user)


@pytest.fixture
def escalation_rule(db):
    return EscalationRuleFactory()


@pytest.fixture
def macro(db, agent_user):
    return MacroFactory(created_by=agent_user)


@pytest.fixture
def api_token(db, agent_user):
    """Create an API token for an agent. The `plain_text` attr holds the raw string."""
    return ApiTokenFactory(user=agent_user)


@pytest.fixture
def admin_api_token(db, admin_user):
    """Create an API token for an admin. The `plain_text` attr holds the raw string."""
    return ApiTokenFactory(user=admin_user)


@pytest.fixture
def ticket_status(db):
    return TicketStatusFactory()


@pytest.fixture
def business_schedule(db):
    return BusinessScheduleFactory()


@pytest.fixture
def holiday(db, business_schedule):
    return HolidayFactory(schedule=business_schedule)


@pytest.fixture
def permission(db):
    return PermissionFactory()


@pytest.fixture
def role(db):
    return RoleFactory()


@pytest.fixture
def audit_log(db, admin_user, ticket):
    from django.contrib.contenttypes.models import ContentType
    return AuditLogFactory(
        user=admin_user,
        auditable_content_type=ContentType.objects.get_for_model(ticket),
        auditable_object_id=ticket.pk,
    )


@pytest.fixture
def custom_field(db):
    return CustomFieldFactory()


@pytest.fixture
def article_category(db):
    return ArticleCategoryFactory()


@pytest.fixture
def article(db, article_category, admin_user):
    return ArticleFactory(category=article_category, author=admin_user)


@pytest.fixture
def side_conversation(db, ticket, admin_user):
    return SideConversationFactory(ticket=ticket, created_by=admin_user)


@pytest.fixture
def ticket_link(db):
    return TicketLinkFactory()
