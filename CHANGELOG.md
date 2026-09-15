# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

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
