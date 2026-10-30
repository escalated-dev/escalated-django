# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Upgrading
- **`ctx.replies.create`, `ctx.tickets.create`, `ctx.tickets.update`, `ctx.contacts.create` and `ctx.tags.create` only accept the plugin contract's fields** (plugin contract, The plugin context). They passed the plugin's data straight to `objects.create(**data)` / `setattr`, so a plugin could set a reply's author or flags, a ticket's requester, assignee or SLA fields, or create a host user with `is_superuser`/`is_staff`. Any other key is now a `ValueError` naming it. Replies: `ticket_id` (an existing ticket), `body`, `is_internal` (true makes a note); the author is the acting user, or nobody. Tickets: `subject`/`title`, `body`/`description`, `priority`, `status`, `department_id`, `ticket_type`, `metadata`, and on create `channel` (default `api`) and `contact_id` or `requester_email`/`requester_name` (a contact, found or created, also set as the guest name and email); never a requester, assignee, reference or SLA field. Unknown choices, departments and contacts are errors. Contacts: `name`, `email` (the user's username is the email when the user model has one, and `name` goes to `name` or `first_name`). Tags: `name`, `slug` (from the name when absent), `color`. Plugins that sent other keys must drop them.
- **Single sign-on is an install-level switch, off by default**
  (`ESCALATED["ACCESS"]["sso"]`, env `ESCALATED_SSO`; ADR
  2026-10-29-configurable-access-features). Nothing ever signed anyone in
  through SSO, so off is how every install already behaved; while it is off
  Admin > Settings > SSO and every `/support/sso/*` route answer 404. To turn
  it on: `python manage.py migrate escalated` (0038), give the IdP the
  endpoints from the SSO page, make sure a SAML install has the IdP
  certificate, decide on `ESCALATED["SSO"]["create_users"]` and
  `["sync_roles"]`, then set the switch. See `docs/access-control.md`.
- `escalated.services.sso_service.SsoService` is rewritten on `signxml`,
  `Authlib` and `PyJWT` (new dependencies): `validate_saml_assertion` and
  `validate_jwt_token` are replaced by `validate_saml_response` and
  `validate_jwt`, which check far more (see below). The SSO settings page now
  validates the fields each provider needs and lists the endpoints for the IdP.
- **Two-factor authentication is now an install-level switch, off by default**
  (`ESCALATED["ACCESS"]["two_factor"]`, env `ESCALATED_TWO_FACTOR`; ADR
  2026-10-29-configurable-access-features). Nothing ever asked for the code, so
  off is how every install already behaved; while it is off the enrolment
  screen answers 404. Run `python manage.py migrate escalated` (0037 adds
  `last_used_step` and stores the secret and recovery codes sealed), then set
  the switch. Users who enrolled before are challenged from their next visit.
  Set `ESCALATED_TWO_FACTOR_REQUIRED=true` (or the setting) only after telling
  staff. See `docs/access-control.md`.
- The enrolment endpoints (`admin/settings/two-factor/setup|confirm|disable/`)
  now answer the shared page with a redirect and flash, and JSON to API
  clients (`Accept: application/json`), as escalated-laravel does; they were
  JSON only, and admin only.
- New dependency: `pyotp` (TOTP); the hand-rolled HMAC is gone.
- **Roles & permissions is now an install-level switch, off by default**
  (`ESCALATED["ACCESS"]["roles_permissions"]`, env
  `ESCALATED_ROLES_PERMISSIONS`; ADR 2026-10-29-configurable-access-features).
  Roles were stored but only the newsletter screens checked them, so off is how
  almost every install already behaved. While it is off the roles screens
  (`/support/admin/roles/*`) answer 404, and the newsletter screens and plugin
  item `permission`s no longer check roles (the admin check decides). Installs
  that relied on those must turn the switch on. To enforce roles: run
  `python manage.py seed_permissions`, give every staff user a role
  (`python manage.py assign_role you@example.com admin`), then turn the switch
  on. An admin without a role is refused everywhere but their own two-factor
  screen. See `docs/access-control.md`.
- The shared `escalated.permissions` prop is `['*']` for staff while the switch
  is off, and `escalated.features` carries `roles_permissions`, `two_factor`
  and `sso`.
- With SDK plugins on (`ESCALATED['SDK_ENABLED']`), run
  `python manage.py escalated_plugin_cron` every minute (cron, Celery Beat,
  django-crontab) so SDK plugins' `cron` schedules run. Without it they never
  run; nothing else changes.
- Run `python manage.py migrate escalated`. The `knowledge_base_public`
  setting now defaults **on**, as in escalated-laravel, so a new install
  serves its knowledge base (customer pages and widget articles) to guests.
  Migration `0036_knowledge_base_public_default_on` keeps existing installs
  as they were: if the install already has Escalated data (any ticket,
  department, article, article category or chat session, or `0001_initial`
  applied more than an hour earlier) and no stored `knowledge_base_public`,
  it stores `0`, so the knowledge base stays private. A value an admin already
  saved is left alone. To open the knowledge base to guests afterwards, turn
  on "public knowledge base" in the admin Settings page.
- **Plugin UI extensions are shared as `escalated.plugins`** (`menuItems`,
  `pageComponents`, `dashboardWidgets`), the shape the shared frontend reads.
  Before, nothing was shared, so plugin menus, widgets and slots never
  appeared, and `EscalatedInertiaShareMiddleware` called inertia-django's
  `share()` with positional arguments, which it refuses. Admin menu items go
  to admins only, items whose permission the viewer lacks are left out, and
  SDK plugins' `widgets` and `components` are included. `{}` when there is
  nothing to show.
- **Plugins receive the canonical domain events.** `ticket.created`,
  `reply.created`, `note.created`, `ticket.status_changed` and the rest of
  the event vocabulary go, once the change commits, to Python plugins
  (`add_action("ticket.created", lambda payload: ...)`) and SDK plugins, with
  the plugin contract's payload: the ticket flat and under `ticket`, plus the
  event's extras; replies flat plus `reply` and `ticket`. SDK plugins used to
  get only ten of them, with `ticket_id` instead of the ticket. The Python hook
  names (`ticket_created`, ...) still fire for Python plugins. A failing
  plugin is logged and never fails the change.
- **`ctx.tickets.query` and `ctx.replies.query` only accept the plugin
  contract's filter keys.** Tickets: `id`, `reference`, `status`, `priority`,
  `channel`, `ticket_type`, `department_id`, `requester_id`, `contact_id`,
  `assigned_to`. Replies: `ticket_id`, `is_internal`, `type`. Any other key
  (including Django lookups such as `pk__gt` or `assigned_to__email`), or a
  non-scalar value, raises instead of reaching `objects.filter()`. Results are
  capped at 500 rows.

### Added
- **Admin > Users roles picker.** While roles & permissions is on, the users
  screen sends `roles` (`{id, name, slug}`, by name) and each user's role slugs,
  and `PUT C:/Program Files/Git/support/admin/users/<id>/roles/` (`{role_ids: [...]}`, needs `role.manage`) replaces a user's
  roles, as escalated-laravel's `escalated.admin.users.roles`. 404 while the
  switch is off.
- **Sign-in through SSO when switched on**, with the provider chosen in Admin >
  Settings > SSO. SAML checks the assertion signature against the configured
  certificate, Issuer, Audience, Destination/Recipient, validity windows,
  InResponseTo against requests issued in the last 10 minutes, and replay;
  OAuth uses a session-bound state and PKCE; JWT pins the algorithm and
  requires `exp`, `aud` and a single-use `jti`. Users are matched by email,
  created only with `create_users`, and given the asserted role only with
  roles on and `sync_roles`.
- **Two-factor authentication is enforced when switched on.** A staff user
  with a confirmed enrolment must pass `Auth/TwoFactorChallenge`
  (`/support/two-factor/challenge/`; TOTP code or single-use recovery code;
  replayed codes refused; 5 attempts per minute) in their session before any
  admin or agent view; JSON requests get `403 {two_factor_required: true}`.
  Enrolment is open to agents as well as admins. Admins can require enrolment
  (`ESCALATED["TWO_FACTOR"]["REQUIRED"]` or the `two_factor_required`
  setting), and `python manage.py reset_two_factor <user>` clears a lost
  device. Pages get `escalated.two_factor_required`.
- **Roles & permissions are enforced when switched on.** Every admin, agent and
  staff API view needs its permission from the user's Escalated roles as well
  as the admin or agent check (map in `escalated/access.py`; unmapped staff URLs
  are refused and a test checks every one is mapped). Status changes to
  `resolved`/`closed`/`reopened` also need `ticket.close`, bulk actions need
  each action's permission, internal API replies need `reply.create_internal`,
  and API tokens are checked as their owner. Failing answers 403.
- `python manage.py assign_role <user> <role>`.
- **SDK plugin cron schedules run.** `python manage.py escalated_plugin_cron`
  (every minute; `--at` picks the minute) sends `cron {plugin, schedule}` to
  the plugin runtime for each schedule in a plugin's manifest `cronSchedules`
  that is due that minute: five-field expressions in UTC (or `@hourly`,
  `@daily`, ...). Each runs as no user within 30 s; a failing schedule is
  logged and never stops the others, and one that cannot be read is logged
  and skipped. As with actions, every SDK plugin the runtime loaded takes part.
- **SDK widget badges.** An SDK widget with a `badge` function (manifest
  `hasBadge: true`) carries `badge` in `escalated.plugins.dashboardWidgets`:
  the plugin's answer to `badge {plugin, component}`, asked as the viewer
  (`ctx.currentUser` is the signed-in user during that call) within 5 s; a
  number or a string, `null` when it fails. Widgets without one carry no
  `badge` key.

### Changed
- `knowledge_base_public` defaults on for new installs (was off), and the
  admin Settings page shows it on when nothing is stored.

### Security
- Plugin ticket and reply queries passed the filter to `objects.filter()`, so
  an SDK plugin could filter on any field or follow relations (such as the
  assignee's password hash). Keys are now whitelisted.
- `ctx.emit` drops hook names that would impersonate a canonical event, a
  legacy alias of one, or a plugin lifecycle action.

## [0.7.9] - 2026-10-28

### Upgrading
- Clients of `POST widget/chat/start/` that checked for `200`, or for `400` on
  bad input, should accept `201` and `422`. The answer keeps every field it had
  (`session_id` included), so code reading those fields needs no change.
- Run `python manage.py migrate escalated`: migration `0035_chat_token_expiry`
  adds a nullable `ChatSession.customer_token_expires_at`. Chats already in
  progress keep working: the next widget request with their token stores the
  token's hash in place of the plain value and gives it a full lifetime.
- Widget chat tokens now expire `ESCALATED["GUEST_ACCESS"]["TTL_MINUTES"]`
  after the chat starts (default 1440, clamped to 5 minutes .. 7 days), as in
  escalated-laravel. After that every chat route answers 404 and the visitor
  starts a new chat.
- `ChatSession.customer_session_id` now holds the token's SHA-256. Code that
  started a chat through `ChatSessionService.start_chat` reads the token once
  from `session.visitor_token`. Agent chat payloads no longer carry the
  visitor's token.

### Added
- **Mobile guest ticket routes.** With `API_ENABLED`, the REST API now serves
  `POST <API_PREFIX>/mobile/guest/tickets`,
  `GET <API_PREFIX>/mobile/guest/tickets/<grant>` and
  `POST <API_PREFIX>/mobile/guest/tickets/<grant>/replies` beside the existing
  mobile `verification` and `lookup`, per the shared contract
  (escalated-developer-context `domain-model/mobile-guest-api.md`). They reuse
  the emailed codes, expiring grants, guest identity policy, attachment links
  and per-IP guest budgets of the browser and widget routes, so a grant from
  any surface opens the others; a bad or expired grant is a 404. See
  docs/guest-access.md.
- **`GUEST_RATE_LIMIT["REQUESTS_PER_MINUTE"]`** (default 60): every mobile
  guest request counts against it, on top of the ticket or reply bucket.

### Changed
- **The older `POST widget/chat/start/` (trailing slash) now answers exactly
  like the widget's `POST widget/chat/start`**, as escalated-laravel does: it
  is served by the same view and returns `201` with `id` and `session_id`
  (both the chat token), `expires_at`, `ticket_reference`, `status`,
  `queue_position`, `agent_name`, `agent` and `messages`. Validation failures
  and a bad verification code are now `422` with list-valued `errors` (were
  `400` with string values).
- Guest answers now send `Cache-Control: private, no-store` (was
  `no-store, private`; same meaning). The five mobile guest routes send it and
  `Referrer-Policy: no-referrer` on every answer, errors included.

### Security
- **Widget chat tokens are stored hashed and expire.** The token returned by
  `chat/start` (`id`, `session_id`) was stored in plain text and never expired.
  Only its SHA-256 is stored now, the start answers carry `expires_at`, and an
  unknown or expired token is a 404 on `chat/<token>/...` and on the older
  body-`session_id` routes. The guest's websocket chat check uses the same
  lookup.

## [0.7.8] - 2026-10-22

### Added
- **`escalated.middleware.EscalatedCsrfMiddleware`.** The shared pages send
  the CSRF token as `X-XSRF-TOKEN` (Inertia visits, read from an `XSRF-TOKEN`
  cookie) or `X-CSRF-TOKEN` (`fetch` calls such as the chat bar, reply
  composer and saved views, read from a `csrf-token` meta tag). Django's
  `CsrfViewMiddleware` reads only `X-CSRFToken` by default, so on a default
  host every such POST was refused with 403; setting
  `CSRF_HEADER_NAME`/`CSRF_COOKIE_NAME` the inertia-django way fixed Inertia
  visits but still refused the `fetch` calls. The new middleware accepts
  either header in place of `CSRF_HEADER_NAME` (only when that header is
  absent) and sets a JavaScript-readable `XSRF-TOKEN` cookie; a missing or
  wrong token is still refused. It is opt-in. Upgrade: add it to
  `MIDDLEWARE` directly after `django.middleware.csrf.CsrfViewMiddleware`,
  and add `<meta name="csrf-token" content="{{ csrf_token }}">` to your
  `INERTIA_LAYOUT` template (see the README's CSRF section).

## [0.7.7] - 2026-10-22

### Fixed
- **Chat transfer reads `department_id`.** `POST
  /agent/chat/<id>/transfer/` took only `agent_id`, so the shared ticket
  view's Transfer menu (which offers departments and posts
  `{"department_id"}`) was refused with 400. It now reads `agent_id` and/or
  `department_id`, as escalated-laravel does: a department takes the ticket,
  and without an agent the chat goes back to the queue (unassigned, waiting)
  and routing runs again for that department. The older `{"type", "id"}` body
  is read too, and `agent_id` alone behaves as before. An unknown department
  is a 404. `chat.transferred` now carries `to_department_id`, and the
  `chat_transferred` signal sends a `to_department` keyword (receivers taking
  `**kwargs` are unaffected).

## [0.7.6] - 2026-10-22

### Added
- The basic report sub-screens, at escalated-laravel's paths: `Admin/Reports/AgentMetrics`
  (`admin/reports/agents/`), `Admin/Reports/SlaReport` (`admin/reports/sla/`) and
  `Admin/Reports/CsatReport` (`admin/reports/csat/`), with the props its
  `Admin\ReportController` passes: per-agent tickets, resolved and average
  first response and resolution hours; SLA compliance overall and per active
  policy with the latest 100 breaches; and the CSAT average, response rate,
  per-agent ratings and daily averages. They read `days` (default 30).
- `tests/test_page_name_parity.py` keeps a `NOT_YET_RENDERED` ledger of the
  shipped pages this package does not render yet.
- The customer knowledge base pages, as escalated-laravel's
  `Customer/KnowledgeBaseController`: `Customer/KnowledgeBase/Index` at `kb/`
  (published articles, newest first, 15 a page, `search` and `category`
  filters, root categories with their published article counts) and
  `Customer/KnowledgeBase/Article` at `kb/<slug>/` (counts the view, up to five
  related articles), with helpful / not helpful feedback posted to
  `kb/<slug>/feedback/` (404 when feedback is off). The knowledge base answers
  404 when `knowledge_base_enabled` is off and 403 to visitors who are not
  signed in unless `knowledge_base_public` is on. Articles shown to readers
  leave out the author.
- `Admin/Reports/AgentDetail` at `admin/reports/agent/<id>/detail/`
  (`admin_reports_agent_detail`), admins only, with the props the shared page
  declares: `period_days`, `agent {id, name, email}`, `total_tickets`,
  `resolved_tickets`, `avg_frt`, `avg_resolution`, `csat_score` (null without
  ratings), `response_percentiles {p50..p99}`, `productivity` (per day
  `{label, value, values: [public replies, resolved]}`), `workload` (tickets
  created per day), `csat_breakdown` (`N stars` counts), and `prev_*` for the
  same number of days before. It reads `days` (default 30).

### Fixed
- **The reports overview and dashboard show figures.** `Admin/Reports` was sent
  `stats`, `by_department` and `csat.breakdown` keyed 1..5, and
  `Admin/Reports/Dashboard` was sent `ticket_volume` and `{status, count}` /
  `{priority, count}` rows; the shared screens read none of those, so both
  rendered zeroes and empty charts. They now carry escalated-laravel's
  `Admin\ReportController` props and read `days` (default 30): the overview
  sends `period_days`, `total_tickets`, `resolved_tickets`,
  `avg_first_response_hours`, `sla_breach_count`, `by_status` / `by_priority`
  maps and `csat {average, total, breakdown}`; the dashboard sends
  `period_days`, `volume`, `by_status`, `by_priority` (`{label, value}` rows),
  `avg_response_hours`, `avg_resolution_hours` (from `first_response_at` and
  `resolved_at`), `sla_compliance` (from the breach flags), `csat_average`
  and `agent_performance`. `ReportingService` itself is unchanged.

## [0.7.5] - 2026-10-22

### Upgrading
- Retention settings default to `never`, so `purge_expired_data` removes
  nothing new until an admin chooses a period. When one is set, closed tickets
  past it are deleted permanently (no soft delete in this package) with their
  replies, attachments and stored files; schedule the command daily.
- A CSAT or guest-policy save with an invalid value is now rejected instead of
  being coerced to a default.
- Run the migrations (`0034_import_job_user` adds a nullable `user` column).
- `POST admin/import/<id>/run/` now queues the run instead of running it inside
  the request. `admin/import/create/` shows the Index screen.
- Saving a webhook with the secret field left blank (or not sent) now keeps
  the stored secret, because the form no longer receives it. Send
  `clear_secret: true` to remove it. The webhook pages read `has_secret`
  instead of `secret`.
- The SSO settings page posts the mask (`********`) back for a secret the
  admin did not change, and it is ignored; any other value replaces the stored
  secret, as before. The older `abc*****` mask is still recognised, here and on
  the general Settings page.

### Added
- Admin Settings sub-pages render the shared `Escalated/Admin/Settings/*`
  screens with escalated-laravel's props and validation:
  - `DataRetention` (`admin/settings/data-retention/`): retention for closed
    tickets, attachments and audit logs, the GDPR flag, and a purge preview.
  - `DatabaseConnection` (`admin/settings/database/`): read-only status of
    every `settings.DATABASES` alias (reachable, migrated, ticket count),
    marking the one `ESCALATED["DATABASE"]` routes to. Switching is refused;
    `admin/settings/database/test/` probes one alias as JSON.
  - `EmailSettings` (`admin/settings/email/`): the email channel's addresses
    and default reply address (`email_addresses`, `default_reply_address`
    settings; stored only).
- `purge_expired_data` applies the Data Retention settings.
- The admin Import wizard, on escalated-laravel's paths and props:
  `Admin/Import/Index` (`admin/import/`), `Connect`
  (`admin/import/<platform>/connect/`, with `POST .../test-connection/`
  answering `{success[, error]}`), `Mapping` (`.../mapping/`), `Review`
  (`POST .../review/`, which writes nothing), `start` (`POST .../start/`) and
  `Progress` (`admin/import/progress/<id>/`, polled through
  `admin/import/status/<id>/`, with `POST admin/import/{pause,resume,cancel}/<id>/`).
  Sources are still the adapters registered on the `import.adapters` filter;
  core ships none. Tested credentials wait in the session, encrypted, until the
  import starts, and are never sent to the browser.
- Imports run in the background: after the starting transaction commits, in a
  thread by default, or through your task queue by registering the
  `import.run_async` action and calling `escalated.services.import_runner.run_job`.
- Import jobs record the admin who started them (`ImportJob.user`).

### Changed
- `CsatSettings` and `PublicTickets` validate their input, redirect back to
  their own page with a success flash (and field errors on a rejected save),
  and `PublicTickets` also accepts PUT. CSAT `csat_delay_hours` is sent as an
  integer. Each sub-page also answers its `admin_settings_<page>_update` name.

### Fixed
- Imports wrote no tickets. Contacts failed on any user model without a `name`
  field, which includes Django's own; every ticket failed on a `requester_id`
  the ticket has no field for; a source timestamp broke the save; and an
  attachment was written to fields the model does not have. Replies then had
  no ticket to attach to.
- An imported ticket's status or priority this package does not know is now
  saved as open / medium, as escalated-laravel does, and a ticket with no
  description takes its subject.
- Import mode now also holds back SLA policy attachment and breach checks,
  escalation rules and automations, as escalated-laravel's ImportContext does.
- The Index, Mapping and Progress screens were sent props the shared pages do
  not read; they now get Laravel's.

### Security
- **Stored secrets are no longer sent to admin pages.** The SSO settings page
  received `sso_jwt_secret` in plain text, and the general Settings page, which
  sends every stored setting, carried the SSO secrets in plain text too; both
  now show `********` (an empty string when unset). The general Settings page
  also showed the first three characters of the Mailgun signing key, Postmark
  inbound token and IMAP password; they are now masked completely. Saving a
  webhook with the secret left blank silently removed the stored signing
  secret; it now keeps it, and the webhook pages get `has_secret` instead of
  `secret`. Import job pages already left credentials out; they are now built
  from an explicit field list with the last 50 errors. 2FA secrets, recovery
  codes and API token hashes were already kept out of every page; a test now
  guards all of these surfaces.

## [0.7.4] - 2026-10-21

### Upgrading
- Run the migrations (`0032_verified_guest_access`) and configure outbound
  email. Use a shared cache across workers for the code budgets.
- Existing permanent guest links (`guest/<guest_token>/`, the widget's old
  `guest_token`) stop working. Guests renew them with the lookup form (email
  code plus ticket reference). `ESCALATED["GUEST_ACCESS"]["LEGACY_TOKENS"] =
  True` keeps the old links working during a transition.
- Clients that do not send `verification_id` and `verification_code` can no
  longer create guest tickets or start widget chats. The widget's create
  responses now carry the grant (with `expires_at`) where they carried the
  permanent token.
- The new URL does not make files already in MEDIA private. Stop your web
  server or CDN from serving `MEDIA_ROOT/escalated/attachments/` publicly; see
  `docs/private-attachments.md`. Links expire, so clients that cached
  attachment URLs must refetch the ticket.
- Webhooks saved under the old names keep receiving those events, now under
  the new names in the delivery's `event` field and `X-Escalated-Event`
  header. Receivers that switch on the event name should accept the new
  names. The edit form shows (and saving stores) the canonical names.
- Stored names are read as aliases, not rewritten: `ticket.replied`,
  `internal_note.added`, `internal_note.created`, `tag.added`,
  `ticket.tagged`, `tag.removed`, `ticket.untagged`, `chat.session_started`
  and `chat.session_ended`. A workflow saved with the `ticket.replied`
  trigger is stored and shown as `reply.created` and keeps firing on replies.

### Added
- Live chat events (ADR 2026-10-21): `chat.started`, `chat.assigned`,
  `chat.transferred`, `chat.message` and `chat.ended` are now sent to
  outbound webhooks and run workflows, and the webhook form and the workflow
  builder offer them. Before this, chat events reached neither. The webhook
  payload is `{"chat": {"session_id", "ticket_id", "status", "agent_id",
  "department_id"}}`, plus `from_agent_id`/`to_agent_id`/`to_department_id`
  (always `null`; transfers are agent to agent) for a transfer,
  `reply_id`/`author_type` (`agent` or `visitor`) for a message and
  `ended_by` (`agent` or `customer`) for an end. It never carries the
  visitor's chat token (`customer_session_id`), the visitor's email or the
  message body. Workflows on chat events run against the chat's ticket. A new
  `chat_assigned` signal is sent when an agent takes a chat (accepted from the
  queue or routed at start). Webhooks and workflows saved under
  `chat.session_started` / `chat.session_ended` receive `chat.started` /
  `chat.ended`. **Upgrade:** run `python manage.py migrate escalated`
  (`0033_workflow_chat_triggers` only updates the trigger choices; no schema
  change).

### Security
- Verified guest access, as in escalated-laravel (`docs/guest-access.md`).
  Guest tickets (browser and widget), widget live chats and ticket lookup now
  need an eight-digit code emailed to the guest (10-minute expiry, five
  guesses, single use; at most 3 codes per mailbox per client IP and 10 per
  mailbox per hour). `POST verification` and `POST lookup` are served under
  `guest/`, `widget/` and `<API_PREFIX>/mobile/guest/`. New tickets get an
  expiring grant (default 24 hours, `GUEST_ACCESS["TTL_MINUTES"]`) whose nonce
  is stored only as a hash, instead of the permanent `guest_token`.
  `/widget/config` sends `guest_verification_required: true` and
  `status_lookup_enabled: true`, and `GET widget/tickets/<reference>` returns
  the ticket's status for a matching `Authorization: Bearer <grant>`.
  `Guest/Create` receives `verification_url` and `lookup_url`, and the guest
  ticket page no longer carries ticket or reply `metadata`, the requester
  record or agent emails.
- Attachments are delivered privately, as in escalated-laravel. Serialized
  attachments (`AttachmentSerializer`, `ApiAttachmentSerializer`) no longer
  carry the file's MEDIA URL. Their `url` is a signed link to the new
  `escalated:attachment_download` view (`<prefix>/attachments/<id>/`), valid
  for `ATTACHMENT_DOWNLOAD_TTL_MINUTES` (default 10). The view checks current
  ticket access: agents and admins who can view the ticket, the requester for
  attachments on the ticket and its public replies, and guests holding a link
  issued by their guest page (bound to the ticket's active guest grant, so
  renewing or revoking the grant revokes them). Internal-note attachments are only served to agents
  and admins. Responses are `Content-Disposition: attachment` with a safe
  filename, `application/octet-stream` except for a few inert types,
  `X-Content-Type-Options: nosniff` and `Cache-Control: private, no-store`.
  API clients send their Escalated bearer token with the download.

### Changed
- Webhooks use the shared event vocabulary (escalated-developer-context ADR
  2026-10-21): internal notes go out as `note.created` (was
  `internal_note.added`) and tag changes as `ticket.tag_added` /
  `ticket.tag_removed` (were `tag.added` / `tag.removed`). The admin Webhooks
  form offers only the canonical names. The names live in
  `escalated/event_names.py`.

## [0.7.3] - 2026-10-20

### Fixed
- Forms on the shared frontend post JSON (Inertia). Views now read a JSON body
  through `escalated.request_data.request_data()`, which falls back to
  `request.POST` for form posts. Saving the admin Settings page no longer
  turns off guest tickets, customer close, inbound email and the powered-by
  badge, and `widget_allowed_origins` can be saved from the UI. A JSON save
  only changes the keys it sends.
- The Settings page receives typed values and `supported_settings`, and saves
  the Support Widget settings (`widget_enabled`, `widget_color`,
  `widget_position`, `widget_greeting`, `widget_departments`), `chat_enabled`
  and the knowledge-base switches.
- Widget, guest-portal and live-chat tickets send `ticket_created`, so they
  get SLA, the created activity, notifications, the `ticket.created` webhook
  and workflows.
- Assign and unassign work on hosts with UUID user keys (activity
  `properties` use `DjangoJSONEncoder`); bulk, macro, workflow and automation
  assign convert user ids with the user model's key field instead of `int()`.
- Customer ticket, admin ticket and agent ticket screens send the props the
  shared pages read: `ticket.replies` (public replies only for customers),
  `ticket.activities`, `ticket.pinned_notes`, `ticket.satisfaction_rating`,
  `cannedResponses`; the canned-responses screen gets `responses`.
- `/widget/config` lists only the `widget_departments` and reads `widget_color`.

### Security
- The widget skips CSRF only for requests from an allowed embedding origin;
  other cross-site and same-origin posts go through the host's
  `CsrfViewMiddleware`.
- Widget article search and articles honour `knowledge_base_enabled` and
  `knowledge_base_public`.
- Widget live chat requires `widget_enabled` and the new `chat_enabled`.

### Changed
- The bundled widget is now `@escalated-dev/escalated` 0.12.3. It keeps its script settings when `embed.js` is placed in the page `<head>`, and Enter no longer picks a stale mention suggestion.
- `widget_enabled` and `chat_enabled` default to off, as in the other hosts.
  Migration `0031` keeps both on for installs that already existed.

## [0.7.2] - 2026-10-19

### Fixed
- The package can be published to PyPI again. It no longer depends on
  `escalated-locale` through a git URL, which PyPI rejects
  (`400 Can't have direct dependency`).
- Translations are bundled: the escalated-locale v0.1.8 gettext catalogues
  ship inside the package at `escalated/_central_locale/locale/`, and
  `get_central_locale_path()` falls back to them when the `escalated_locale`
  package is not installed. `pip install escalated-django[locale]` installs
  the standalone package, which still wins when present.
  `scripts/sync_central_locale.py <tag>` refreshes the bundled copy.

## [0.7.1] - 2026-10-19

### Changed
- The bundled widget is now `@escalated-dev/escalated` 0.12.2. It hides its Check Status tab when `/config` returns `status_lookup_enabled: false`.

### Security
- Removed `GET /widget/tickets/lookup/?reference=&email=`. It returned the
  ticket's `guest_token` to anyone who knew the reference and claimed the
  guest's email address. Behaviour change: the email lookup no longer exists
  (it now answers `404`); guests open their ticket from the link in their
  confirmation email.

### Fixed
- The shared widget (`@escalated-dev/escalated`) now works against this
  backend. Its paths are added without trailing slashes beside the original
  routes, which keep their shapes: `GET /widget/config` adds `color`,
  `greeting`, `position`, `departments`, `kb_enabled`, `guest_tickets_enabled`
  and `status_lookup_enabled: false`; `GET /widget/articles?q=`,
  `GET /widget/articles/<slug>` (top-level fields), `POST /widget/tickets`
  (`201` with top-level `reference`), and token-addressed chat:
  `POST /widget/chat/start` returns the session token as `id`, used by
  `GET`/`POST /widget/chat/<id>/messages`, `/typing`, `/end` and `/rate`.
  Widget tickets and chats accept `department_id` (active departments only),
  and chat start accepts an opening `message`. Chat session tokens are now
  256-bit random values.
- Compare account identities exactly on MySQL, including trailing spaces, in visibility, filters, and routing.

### Added

- **Embed the widget on other sites.** List the sites in
  `ESCALATED["WIDGET_ALLOWED_ORIGINS"]` or the `widget_allowed_origins` admin
  setting (origins such as `https://shop.example.com`, or
  `https://*.example.com` for subdomains). For those origins the widget and
  widget chat routes answer CORS preflights, add `Access-Control-Allow-Origin`
  to every response (including 400, 403 and 429), and run as an anonymous
  guest even when the browser is signed in. Other origins and same-origin
  requests are unchanged. `GET /support/widget/embed.js` serves the standalone
  bundle (`WIDGET_SERVE_SCRIPT`). Widget tickets and chats store the page's
  sanitised `metadata`, with `embedded_on` set from the request's Origin, and
  `/widget/config/` returns `accepts_metadata: true`. See
  `docs/embedding-the-widget.md`.
- Opt-in department and account ticket visibility across HTTP/API queries,
  policies, reports, bulk actions, widgets, chat and notification recipients.
- Nullable polymorphic account identities with host resolver hooks, account
  filters, and account/type conditions in routing rules.
- Optional department/type SLA targets with deterministic selection and
  unchanged deadlines when a ticket moves departments.

## [0.7.0] - 2026-10-08

### Upgrading

- **Only the requester can reply by email.** A matched message is a reply only
  when `From` is the ticket's guest email or the requester's `email`
  (case-insensitive), and it is posted as the requester. Mail from anyone else,
  an agent's address included, opens a new ticket, so agents reply in the app.
- **Set `ESCALATED["EMAIL_INBOUND_SECRET"]`.** With it set, only the signed
  Reply-To address links mail to a ticket; `In-Reply-To`, `References` and
  subject references no longer do.
- **Accepted email replies reopen resolved and closed tickets.**
- **Guest endpoints are rate-limited per client IP** (5 tickets and 10 replies
  a minute) through `ESCALATED["GUEST_RATE_LIMIT"]`. The widget ticket endpoint
  drops from 10 to 5 a minute. Behind a proxy, set `REMOTE_ADDR` from your
  trusted proxies or every guest shares one limit. Point `CACHE` at a shared
  cache when you run more than one process.

### Added
- **Per-IP rate limit on guest ticket creation and replies.** The widget and guest-form ticket
  endpoints allow 5 submissions and the guest reply endpoint 10 replies per client IP per minute,
  counted separately; over the limit the response is `429` with `Retry-After`. The reply limit is
  checked before the guest token, so wrong-token requests count. Configure with
  `ESCALATED["GUEST_RATE_LIMIT"]` (`ENABLED`, `TICKETS_PER_MINUTE`, `REPLIES_PER_MINUTE`, `CACHE`).
  The widget ticket endpoint previously allowed 10 per minute. Behind a proxy, set `REMOTE_ADDR`
  from your trusted proxies or all guests share one limit.

### Fixed
- **Inbound replies come only from the ticket's requester.** With `EMAIL_INBOUND_SECRET` set, only
  the signed Reply-To address links mail to a ticket. A matched email is a reply only when `From`
  is the ticket's guest or requester email, and it is posted as the requester; any other sender
  gets a new ticket. Accepted replies reopen resolved or closed tickets.

## [0.6.4] - 2026-09-15

### Added
- **Cloud → site webhook receiver.** `POST /support/cloud/webhook/` applies `ticket.updated` and
  `ticket.status_changed` from cloud.escalated.dev to the local ticket (matched by `reference`),
  verified with the new `HOSTED_SIGNING_SECRET` and deduplicated by `event_id`. Synced mode is
  now two-way, as it already was for the Laravel package (v1.8.4).

## [0.6.3] - 2026-09-15

### Fixed
- **Synced mode never reached the cloud.** `HostedApiClient.emit()` posted to
  `/sync/events`, a route cloud.escalated.dev does not serve, so every
  `ticket.*` / `reply.created` event from the `SyncedDriver` was a 404 that the
  driver logged and dropped. Events now go to `POST /events` with a stable
  `event_id` and timestamp so the cloud can project them and ignore
  redeliveries.

## [0.6.2] - 2026-09-13

### Fixed
- **Webhooks configured in the admin never received anything.**
  `WebhookDispatcher.dispatch()` had no caller outside the manual retry view, so
  a webhook saved on the Webhooks page got no deliveries. A new
  `escalated.webhook_handlers` module connects a receiver for every event the
  webhook form offers. Delivery runs inside the signal, as the `WEBHOOK_URL`
  delivery already did. A failure is logged and never interrupts the change
  that raised the event, and nothing is sent during an import (#76).
- **Some models only existed once the URL conf had been imported.**
  `Workflow`, `WorkflowLog`, `DelayedAction`, `Mention`, `PluginStoreRecord`
  and `EscalatedPlugin` lived in modules nothing imported at `django.setup()`.
  In a Celery worker, a shell or a management command, deleting a ticket
  failed on the `workflow_logs` foreign key, and `makemigrations` treated the
  models as deleted. The models module now imports them.
  - Migration 0029 aligns the migration state with the models. It adds the
    `ticket_type` index the model always declared, renames
    `escalated_automation_active_idx` to `escalated_auto_active_idx` (Django
    rejects index names over 30 characters), and drops the database foreign key
    from mentions to the host user table, which 0028 missed. Everything else is
    state only.
  - CI now fails when `makemigrations --check` finds drift (#79).
- **Real-time broadcasting was never connected.** `connect_signals()` was
  documented as something `AppConfig.ready()` calls, and nothing did. It is
  called at startup now, and each handler returns at once unless
  `ESCALATED_BROADCASTING_ENABLED` is set (#75).
- **Python plugins never received ticket events.** The ticket actions
  `hook_registry` documents were never fired. Every documented action with a
  matching signal now fires through `do_action()`, and SDK plugins still get
  each event once, through the bridge (#77).
- **Escalation rules changed tickets silently.** A rule that set the priority,
  assignee or department saved the ticket without sending
  `ticket_priority_changed`, `ticket_assigned` or `department_changed`, so the
  assigned agent got no email and workflows and webhooks never heard. The
  signals are sent once the ticket is saved (#78).
- **Import jobs failed on a clean install.** Import job credentials are
  encrypted with `cryptography`, which was never declared.
  `cryptography>=44.0.1` is now a dependency (#74).

## [0.6.1] - 2026-09-13

### Fixed
- **Thirty-four screens rendered blank, and six lists were always empty.** The
  views rendered page names with no component behind them in
  `@escalated-dev/escalated`, and Inertia resolves such a name to nothing rather
  than to an error, so each returned 200 and an empty panel. Twenty-two are
  renamed to the component the frontend ships, mostly `Create`/`Edit` pairs
  collapsing into one `Form` and `Admin/KB/...` becoming
  `Admin/KnowledgeBase/...`. `CustomFields/Form` now gets `field`, and the CSAT
  and SSO settings screens get `settings`, which is what they read. Tags, macros
  and canned responses are edited inline on their index screens, so a rejected
  save there landed on a blank page; each now re-renders its index with the
  errors attached. The six advanced reports stay blank: their views pass
  `{data, filters}` where the components take flat props.

  Separately, the admin, agent and customer ticket queues, the audit log, the
  knowledge-base article list and the webhook delivery log handed their
  components a bare list and a sibling `pagination` dict. The components read
  `records.data` and page through `records.links`, so all six rendered
  permanently empty, and an empty ticket queue reads as a quiet day rather than
  a fault. `paginated()` in `escalated/rendering.py` now builds the shape they
  were written against.

- **The shared workflow builder could not save a workflow, and reply workflows
  never ran.** `POST admin/workflows/` re-rendered the index and saved nothing,
  `create/` answered with a JSON 201 an Inertia form cannot consume, `PUT` and
  `DELETE` were ignored, and a workflow with no name, trigger or actions was
  saved anyway. The reply handler fired `ticket.replied`, so a `reply.created`
  workflow saved from the builder never ran.

  The views now follow escalated-developer-context
  `domain-model/workflow-admin-contract.md`. `POST` creates, and `PUT` and
  `DELETE` update and delete with a `303`; toggle, reorder (`workflow_ids`) and
  delete redirect to the index; `name`, `trigger_event` and at least one action
  are required, and errors come back as the Form's `errors` prop. The Form gets
  `workflow`, `trigger_events`, `action_types` and `operators`, and
  `trigger_events` is exactly what the handlers fire. The reply handler fires
  `reply.created`, and workflows stored under `ticket.replied` still run. The
  engine executes `insert_canned_reply`, `add_tag` gives a new tag a slug (the
  second new tag used to fail on the unique `slug`), and empty or omitted
  conditions match every ticket. The old `create/`, update and `delete/` URLs
  keep working.

### Changed
- **The test suite runs on PostgreSQL and MySQL as well as SQLite.** It had only
  ever seen SQLite, which is the one backend no host deploys on and the one that
  enforces the least: no foreign keys unless asked, no complaint about comparing
  a boolean to an integer, and its own answers for LIKE case sensitivity and
  aggregate return types.

  `tests/settings.py` reads `ESCALATED_TEST_ENGINE` (`sqlite`, `postgres` or
  `mysql`), defaulting to SQLite so running the suite locally still needs
  nothing installed. An unrecognised value raises rather than falling back,
  because a CI leg that quietly ran SQLite would report green having tested
  nothing the matrix exists for — and `tests/test_database_engine.py` asserts
  the connection is on the backend that was asked for and can actually be
  queried.

  All 831 tests pass on all three. Nothing needed fixing, which is what the
  Django ORM is for.

### Added
- **`tests/test_page_name_parity.py`**, asserting every page name this package
  renders resolves to a component. It diffs them against the manifest the
  frontend publishes, vendored at `tests/fixtures/escalated-pages.json`, and
  fails if its list of known-blank names still excuses one that has since been
  fixed, so that list can only shrink.

## [0.6.0] - 2026-09-12

### Added
- **Configurable database connection.** `ESCALATED["DATABASE"]` names the database alias Escalated's own tables live on, wired through the new `escalated.routers.EscalatedRouter`. `None` uses the project's `default` database, which is the historical behaviour; the router returns "no opinion" for everything when nothing is configured, so adding it to a project that has not set `DATABASE` changes nothing.

  `allow_migrate` keeps Escalated's tables on that database **and only there** — without the second half they would be created on the configured database and left behind on `default` too, diverging silently. Your user table is deliberately not routed: it stays wherever the project keeps it.

### Changed
- **Escalated's foreign keys to `AUTH_USER_MODEL` are now `db_constraint=False`** (migration `0028_drop_host_user_fk_constraints`). Django cannot create a foreign key across databases, so while those constraints existed the setting above could not work at all — `migrate` failed on the first user-referencing table.

  This runs on every install, including single-database ones, and **does not change Django's behaviour**: `on_delete` is implemented in Python by the deletion collector, not by a database `ON DELETE` clause, and Django never emits one. What is given up is the database's own referential check against direct SQL writes that bypass the ORM.

### Notes
- A **join** cannot span two databases. Single-object traversal (`ticket.assigned_to`) is resolved with a second query and works; a queryset that joins *through* the user model (`select_related("assigned_to")`, `filter(assigned_to__email=...)`) does not, when the two are separated. Filter on the key and load users separately.

### Added
- Central translations sourced from the `escalated-locale` PyPI package
  via `escalated.locale_paths.get_locale_paths()`; the plugin-local
  `escalated/locale/` directory remains as the override layer that wins
  over the central catalogue
- Missing admin views for automations, articles, and side-conversations
- Inertia UI optional with `UI_ENABLED` setting
- Plugin system with service layer and admin views
- Django structural alignment with Laravel
- Ticket type categorization field with filtering
- `seed_permissions` management command with default roles
- Plugin bridge for Django backend
- Import framework ported to Django backend
- `show_powered_by` setting and Inertia share middleware
- Platform parity Phases 1-5: audit logs, custom statuses, business hours, roles and permissions, custom fields, ticket linking, merging, side conversations, knowledge base, agent routing, automations, webhooks, 2FA, custom objects, reports
- Multi-language (i18n) support with EN, ES, FR, DE translations
- WordPress-style plugin/extension system
- REST API layer with token auth, rate limiting, and full ticket CRUD
- PyPI trusted publishing workflow
- GitHub Actions test pipeline

### Fixed
- Test patches updated from `render` to `render_page` after rendering refactor
- Merge conflicts between api and plugins branches resolved
- Replay protection and strengthened SES webhook verification
- 12 failing CI tests: URL namespace, factory, SLA, and status transitions
- Django settings configured via pyproject.toml for pytest

## [0.4.0] - 2026-02-09

### Added
- Bulk actions: assign, change status/priority, add tags, close, or delete multiple tickets
- Macros: reusable multi-step automations
- Ticket followers with notification support
- Satisfaction ratings (1-5 star CSAT with optional comments)
- Pinned internal notes
- Presence indicators for real-time ticket viewing
- Enhanced dashboard with CSAT metrics, resolution times, SLA breach tracking

## [0.1.9] - 2026-02-08

### Security
- Fix SSRF, XSS, auth bypass, and credential exposure vulnerabilities

## [0.1.8] - 2026-02-08

### Added
- Inbound email system with adapters
- Guest reply fixes
- Cloud driver fixes

## [0.1.7] - 2026-02-08

### Added
- Admin ticket management and configurable reference prefix
- `EscalatedSettings` model and guest ticket support
- Frontend assets moved to `@escalated-dev/escalated` npm package
- Initial release of Escalated Django app
