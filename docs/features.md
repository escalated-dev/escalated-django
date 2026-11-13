# Features

## Features

- **Ticket lifecycle** — Create, assign, reply, resolve, close, reopen with configurable status transitions
- **Access control** — Roles & permissions as an install-level switch, enforced on every admin, agent and staff API view when on and hidden when off; see [access control](access-control.md)
- **SLA engine** — Per-priority response and resolution targets, business hours calculation, automatic breach detection
- **Escalation rules** — Condition-based rules that auto-escalate, reprioritize, reassign, or notify
- **Agent dashboard** — Ticket queue with filters, bulk actions, internal notes, canned responses
- **Customer portal** — Self-service ticket creation, replies, and status tracking
- **Admin panel** — Manage departments, SLA policies, escalation rules, tags, and view reports
- **File attachments** — Drag-and-drop uploads with configurable storage and size limits
- **Activity timeline** — Full audit log of every action on every ticket
- **Email notifications** — Configurable per-event notifications with webhook support
- **Department routing** — Organize agents into departments with auto-assignment (round-robin)
- **Tagging system** — Categorize tickets with colored tags
- **Inertia.js + Vue 3 UI** — Shared frontend via [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated)
- **Ticket splitting** — Split a reply into a new standalone ticket while preserving the original context
- **Ticket snooze** — Snooze tickets with presets (1h, 4h, tomorrow, next week); `python manage.py wake_snoozed_tickets` management command auto-wakes them on schedule
- **Saved views / custom queues** — Save, name, and share filter presets as reusable ticket views
- **Embeddable support widget** — Lightweight `<script>` widget with KB search, ticket form, and status check
- **Email threading** — Outbound emails include proper `In-Reply-To` and `References` headers for correct threading in mail clients
- **Inbound email** — Mailgun, Postmark, SES webhooks and IMAP polling create tickets and replies. See [Inbound email](operations.md#inbound-email)
- **Branded email templates** — Configurable logo, primary color, and footer text for all outbound emails
- **Real-time broadcasting** — Opt-in broadcasting via Django Channels with automatic polling fallback
- **Knowledge base toggle** — Enable or disable the public knowledge base from admin settings
