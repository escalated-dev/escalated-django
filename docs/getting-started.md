# Getting started

## Requirements

- Python 3.10+
- Django 5.2+
- Node.js 18+ (for frontend assets)

## Quick Start

```bash
pip install escalated-django
npm install @escalated-dev/escalated
```

### 1. Add to INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    "django.contrib.contenttypes",
    "inertia",
    "escalated",
]
```

### 2. Include URLs

```python
from django.urls import path, include

urlpatterns = [
    # ...
    path("support/", include("escalated.urls")),
]
```

### 3. Run migrations

```bash
python manage.py migrate escalated
```

Visit `/support` — you're live.

`python manage.py install` runs the migrations, seeds permissions, a default
department and SLA policy, and then checks the setup: it reports a user model
Escalated cannot gate (see below), no admin users, no agents, roles nobody
holds while roles & permissions is on, and recurring jobs that are not running.

### 4. Make yourself staff

Admins are users with `is_staff` or `is_superuser`; agents are the users in an
active department's `agents`. A custom user model must have `is_staff` or
`is_superuser` (subclass `AbstractUser`, or add `PermissionsMixin` and an
`is_staff` field). Without either, staff pages raise
`escalated.permissions.UserModelNotSupported` naming the model and the fix, and
`manage.py check` warns (`escalated.W004`).

## Required: schedule the recurring jobs

Django has no scheduler of its own, so Escalated's recurring jobs run only
when you schedule them (cron, Celery beat, a systemd timer, django-crontab...).
Until you do, SLA timers never breach, escalation rules and automations never
fire and snoozed tickets never wake.

| Command | Interval |
|---|---|
| `python manage.py check_sla` | every minute |
| `python manage.py wake_snoozed_tickets` | every minute |
| `python manage.py evaluate_escalations` | every 5 minutes |
| `python manage.py run_automations` | every 5 minutes |
| `python manage.py close_resolved` | daily |
| `python manage.py purge_expired_data` | daily |
| `python manage.py purge_activities` | weekly |
| `python manage.py poll_imap` | every minute, with the IMAP inbound adapter |
| `python manage.py close_idle_chats` and `cleanup_abandoned_chats` | every minute, with live chat on |
| `python manage.py dispatch_newsletters` | every minute, with newsletters on |
| `python manage.py escalated_plugin_cron` | every minute, with `SDK_ENABLED` |

For example, in a crontab (run from your project, with its virtualenv):

```cron
* * * * *   python manage.py check_sla && python manage.py wake_snoozed_tickets
*/5 * * * * python manage.py evaluate_escalations && python manage.py run_automations
0 3 * * *   python manage.py close_resolved && python manage.py purge_expired_data
0 4 * * 0   python manage.py purge_activities
```

`check_sla` records a heartbeat each time it runs. While the heartbeat is
missing or more than 15 minutes old, Admin > Settings and the admin reports
pages warn that the recurring jobs are not running and list these commands
(the `scheduler` page prop), Escalated logs a warning (logger
`escalated.scheduler`), and `python manage.py check --database default`
reports it (`escalated.W003`).

## Embedding the admin in your own admin panel (optional)

Escalated's standalone admin at `/support/admin/` is the default and needs no
setup. If your project already has an admin panel or back office, you can
instead mount Escalated's admin screens under your own prefix and view
decorators, render them inside your Vue + Inertia layout or your own Django
template (or an allow-listed iframe), and list Escalated's menu in your own
sidebar. It is off unless you turn it on:

```python
# settings.py
from escalated.embed import embed_admin

ESCALATED = {
    # ...
    "EMBED": embed_admin(
        prefix="admin/support",
        middleware=["django.contrib.admin.views.decorators.staff_member_required"],
        layout="Layouts/AdminLayout",
    ),
}

# urls.py: in place of path("support/", include("escalated.urls"))
urlpatterns = [path("", include("escalated.embed_urls"))]
```

URL names stay the same, Escalated's admin gate stays on unless you replace it,
and the agent panel, customer portal, widget and API do not move. See
[embedding the admin](embedding-admin.md).
