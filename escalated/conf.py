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
