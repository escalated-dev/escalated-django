# Agent panel data

What this package sends the shared frontend's agent panel beyond the ticket
pages' required props. The contract is ADR
[2026-11-05-agent-panel-data](https://github.com/escalated-dev/escalated-developer-context/blob/main/decisions/2026-11-05-agent-panel-data.md)
in escalated-developer-context; escalated-laravel is the reference
implementation. Everything here is optional: an older frontend ignores it.

Run `python manage.py migrate` for migration `0039_agent_panel_data`. The
shared props below come from `escalated.middleware.EscalatedInertiaShareMiddleware`.

## The agent's own status

| Route | Name | Body | Answer |
|---|---|---|---|
| `PUT` or `POST {prefix}/agent/status/` | `escalated.agent.status` | `{ "status": "online" \| "away" \| "offline" }` | `{ "agent_status": "away" }` (JSON); back (Inertia visit); 422 for any other value |

The status is `AgentProfile.chat_status`, the field live-chat routing reads.
The existing `POST {prefix}/agent/chat/status/` still writes it and now also
answers `agent_status`. Agents share `escalated.agent_status` (`offline` until
set) and `escalated.agent_statuses`. No signal is sent.

## Knowledge-base search

`GET {prefix}/agent/kb/search/?q=` (`escalated.agent.kb.search`, `kb.view`
under roles & permissions): `q` 2 to 200 characters, `limit` 1 to 20 (default
10), otherwise 422. Answers `{ data: [{ id, title, excerpt, url, category, updated_at }] }`
for published articles; `url` is the absolute customer knowledge-base URL.
Matching is Django's `icontains` on title and body (case-insensitive, `%` and
`_` literal), title matches first, then the most recently updated. 404 while
the knowledge base is off.

## Unread tickets

- `Ticket.last_customer_activity_at` is set when a ticket is created (not
  while importing) and on public replies from the requester, a guest (no
  author) or a user who is not staff. Agents' replies, notes, system replies
  and replies a workflow or automation writes never move it.
- `TicketRead` (`escalated_ticket_reads`: `user`, `ticket`, `last_read_at`);
  a null `last_read_at` means marked unread. Rows go with the ticket.
- Opening `escalated.agent.tickets.show` marks the ticket read.
- `POST {prefix}/agent/tickets/{ticket}/read/` and `/unread/`
  (`escalated.agent.tickets.read` / `.unread`, `ticket.view`) answer
  `{ is_unread }` or go back; the agent bulk route takes `mark_read` and
  `mark_unread`.
- `is_unread` on TicketIndex rows and the TicketShow ticket; `inbox.unread`
  (`{ mine, unassigned, all }`).

## Customer online status

`requester_online` and `requester_last_seen_at` on TicketIndex rows and the
TicketShow ticket, from one query per page, never on customer, guest or widget
responses. The customer is the requester, else the ticket's contact, else the
ticket itself. Last-seen (`CustomerPresence`) is recorded by the customer
ticket views (staff skipped), the widget chat (start and every token request)
and the widget ticket status lookup, at most once per customer every 30
seconds by a conditional `UPDATE`. Online means within
`ESCALATED["PRESENCE_ONLINE_WINDOW_SECONDS"]` (env
`ESCALATED_PRESENCE_ONLINE_WINDOW`, default 120).

## Notifications

`AgentNotification` (`escalated_notifications`) holds the agents' in-app
notifications; `ESCALATED["AGENT_NOTIFICATIONS"] = False` turns the feed off
(routes 404, no shared prop).

| `type` | Sent to | When |
|---|---|---|
| `ticket_assigned` | the assignee | someone else assigns them a ticket (self-assignment sends nothing, email included) |
| `ticket_reply` | the assignee and followers | a customer-side public reply or chat message |
| `mention` | the mentioned agent | an @mention in an agent's reply or internal note (also emailed while `email` is a notification channel) |
| `sla_warning` / `sla_breached` | the assignee | the `sla_warning` / `sla_breached` signals |
| `chat_transferred` | the receiving agent | a chat is transferred to them by someone else |

@mentions follow escalated-laravel: `@{Full Name}` (what the composer's picker
inserts) and `@name` match an active staff user (agent or admin) by full name,
username or email, ignoring case. Each creates a `Mention` row. A customer's
reply mentions nobody, and nobody is notified of their own mention. The picker
searches at `GET {prefix}/admin/agents/search/?q=` (`escalated.admin.agents.search`,
admin gate, `ticket.view`): up to 10 `{ id, name, email }`.

| Route | Name | Answer |
|---|---|---|
| `GET {prefix}/agent/notifications/` | `escalated.agent.notifications.index` | `{ data, meta: { current_page, last_page, per_page, total }, unread_count }`; `?page`, `?per_page` (20, max 50), `?unread=1` |
| `POST {prefix}/agent/notifications/{id}/read/` | `escalated.agent.notifications.read` | `{ unread_count }`; 404 for someone else's |
| `POST {prefix}/agent/notifications/read-all/` | `escalated.agent.notifications.read-all` | `{ unread_count: 0 }` |

Items are `{ id, type, title, body, ticket, url, created_at, read_at }`;
titles go through `gettext`. A ticket the agent can no longer see is redacted
(`ticket`, `url`, `body` null, generic title). Agents share
`escalated.notifications.unread_count`. While broadcasting is on, each new
item is sent as `notification.created` to the channel `escalated.agents.{id}`,
which only that user may subscribe to. Mute preferences are not built.
