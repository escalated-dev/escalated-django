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
