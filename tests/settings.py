import os

from django.core.exceptions import ImproperlyConfigured

from escalated.locale_paths import get_locale_paths

DEBUG = True
USE_TZ = True

# Compose LOCALE_PATHS with the plugin-local override first (winning
# priority) and the central `escalated-locale` package second. This
# mirrors the wiring host projects are documented to use in the README.
LOCALE_PATHS = get_locale_paths()

# The suite runs on SQLite unless ESCALATED_TEST_ENGINE says otherwise, so it
# needs nothing installed locally. CI runs it three times -- sqlite, postgres
# and mysql -- because the three disagree about enough to matter: PostgreSQL
# refuses to compare a boolean to an integer and its LIKE is case-sensitive,
# MySQL's is not, aggregates come back as Decimal from one backend and int from
# another, and SQLite enforces no foreign keys unless asked. A suite that has
# only ever seen SQLite has tested none of it.
#
# An unrecognised value raises rather than falling back: a CI leg that quietly
# ran SQLite would report green having tested nothing the matrix exists for.
_ENGINES = {
    "sqlite": "django.db.backends.sqlite3",
    "postgres": "django.db.backends.postgresql",
    "mysql": "django.db.backends.mysql",
}

TEST_ENGINE = os.environ.get("ESCALATED_TEST_ENGINE", "sqlite")

if TEST_ENGINE not in _ENGINES:
    raise ImproperlyConfigured(
        f"ESCALATED_TEST_ENGINE must be one of {', '.join(sorted(_ENGINES))}; got {TEST_ENGINE!r}."
    )

if TEST_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": _ENGINES[TEST_ENGINE],
            "NAME": ":memory:",
        }
    }
else:
    _default_port = "5432" if TEST_ENGINE == "postgres" else "3306"
    _default_user = "postgres" if TEST_ENGINE == "postgres" else "root"

    DATABASES = {
        "default": {
            "ENGINE": _ENGINES[TEST_ENGINE],
            "NAME": os.environ.get("ESCALATED_TEST_NAME", "escalated_test"),
            "USER": os.environ.get("ESCALATED_TEST_USER", _default_user),
            "PASSWORD": os.environ.get("ESCALATED_TEST_PASSWORD", ""),
            "HOST": os.environ.get("ESCALATED_TEST_HOST", "127.0.0.1"),
            "PORT": os.environ.get("ESCALATED_TEST_PORT", _default_port),
        }
    }

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "escalated",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "auth.User"
ROOT_URLCONF = "tests.urls"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

ESCALATED = {
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
    "NOTIFICATION_CHANNELS": [],
    "WEBHOOK_URL": None,
    "API_ENABLED": True,
    "API_RATE_LIMIT": 60,
    "API_TOKEN_EXPIRY_DAYS": None,
    "API_PREFIX": "support/api/v1",
}

TEMPLATES = [
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
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

SECRET_KEY = "test-secret-key-not-for-production"
