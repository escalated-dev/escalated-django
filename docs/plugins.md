# Plugin Authoring Guide

Escalated supports a flexible plugin system that allows you to extend functionality without modifying core code. Plugins can hook into system events, modify data, add UI components, and integrate with external services.

## Plugin Structure

Every plugin requires two files:

1. **`plugin.json`** - Plugin manifest containing metadata
2. **`plugin.py`** - Main Python module with plugin logic

### Minimal Example

**plugin.json:**
```json
{
  "name": "My Plugin",
  "slug": "my-plugin",
  "version": "1.0.0",
  "description": "A simple plugin",
  "author": "Your Name",
  "main_file": "plugin.py"
}
```

**plugin.py:**
```python
from escalated.hooks import add_action

def on_ticket_created(ticket):
    print(f"New ticket created: {ticket.reference}")

add_action("ticket_created", on_ticket_created)
```

## Manifest Schema

The `plugin.json` file supports the following fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Human-readable plugin name |
| `slug` | string | Yes | Unique identifier (lowercase, hyphens) |
| `version` | string | Yes | Semantic version (e.g., "1.0.0") |
| `description` | string | Yes | Brief description of functionality |
| `author` | string | Yes | Author name or organization |
| `main_file` | string | No | Entry point file (defaults to `plugin.py`) |
| `requires` | object | No | Minimum version requirements |
| `requires.escalated` | string | No | Minimum Escalated version |
| `requires.python` | string | No | Minimum Python version |

### Example with Requirements

```json
{
  "name": "Advanced Plugin",
  "slug": "advanced-plugin",
  "version": "2.1.0",
  "description": "Advanced features",
  "author": "Acme Corp",
  "main_file": "plugin.py",
  "requires": {
    "escalated": "1.0.0",
    "python": "3.9"
  }
}
```

## Hook System

Escalated uses an event-driven hook system with two types: **actions** and **filters**.

### Actions

Actions allow you to execute code when specific events occur.

```python
from escalated.hooks import add_action, do_action, has_action, remove_action

# Register an action
add_action('ticket_created', callback, priority=10)

# Trigger an action
do_action('ticket_created', ticket, user)

# Check if action exists
if has_action('ticket_created'):
    pass

# Remove an action
remove_action('ticket_created', callback)
```

**Using the decorator:**

```python
from escalated.hooks import on_action

@on_action('ticket_created', priority=10)
def handle_ticket_created(ticket, user):
    # Your logic here
    pass
```

### Filters

Filters allow you to modify data as it passes through the system.

```python
from escalated.hooks import add_filter, apply_filters, has_filter, remove_filter

# Register a filter
add_filter('ticket_data', callback, priority=10)

# Apply filters
data = apply_filters('ticket_data', data, ticket)

# Check if filter exists
if has_filter('ticket_data'):
    pass

# Remove a filter
remove_filter('ticket_data', callback)
```

**Using the decorator:**

```python
from escalated.hooks import on_filter

@on_filter('ticket_data', priority=10)
def modify_ticket_data(data, ticket):
    data['custom_field'] = 'value'
    return data
```

### Priority

Both actions and filters support priority ordering (default: 10). Lower numbers run first.

```python
add_action('ticket_created', early_handler, priority=5)
add_action('ticket_created', late_handler, priority=20)
```

## Available Hooks

### Ticket Hooks

**Actions:**
- `ticket_created` (ticket, user)
- `ticket_updated` (ticket, user, changes)
- `ticket_assigned` (ticket, agent)
- `ticket_status_changed` (ticket, old_status, new_status)
- `ticket_deleted` (ticket_id)

**Filters:**
- `ticket_data` (data, ticket) - Modify ticket data before save
- `ticket_list_query` (queryset) - Modify ticket list queries

### User Hooks

**Actions:**
- `user_created` (user)
- `user_login` (user)
- `user_logout` (user)

**Filters:**
- `user_permissions` (permissions, user) - Modify user permissions

### Comment Hooks

**Actions:**
- `comment_created` (comment, ticket)
- `comment_updated` (comment)

**Filters:**
- `comment_content` (content, comment) - Modify comment content

### Plugin Lifecycle Hooks

