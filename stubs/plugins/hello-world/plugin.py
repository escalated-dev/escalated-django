"""
Hello World Plugin for Escalated
=================================

This plugin does nothing particularly useful -- it exists to show you how
plugins work and to give you something to delete when you feel productive.

It demonstrates:
- How to use action hooks and filter hooks
- How to handle lifecycle events (activate, deactivate, uninstall)
- How to register UI components (menus, widgets, page slots)
- How plugins integrate with Escalated

Delete it whenever you want -- it will not be offended.
"""

import logging

from escalated.hooks import add_action, add_filter
from escalated.plugin_ui_service import add_page_component, register_menu_item

logger = logging.getLogger("escalated.plugins.hello-world")


# ===========================================================================
# LIFECYCLE HOOKS (completely optional)
# ===========================================================================


def on_activated():
    """Runs when the plugin is activated."""
    logger.info("Hello World plugin was activated! Time to do... nothing!")
    # This is where you would typically:
    #   - Run database migrations for plugin-specific tables
    #   - Set up default options / settings
    #   - Initialize plugin data


def on_deactivated():
    """Runs when the plugin is deactivated."""
    logger.info("Hello World plugin was deactivated. We had a good run!")
    # This is where you would typically:
    #   - Clean up temporary data
    #   - Clear caches
    #   - Disable scheduled tasks


def on_uninstalling():
    """Runs when the plugin is being deleted."""
    logger.info("Hello World plugin is being deleted. Goodbye!")
    # This is where you would typically:
    #   - Drop database tables created by the plugin
    #   - Remove all plugin data
    #   - Clean up any files the plugin created


add_action("plugin_activated_hello-world", on_activated)
add_action("plugin_deactivated_hello-world", on_deactivated)
add_action("plugin_uninstalling_hello-world", on_uninstalling)


# ===========================================================================
# REGULAR PLUGIN CODE
# ===========================================================================


def on_plugin_loaded(slug, manifest):
    """Say hello when we are loaded."""
    if slug != "hello-world":
        return

    logger.info(
        "Hello World! The plugin is loaded (v%s). But hey, at least I exist!",
        manifest.get("version", "unknown"),
    )

    # Register a component to appear on the agent dashboard header slot
    add_page_component("dashboard", "header", {
        "component": "HelloWorldBanner",
        "plugin": "hello-world",
        "position": 1,
    })


add_action("plugin_loaded", on_plugin_loaded)


# ===========================================================================
# EXAMPLES (all commented out -- uncomment to try!)
# ===========================================================================

# Example 1: Log when tickets are created
# def log_ticket_created(ticket, user):
#     logger.info("Hello World says: A ticket was born! %s", ticket.reference)
#
# add_action('ticket_created', log_ticket_created, priority=10)


# Example 2: Add a prefix to ticket subjects
# def prefix_ticket_subject(subject, ticket):
#     return f"[HW] {subject}"
#
# add_filter('ticket_subject', prefix_ticket_subject, priority=10)


# Example 3: Track dashboard views
# def on_dashboard_viewed(user):
#     logger.info("Hello World: Someone is looking at the dashboard! User: %s", user)
#
# add_action('dashboard_viewed', on_dashboard_viewed)


# Example 4: Add a custom menu item
# register_menu_item({
#     'label': 'Hello World',
#     'url': '/support/admin/',  # Just link to admin for now
#     'icon': 'hand-wave',
#     'position': 999,
# })


# Example 5: Add custom data to dashboard stats
# def enrich_dashboard_stats(stats, user):
#     stats['hello_world_counter'] = 42
#     return stats
#
# add_filter('dashboard_stats_data', enrich_dashboard_stats, priority=10)


# Example 6: Inject a widget into the ticket detail sidebar
# add_page_component('ticket.show', 'sidebar', {
#     'component': 'HelloWorldWidget',
#     'data': {'message': 'Hello from plugin!'},
#     'position': 999,
# })


# Example 7: Modify the ticket list queryset (show only high-priority tickets)
# def filter_high_priority(queryset, request):
#     return queryset.filter(priority='high')
#
# add_filter('ticket_list_query', filter_high_priority, priority=10)
