import os

from django.conf import settings


DEFAULTS = {
    "MODE": "self_hosted",
    "USER_MODEL": None,  # Falls back to settings.AUTH_USER_MODEL
    "TABLE_PREFIX": "escalated_",
    "ROUTE_PREFIX": "support",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": None,
    "ALLOW_CUSTOMER_CLOSE": True,
    "AUTO_CLOSE_RESOLVED_AFTER_DAYS": 7,
    "MAX_ATTACHMENTS": 5,
    "MAX_ATTACHMENT_SIZE_KB": 10240,
    "DEFAULT_PRIORITY": "medium",
    "SLA": {
        "ENABLED": True,
        "BUSINESS_HOURS_ONLY": False,
        "BUSINESS_HOURS": {
            "START": "09:00",
            "END": "17:00",
            "TIMEZONE": "UTC",
            "DAYS": [1, 2, 3, 4, 5],
        },
    },
    "NOTIFICATION_CHANNELS": ["email"],
    "WEBHOOK_URL": None,
    # Inbound email settings
    "INBOUND_EMAIL_ENABLED": False,
    "INBOUND_EMAIL_ADAPTER": "mailgun",
    "INBOUND_EMAIL_ADDRESS": "support@example.com",
    # Mailgun
    "MAILGUN_SIGNING_KEY": None,
    # Postmark
    "POSTMARK_INBOUND_TOKEN": None,
    # AWS SES
    "SES_REGION": "us-east-1",
    "SES_TOPIC_ARN": None,
    # IMAP
    "IMAP_HOST": None,
    "IMAP_PORT": 993,
    "IMAP_ENCRYPTION": "ssl",
    "IMAP_USERNAME": None,
    "IMAP_PASSWORD": None,
    "IMAP_MAILBOX": "INBOX",
    # REST API settings
    "API_ENABLED": False,
    "API_RATE_LIMIT": 60,
    "API_TOKEN_EXPIRY_DAYS": None,
    "API_PREFIX": "support/api/v1",
    # Plugin system settings
    "PLUGINS_ENABLED": True,
    "PLUGINS_PATH": None,  # Defaults to <BASE_DIR>/plugins/escalated at runtime
}


def get_setting(name):
    """
    Retrieve a setting from the ESCALATED dict in Django settings,
    falling back to DEFAULTS if not provided.
    """
    user_settings = getattr(settings, "ESCALATED", {})
    value = user_settings.get(name, DEFAULTS.get(name))

    # Special case: USER_MODEL defaults to AUTH_USER_MODEL
    if name == "USER_MODEL" and value is None:
        value = settings.AUTH_USER_MODEL

    # Special case: PLUGINS_PATH defaults to BASE_DIR/plugins/escalated
    if name == "PLUGINS_PATH" and value is None:
        base_dir = getattr(settings, "BASE_DIR", None)
        if base_dir:
            value = os.path.join(str(base_dir), "plugins", "escalated")
        else:
            value = os.path.join(os.getcwd(), "plugins", "escalated")

    # Deep-merge dicts (one level) for SLA settings
    if name == "SLA" and isinstance(value, dict):
        merged = {**DEFAULTS["SLA"]}
        merged.update(value)
        if "BUSINESS_HOURS" in value and isinstance(value["BUSINESS_HOURS"], dict):
            merged["BUSINESS_HOURS"] = {
                **DEFAULTS["SLA"]["BUSINESS_HOURS"],
                **value["BUSINESS_HOURS"],
            }
        return merged

    return value


def get_table_name(suffix):
    """Return a fully-prefixed table name."""
    prefix = get_setting("TABLE_PREFIX")
    return f"{prefix}{suffix}"