**Actions:**
- `plugin_loaded` (slug, manifest)
- `plugin_activated` (slug)
- `plugin_activated_{slug}` - Specific to your plugin
- `plugin_deactivated` (slug)
- `plugin_deactivated_{slug}` - Specific to your plugin
- `plugin_uninstalling` (slug)
- `plugin_uninstalling_{slug}` - Specific to your plugin

## UI Integration

Plugins can extend the UI by registering menu items, dashboard widgets, and page components.

### Menu Items

```python
from escalated.plugin_ui_service import register_menu_item

register_menu_item({
    "label": "Billing",
    "url": "/support/admin/billing",
    "icon": "credit-card",
    "section": "admin",  # 'admin', 'agent', or 'customer'
    "priority": 50
})
```

### Dashboard Widgets

```python
from escalated.plugin_ui_service import register_dashboard_widget

register_dashboard_widget({
    "id": "billing-summary",
    "label": "Billing Summary",
    "component": "BillingSummaryWidget",
    "section": "agent",  # 'admin', 'agent', or 'customer'
    "priority": 10
})
```

### Page Components

```python
from escalated.plugin_ui_service import add_page_component

add_page_component("ticket-detail", "sidebar", {
    "component": "BillingInfo",
    "props": {
        "show_total": True
    },
    "priority": 10
})
```

**Available pages:**
- `ticket-detail` - Ticket detail page
- `dashboard` - Main dashboard
- `user-profile` - User profile page

**Available sections:**
- `header` - Page header area
- `sidebar` - Right sidebar
- `footer` - Page footer
- `tabs` - Tab navigation

## Full Example: Slack Notifier

A complete plugin that sends Slack notifications when tickets are created.

**plugin.json:**
```json
{
  "name": "Slack Notifier",
  "slug": "slack-notifier",
  "version": "1.0.0",
  "description": "Send Slack notifications for ticket events",
  "author": "Your Company",
  "main_file": "plugin.py",
  "requires": {
    "escalated": "1.0.0",
    "python": "3.8"
  }
}
```

**plugin.py:**
```python
import logging
import requests
from django.conf import settings
from escalated.hooks import add_action

logger = logging.getLogger(__name__)

def on_activate():
    """Called when plugin is activated"""
    logger.info("Slack Notifier plugin activated")

def on_ticket_created(ticket):
    """Send Slack notification when a ticket is created"""
    webhook_url = getattr(settings, "SLACK_WEBHOOK_URL", None)
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not configured")
        return

    try:
        response = requests.post(webhook_url, json={
            "text": f"New ticket *{ticket.reference}*: {ticket.subject}",
            "attachments": [{
                "color": "good",
                "fields": [
                    {"title": "Priority", "value": ticket.priority, "short": True},
                    {"title": "Status", "value": ticket.status, "short": True}
                ]
            }]
        }, timeout=5)
        response.raise_for_status()
        logger.info(f"Slack notification sent for ticket {ticket.reference}")
    except requests.RequestException as e:
        logger.error(f"Failed to send Slack notification: {e}")

def on_uninstall():
    """Called when plugin is being uninstalled"""
    logger.info("Slack Notifier plugin uninstalled")

# Register hooks
add_action("plugin_activated_slack-notifier", on_activate)
add_action("ticket_created", on_ticket_created)
add_action("plugin_uninstalling_slack-notifier", on_uninstall)
```

## Distribution Methods

### ZIP Upload (Local Plugins)

1. Create a directory with `plugin.json` and `plugin.py`
2. ZIP the contents (not the parent folder)
3. Upload through Admin → Plugins → Upload Plugin
4. Plugin is installed to `plugins/escalated/{slug}/`

**Directory structure inside ZIP:**
```
plugin.json
plugin.py
requirements.txt (optional)
```

### pip Packages

Plugins can be distributed as pip packages. Any package containing a `plugin.json` file in its distribution files will be auto-detected.

**Package structure:**
```
my-plugin/
├── pyproject.toml
├── plugin.json
├── plugin.py
└── README.md
```

**pyproject.toml:**
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "escalated-billing"
version = "1.0.0"
description = "Billing plugin for Escalated"
authors = [{name = "Your Name", email = "you@example.com"}]
dependencies = [
    "django>=4.2",
    "requests>=2.31.0"
]
requires-python = ">=3.8"

[tool.setuptools]
packages = []

