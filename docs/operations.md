# Running Escalated for Django

## Hosting Modes

### Self-Hosted (default)

Everything stays in your database. No external calls. Full autonomy.

```python
ESCALATED = {
    "MODE": "self_hosted",
}
```

### Synced

Local database + automatic sync to `cloud.escalated.dev` for unified inbox across multiple apps. If the cloud is unreachable, your app keeps working — events queue and retry.

```python
ESCALATED = {
    "MODE": "synced",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

Agent actions taken in the cloud portal come back through a signed webhook. Set the
site's signing secret (shown on the connected site in the cloud dashboard) and give
the cloud this URL:

```python
ESCALATED = {
    "MODE": "synced",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
    "HOSTED_SIGNING_SECRET": "whsec_...",  # webhook URL: https://your-app.example.com/support/cloud/webhook/
}
```

The receiver verifies `X-Escalated-Signature` (HMAC-SHA256 of the raw body), ignores replayed
`event_id`s for 24 hours, and applies subject, description, priority and status from
`ticket.updated` / `ticket.status_changed` to the local ticket whose `reference` matches the
projection's `external_id`. Changes run through the local driver, so your signal handlers fire,
and are not echoed back to the cloud.

### Cloud

All ticket data proxied to the cloud API. Your app handles auth and renders UI, but storage lives in the cloud.

```python
ESCALATED = {
    "MODE": "cloud",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

All three modes share the same views, UI, and business logic. The driver pattern handles the rest.

## Configuration

Add to your `settings.py`:

```python
ESCALATED = {
    "MODE": "self_hosted",  # self_hosted | synced | cloud
    "TABLE_PREFIX": "escalated_",
    "ROUTE_PREFIX": "support",
    "DEFAULT_PRIORITY": "medium",
    # Tickets
    "ALLOW_CUSTOMER_CLOSE": True,
    "AUTO_CLOSE_RESOLVED_AFTER_DAYS": 7,
    "MAX_ATTACHMENTS": 5,
    "MAX_ATTACHMENT_SIZE_KB": 10240,
    "ATTACHMENT_DOWNLOAD_TTL_MINUTES": 10,  # see docs/private-attachments.md
    # SLA
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
    # Notifications
    "NOTIFICATION_CHANNELS": ["email"],
    "WEBHOOK_URL": None,
    # Email threading: domain for Message-IDs, secret that signs the Reply-To
    "EMAIL_DOMAIN": "support.example.com",
    "EMAIL_INBOUND_SECRET": "",
    # Cloud/Synced mode
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": None,
}
```

### Inbound email

Inbound mail is matched to a ticket like this:

- **Thread matching**: when `EMAIL_INBOUND_SECRET` is set, outbound mail carries a signed Reply-To (`reply+{id}.{hmac8}@domain`) and only that address links an inbound email to a ticket. Without a secret, the `In-Reply-To` / `References` Message-IDs and the subject reference (e.g. `[ESC-A1B2C3]`) are used instead.
- **Sender check**: a matched email becomes a reply only when the `From` address is the ticket's requester (the guest email or the requester's email, case-insensitive). It is posted as that requester. Staff identity is never taken from the `From` header, so agents reply in the app.
- **Anything else** (no match, or a sender who is not the requester) creates a new ticket, so mail is never dropped.
- **Reopen**: an accepted reply reopens a resolved or closed ticket.

Set a secret in production; Message-IDs and ticket references can be guessed.

### UUID / string user keys

Escalated works with any `AUTH_USER_MODEL` primary key type — integer, UUID, or
string. References to your users via `ForeignKey(AUTH_USER_MODEL)` (assignee,
follower, author, etc.) already match your user PK automatically. The remaining
host-user references — `Contact.user_id` and the generic-relation `object_id`
columns for ticket requester, activity causer, satisfaction `rated_by`, and API
token owner — are stored as `CharField`, so they hold an integer id (as its
string form) or a UUID/string id transparently. No configuration is required;
just run migrations.

