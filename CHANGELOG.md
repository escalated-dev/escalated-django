# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

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
