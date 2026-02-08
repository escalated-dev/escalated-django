import django
from django.conf import settings


def pytest_configure():
    settings.configure(
        DEBUG=True,
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "escalated",
        ],
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        AUTH_USER_MODEL="auth.User",
        ROOT_URLCONF="escalated.urls",
        ESCALATED={
            "MODE": "self_hosted",
            "TABLE_PREFIX": "escalated_",
            "DEFAULT_PRIORITY": "medium",
            "ALLOW_CUSTOMER_CLOSE": True,
            "AUTO_CLOSE_RESOLVED_AFTER_DAYS": 7,
            "MAX_ATTACHMENTS": 5,
            "MAX_ATTACHMENT_SIZE_KB": 10240,
            "SLA": {
                "ENABLED": True,
                "BUSINESS_HOURS_ONLY": False,
            },
            "NOTIFICATION_CHANNELS": [],  # Disable notifications in tests
            "WEBHOOK_URL": None,
        },
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": [],
                "APP_DIRS": True,
                "OPTIONS": {
                    "context_processors": [
                        "django.template.context_processors.request",
                        "django.contrib.auth.context_processors.auth",
                    ],
                },
            },
        ],
        MIDDLEWARE=[
            "django.middleware.common.CommonMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
        ],
        SECRET_KEY="test-secret-key-not-for-production",
    )
    django.setup()


import pytest
from django.contrib.auth.models import User

from tests.factories import (
    UserFactory,
    TicketFactory,
    ReplyFactory,
    TagFactory,
    DepartmentFactory,
    SlaPolicyFactory,
    EscalationRuleFactory,
    CannedResponseFactory,
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
