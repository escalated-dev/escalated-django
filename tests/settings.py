from escalated.locale_paths import get_locale_paths

DEBUG = True
USE_TZ = True

# Compose LOCALE_PATHS with the plugin-local override first (winning
# priority) and the central `escalated-locale` package second. This
# mirrors the wiring host projects are documented to use in the README.
LOCALE_PATHS = get_locale_paths()

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
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
