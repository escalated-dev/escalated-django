"""
Translation between this package's ticket vocabulary and the one
cloud.escalated.dev speaks. Used by the cloud webhook receiver on the way in.
Values not listed pass through unchanged.
"""

PRIORITY_FROM_CLOUD = {"normal": "medium"}
STATUS_FROM_CLOUD = {"waiting": "waiting_on_customer", "snoozed": "open"}
PRIORITY_TO_CLOUD = {"medium": "normal", "critical": "urgent"}
STATUS_TO_CLOUD = {
    "waiting_on_customer": "waiting",
    "waiting_on_agent": "waiting",
    "escalated": "open",
    "reopened": "open",
}

LOCAL_STATUSES = frozenset(
    {"open", "in_progress", "waiting_on_customer", "waiting_on_agent", "escalated", "resolved", "closed", "reopened"}
)
LOCAL_PRIORITIES = frozenset({"low", "medium", "high", "urgent", "critical"})


def priority_from_cloud(value):
    value = str(value)
    return PRIORITY_FROM_CLOUD.get(value, value)


def status_from_cloud(value):
    value = str(value)
    return STATUS_FROM_CLOUD.get(value, value)


def priority_to_cloud(value):
    value = str(value)
    return PRIORITY_TO_CLOUD.get(value, value)


def status_to_cloud(value):
    value = str(value)
    return STATUS_TO_CLOUD.get(value, value)
