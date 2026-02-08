# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-02-07

### Added
- Initial release of escalated-django
- Three hosting modes: self-hosted, synced, cloud
- Ticket model with full lifecycle management (open, in-progress, resolved, closed, etc.)
- Reply and internal notes system
- Department management with agent assignment
- SLA policy enforcement with business hours support
- Escalation rules engine with condition-based triggers
- Tag system for ticket categorization
- Canned responses for agents
- Ticket activity audit trail
- Attachment support with GenericForeignKey
- Inertia.js + Vue 3 views for customer, agent, and admin interfaces
- Django signals for all ticket lifecycle events
- Management commands: check_sla, evaluate_escalations, close_resolved, purge_activities
- Email notification templates
- Middleware for agent and admin access control
- Comprehensive test suite with factory_boy fixtures
