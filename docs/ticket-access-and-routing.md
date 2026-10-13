# Ticket access and routing

All options are independent and disabled by default. Apply migration `0030`
before enabling them; it adds nullable account columns and SLA targets.

```python
ESCALATED = {
    "VISIBILITY": "department",  # default: "all"
    "ACCOUNTS": {
        "ENABLED": True,
        "RESOLVER": "your_app.support.resolve_account",
        "SCOPE_AGENTS": True,
    },
    "SLA": {"ENABLED": True, "TARGETED": True},
}
```

In department mode agents only see tickets in their departments. An assignment,
requester relationship, or follower relationship does not grant an agent an
exception. Tickets without a department are hidden from agents. Staff and
superusers retain full access. Customer and guest ownership checks still apply.

Package routes establish a request-local access context automatically, including
API bearer-token requests, lists, search, dashboards, bulk actions, reports and
widget lookups. Ticket-related ratings, replies, activities, links, conversations
and chats follow the same restrictions. Policies also check already-loaded
tickets. Membership is read for each query, and contexts are reset on exit.

Host views can install `escalated.ticket_access.TicketAccessMiddleware` after
authentication middleware. Host services can use an explicit context:

```python
from escalated.ticket_access import ticket_access
from escalated.models import Ticket

with ticket_access(agent):
    tickets = list(Ticket.objects.all())
```

Console and background work without a context retains full access. Trusted
internal code can use `Ticket.unrestricted`. Custom raw SQL, reverse joins from
host models and external storage drivers must apply the same restrictions;
managers do not rewrite arbitrary SQL. Cloud-only mode rejects these local
access options. Synced mode uses local access checks.

The account resolver receives a requester, attached subject, or agent model and
returns a persisted account model or `None`. Accounts are stored as a stable
Django model label and string primary key, compared case-sensitively. No account
table is supplied by the package. `ticket.account` resolves the host model.
Requester accounts are assigned at ticket creation; attaching a subject fills
an empty account without replacing an existing one. Host `TicketService.create`
calls may supply a `subjects` list so creation signals see the account.

Account visibility grants each agent exactly one account. A resolver returning
`None` grants no tickets. Account and department restrictions intersect when
both are enabled. Use departments for agents covering multiple accounts.
Staff list/API responses include `account_type` and `account_id` when accounts
are enabled, and lists accept those two parameters together as a filter.

Escalation conditions support `ticket_type`, `account_type`, `account_id` and
`account: {"type": "your_app.Company", "id": "123"}`. Automations and workflows
use their existing field/value format with the same names. Compound workflow
account conditions support `equals`, `not_equals`, `is_empty`, `is_not_empty`.
Incomplete account identities fail closed.

SLA policies may have a nullable `department` and `ticket_type`. With targeted
SLAs enabled, active matches rank: both targets, department only, type only,
then untargeted default. Lowest policy ID wins a tie. Without a match or default,
no policy is selected. With the option off only untargeted defaults apply.
Department/type changes preserve the existing policy and deadlines. Explicitly
call `SlaService.attach_default_policy(ticket)` to select again; deadlines are
measured from ticket creation. Retarget policies before deleting a department.

Notification recipients and automatic assignment candidates are checked against
ticket access. Restricted agents cannot subscribe to broad ticket channels;
host subscriptions should call `can_access_channel(user, channel)`. Chat
WebSockets recheck access before each delivery when restrictions are enabled.
Anonymous chat clients supply their existing private customer session identifier
as the `session` query parameter. Scoped HTTP polling remains available.
