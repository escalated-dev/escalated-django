# escalated-django

Embeddable support ticket system for Django applications. Uses Inertia.js + Vue 3 for the frontend UI.

## Installation

```bash
pip install escalated-django
```

## Quick Start

### 1. Add to INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    'django.contrib.contenttypes',
    'inertia',
    'escalated',
]
```

### 2. Configure settings

```python
ESCALATED = {
    "MODE": "self_hosted",          # "self_hosted", "synced", or "cloud"
    "TABLE_PREFIX": "escalated_",
    "ROUTE_PREFIX": "support",
    "DEFAULT_PRIORITY": "medium",
    "ALLOW_CUSTOMER_CLOSE": True,
    "AUTO_CLOSE_RESOLVED_AFTER_DAYS": 7,
    "MAX_ATTACHMENTS": 5,
    "MAX_ATTACHMENT_SIZE_KB": 10240,
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
```

### 3. Include URLs

```python
from django.urls import path, include

urlpatterns = [
    # ...
    path("support/", include("escalated.urls")),
]
```

### 4. Run migrations

```bash
python manage.py migrate escalated
```

### 5. Set up Inertia.js

This package requires `inertia-django` for rendering views. Install it and configure your Vue 3 frontend to render the Escalated components.

```bash
pip install inertia-django
```

See the [inertia-django documentation](https://github.com/inertiajs/inertia-django) for setup instructions.

## Hosting Modes

### Self-hosted (default)

All data stored in your local database. Full control.

```python
ESCALATED = {"MODE": "self_hosted"}
```

### Synced

Data stored locally AND synced to Escalated Cloud for backup and analytics.

```python
ESCALATED = {
    "MODE": "synced",
    "HOSTED_API_KEY": "your-api-key",
}
```

### Cloud

All data proxied to Escalated Cloud. No local ticket storage.

```python
ESCALATED = {
    "MODE": "cloud",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

## Management Commands

```bash
# Check SLA deadlines and send breach/warning notifications
python manage.py check_sla

# Evaluate escalation rules against open tickets
python manage.py evaluate_escalations

# Auto-close tickets resolved more than N days ago
python manage.py close_resolved --days 7

# Purge old activity logs
python manage.py purge_activities --days 90
```

Schedule these with cron or Django-celery-beat for automated enforcement.

## URL Structure

### Customer routes
- `GET /support/tickets/` - List my tickets
- `GET /support/tickets/create/` - Create ticket form
- `POST /support/tickets/store/` - Submit new ticket
- `GET /support/tickets/<id>/` - View ticket
- `POST /support/tickets/<id>/reply/` - Reply to ticket
- `POST /support/tickets/<id>/close/` - Close ticket
- `POST /support/tickets/<id>/reopen/` - Reopen ticket

### Agent routes
- `GET /support/agent/` - Agent dashboard
- `GET /support/agent/tickets/` - All tickets
- `GET /support/agent/tickets/<id>/` - Ticket detail
- `POST /support/agent/tickets/<id>/reply/` - Agent reply
- `POST /support/agent/tickets/<id>/note/` - Internal note
- `POST /support/agent/tickets/<id>/assign/` - Assign agent
- `POST /support/agent/tickets/<id>/status/` - Change status
- `POST /support/agent/tickets/<id>/priority/` - Change priority

### Admin routes
- `GET /support/admin/reports/` - Analytics dashboard
- CRUD for departments, SLA policies, escalation rules, tags, canned responses

## Signals

Connect to ticket lifecycle events:

```python
from escalated.signals import ticket_created, ticket_resolved

@receiver(ticket_created)
def on_ticket_created(sender, ticket, user, **kwargs):
    print(f"New ticket: {ticket.reference}")

@receiver(ticket_resolved)
def on_ticket_resolved(sender, ticket, user, **kwargs):
    print(f"Resolved: {ticket.reference}")
```

Available signals: `ticket_created`, `ticket_updated`, `ticket_status_changed`, `ticket_assigned`, `ticket_unassigned`, `ticket_priority_changed`, `ticket_escalated`, `ticket_resolved`, `ticket_closed`, `ticket_reopened`, `reply_created`, `internal_note_added`, `sla_breached`, `sla_warning`, `tag_added`, `tag_removed`, `department_changed`.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