[tool.setuptools.package-data]
"*" = ["plugin.json", "plugin.py"]
```

**plugin.json:**
```json
{
  "name": "Billing Plugin",
  "slug": "escalated-billing",
  "version": "1.0.0",
  "description": "Add billing features to Escalated",
  "author": "Your Name",
  "main_file": "plugin.py"
}
```

**Installation:**
```bash
pip install escalated-billing
```

**Discovery:** Escalated uses `importlib.metadata` to discover plugins in installed packages. pip-installed plugins:
- Show a **composer** badge in the UI (indicates package manager installation)
- Cannot be deleted from the Admin UI
- Must be uninstalled via `pip uninstall {package-name}`

**Slug naming:** The plugin slug is derived from the package name. For example:
- Package `escalated-billing` → slug `escalated-billing`
- Package `my_custom_plugin` → slug `my_custom_plugin`

## Best Practices

### Keep plugin.py Lightweight

The main plugin file is loaded on every request. Keep initialization fast:

```python
# Good: Lazy imports
def on_ticket_created(ticket):
    from .heavy_module import process_ticket
    process_ticket(ticket)

# Bad: Heavy imports at module level
import heavy_module
import another_heavy_module
```

### Use Activation Hooks for Setup

Run migrations, create database tables, or register settings during activation:

```python
from django.core.management import call_command
from escalated.hooks import add_action

def on_activate():
    # Run migrations
    call_command('migrate', 'my_plugin')

    # Initialize settings
    from .models import PluginSettings
    PluginSettings.objects.get_or_create(
        key='default_config',
        defaults={'value': '{}'}
    )

add_action("plugin_activated_my-plugin", on_activate)
```

### Use Uninstall Hooks for Cleanup

Clean up resources when the plugin is uninstalled:

```python
def on_uninstall():
    # Remove plugin data
    from .models import PluginData
    PluginData.objects.all().delete()

    # Cancel scheduled tasks
    from django_celery_beat.models import PeriodicTask
    PeriodicTask.objects.filter(name__startswith='my-plugin').delete()

add_action("plugin_uninstalling_my-plugin", on_uninstall)
```

### Namespace Your Hooks

Prefix custom hooks with your plugin slug to avoid conflicts:

```python
# Good
do_action('billing_invoice_created', invoice)
add_filter('billing_tax_rate', tax_rate, invoice)

# Bad
do_action('invoice_created', invoice)  # Too generic
```

### Handle Errors Gracefully

Don't let plugin errors break core functionality:

```python
import logging

logger = logging.getLogger(__name__)

def on_ticket_created(ticket):
    try:
        # Plugin logic
        send_notification(ticket)
    except Exception as e:
        logger.error(f"Plugin error: {e}", exc_info=True)
        # Don't re-raise - let core continue
```

### Test Locally First

Test plugins by placing them in `plugins/escalated/` before packaging:

```
plugins/
└── escalated/
    └── my-plugin/
        ├── plugin.json
        └── plugin.py
```

Escalated will auto-discover and load the plugin. Use Django's development server for testing:

```bash
python manage.py runserver
```

### Version Your Plugins

Use semantic versioning and update the version in `plugin.json`:

- **Major** (1.0.0 → 2.0.0): Breaking changes
- **Minor** (1.0.0 → 1.1.0): New features, backwards compatible
- **Patch** (1.0.0 → 1.0.1): Bug fixes

### Leverage the PyPI Ecosystem

pip plugins benefit from the Python ecosystem:

- **Distribution**: Publish to PyPI for easy installation
- **Dependencies**: Declare dependencies in `pyproject.toml`
- **Versioning**: Use pip's version resolution
- **Updates**: Users can upgrade with `pip install --upgrade`

Example with dependencies:

```toml
[project]
dependencies = [
    "django>=4.2",
    "requests>=2.31.0",
    "celery>=5.3.0",
    "stripe>=7.0.0"
]
```

## Debugging

Enable debug logging to troubleshoot plugin issues:

**settings.py:**
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'escalated.plugins': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

Common issues:

1. **Plugin not loading**: Check `plugin.json` syntax and file permissions
2. **Hooks not firing**: Verify hook names match exactly (case-sensitive)
3. **Import errors**: Ensure all dependencies are installed
4. **pip plugin not detected**: Verify `plugin.json` is included in package data

## Next Steps

- Review the [Plugin API Reference](api-reference.md)
- Explore [example plugins](https://github.com/escalated/plugins)
- Join the [community forum](https://community.escalated.dev) for support