### Ticket subjects

A ticket has a **requester** (who raised it) and a **subject line** (free text).
You can also attach host-app entities the ticket is *about* — a project, customer,
or asset — so agents see context and can jump back into your app.

Implement the presentation contract on any model (or use the mixin for defaults):

```python
from django.db import models

from escalated.contracts import TicketSubjectMixin


class Project(models.Model, TicketSubjectMixin):
    name = models.CharField(max_length=255)

    def ticket_subject_subtitle(self):
        return f"Project · {self.customer.name}"

    def ticket_subject_url(self):
        return reverse("projects:detail", args=[self.pk])
```

Attach, detach, or replace subjects on a ticket:

```python
ticket.attach_subject(project, role="project")
ticket.attach_subject(customer, role="account")
ticket.sync_subjects([project, (customer, "account")])
ticket.detach_subject(project)
```

Each link is serialized on the ticket as
`{ type, id, role, title, subtitle, url, color, icon, missing }`.
`object_id` is stored as a string so integer, UUID, and string primary keys all work.

To allow attaching via the agent or REST API (and block arbitrary model resolution),
list permitted models in settings:

```python
ESCALATED = (
    {
        # ...
        "TICKET_SUBJECT_TYPES": [
            "myapp.Project",
            "myapp.Customer",
        ],
    },
)
```

Leave `TICKET_SUBJECT_TYPES` empty to disable API attach; programmatic
`attach_subject()` still works for any model when the allowlist is empty.

Agent/admin routes: `POST /…/tickets/<id>/subjects`, `DELETE /…/tickets/<id>/subjects/<link_id>`.
REST API: `POST /tickets/<reference>/subjects`, `DELETE /tickets/<reference>/subjects/<link_id>`.

## Management Commands

```bash
# Check SLA deadlines and fire breach notifications
python manage.py check_sla

# Evaluate escalation rules against open tickets
python manage.py evaluate_escalations

# Auto-close tickets resolved more than N days ago
python manage.py close_resolved --days 7

# Purge old activity logs
python manage.py purge_activities --days 90

# Purge expired tokens/codes and apply the Data Retention settings
# (Admin > Settings > Data Retention; every setting defaults to "never")
python manage.py purge_expired_data [--dry-run]

# Run SDK plugins' due cron schedules (every minute, with SDK_ENABLED)
python manage.py escalated_plugin_cron
```

Data retention deletes closed tickets outright (this package has no soft
delete), together with their replies, attachments and stored files. Run
`purge_expired_data` daily.

Schedule these with cron, Celery Beat, or django-crontab for automated enforcement.

## Custom Ticket Actions

Host projects can add custom buttons to the agent ticket screen and handle clicks
with a normal Django signal receiver. Register actions in settings:

```python
# settings.py
ESCALATED = {
    # ...
    "TICKET_ACTIONS": [
        {
            "key": "sync-crm",
            "label": "Sync CRM",
            "variant": "primary",  # primary | secondary | danger
            "confirmation": "Sync this ticket to the CRM?",
            "metadata": {"icon": "refresh-cw"},
            # visible / enabled may be a bool or a callable(ticket, user)
            "enabled": lambda ticket, user: not ticket.metadata.get("crm_synced"),
        },
    ],
}
```

Visible actions are exposed on the agent ticket page as `customActions` and on the
API ticket detail response as `custom_actions` (each with a `url` and `method`).
Triggering one (`POST /support/agent/tickets/<id>/actions/<key>/` or the API route
`/<prefix>/tickets/<reference>/actions/<key>/`) validates the action is visible
(404) and enabled (403), then sends the `custom_action_triggered` signal:

```python
from django.dispatch import receiver
from escalated.signals import custom_action_triggered


@receiver(custom_action_triggered)
def on_custom_action(sender, ticket, user, action_key, payload, metadata, **kwargs):
    if action_key != "sync-crm":
        return
    # your handler
```

