# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

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

### Upgrade notes
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