Escalated also records an internal note on the ticket whenever an action fires,
for auditability.

## Routes

All routes use the configurable prefix (default: `support`). A ticket's `<id>`
in these paths may also be its reference (`ESC-A1B2C3`), as the shared pages link it.

| Route | Method | Description |
|-------|--------|-------------|
| `/support/tickets/` | GET | Customer ticket list |
| `/support/tickets/create/` | GET | New ticket form |
| `/support/tickets/<id>/` | GET | Ticket detail |
| `/support/agent/` | GET | Agent dashboard |
| `/support/agent/tickets/` | GET | Agent ticket queue |
| `/support/agent/tickets/<id>/` | GET | Agent ticket view |
| `/support/admin/reports/` | GET | Admin reports |
| `/support/admin/departments/` | GET | Department management |
| `/support/admin/sla-policies/` | GET | SLA policy management |
| `/support/admin/escalation-rules/` | GET | Escalation rule management |
| `/support/admin/tags/` | GET | Tag management |
| `/support/admin/canned-responses/` | GET | Canned response management |
| `/support/agent/tickets/bulk/` | POST | Bulk actions on multiple tickets |
| `/support/agent/tickets/<id>/follow/` | POST | Follow/unfollow a ticket |
| `/support/agent/tickets/<id>/macro/` | POST | Apply a macro to a ticket |
| `/support/agent/tickets/<id>/presence/` | POST | Update presence on a ticket |
| `/support/agent/tickets/<id>/pin/<reply_id>/` | POST | Pin/unpin an internal note |
| `/support/tickets/<id>/rate/` | POST | Submit satisfaction rating |

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

## Database connection

By default Escalated's tables live on your project's `default` database. Name a
different one to keep them somewhere else — a schema shared with a legacy
system, a multi-tenant split, a separate reporting store, or simply out of your
primary database.

Django has no per-model connection setting; routing is the mechanism, so this
takes two pieces of configuration:

```python
# settings.py
DATABASES = {
    "default": {...},
    "support": {...},
}

DATABASE_ROUTERS = ["escalated.routers.EscalatedRouter"]

ESCALATED = {
    "DATABASE": "support",
}
```

Leave `DATABASE` unset (or omit the router) for the `default` database — the
historical behaviour, and what almost every project wants. The router returns
"no opinion" for everything when nothing is configured, so adding it to a
project that has not set `DATABASE` changes nothing.

Migrate Escalated's tables onto it with:

```bash
python manage.py migrate escalated --database=support
```

### Foreign keys to your user table

Escalated's relations to `AUTH_USER_MODEL` are declared `db_constraint=False`.
**Django cannot create a foreign key across databases**, so while those
constraints existed the setting could not work at all — `migrate` failed on the
first user-referencing table.

This does not change Django's behaviour. `on_delete` is implemented in Python by
the deletion collector, not by a database `ON DELETE` clause, and Django never
emits one; cascades and `SET_NULL` work exactly as before. What is given up is
the database's own referential check against direct SQL writes that bypass the
ORM — which is also the only way the two sides could ever live apart.

Migration `0028_drop_host_user_fk_constraints` applies it. It runs on every
install, including single-database ones.

**Your user table does not move.** The router has no opinion about it, so it
stays wherever your project keeps it.

### What cannot cross the boundary

Single-object traversal works: `ticket.assigned_to` is resolved with a second
query, routed by the router, so a ticket on one database resolves its assignee
on another.

A **join** cannot span two databases — nothing can do that. So a queryset that
filters or `select_related`s *through* the user model, like
`Ticket.objects.select_related("assigned_to")` or
`.filter(assigned_to__email=...)`, is not available when the two are separated.
Filter on the key instead (`assigned_to_id=...`) and load the users in a second
query.
