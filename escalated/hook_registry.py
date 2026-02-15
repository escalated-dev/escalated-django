"""
Central registry of all available hooks and filters in Escalated.

This module serves as **documentation** for plugin developers. Plugins can
reference this to discover what hooks are available and what arguments
each hook receives.

Usage::

    from escalated.hook_registry import HookRegistry

    # Get all documented actions
    actions = HookRegistry.get_actions()

    # Get all documented filters
    filters = HookRegistry.get_filters()

    # Get everything
    all_hooks = HookRegistry.get_all_hooks()
"""


class HookRegistry:
    """
    Catalogue of all hooks fired by the Escalated package.

    Each entry includes a human-readable description, a list of parameters
    the callback receives, and a Python example.
    """

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @staticmethod
    def get_actions():
        return {
            # ===========================================================
            # PLUGIN LIFECYCLE
            # ===========================================================
            "plugin_loaded": {
                "description": "Fired when a plugin file has been loaded.",
                "parameters": ["slug", "manifest"],
                "example": (
                    "add_action('plugin_loaded', "
                    "lambda slug, manifest: print(f'Loaded {slug}'))"
                ),
            },
            "plugin_activated": {
                "description": "Fired when any plugin is activated.",
                "parameters": ["slug"],
                "example": (
                    "add_action('plugin_activated', "
                    "lambda slug: print(f'Activated {slug}'))"
                ),
            },
            "plugin_activated_{slug}": {
                "description": (
                    "Fired when a specific plugin is activated. "
                    "Replace {slug} with the plugin's slug."
                ),
                "parameters": [],
                "example": (
                    "add_action('plugin_activated_hello-world', "
                    "lambda: print('Hello World activated!'))"
                ),
            },
            "plugin_deactivated": {
                "description": "Fired when any plugin is deactivated.",
                "parameters": ["slug"],
                "example": (
                    "add_action('plugin_deactivated', "
                    "lambda slug: print(f'Deactivated {slug}'))"
                ),
            },
            "plugin_deactivated_{slug}": {
                "description": (
                    "Fired when a specific plugin is deactivated. "
                    "Replace {slug} with the plugin's slug."
                ),
                "parameters": [],
                "example": (
                    "add_action('plugin_deactivated_hello-world', "
                    "lambda: print('Hello World deactivated!'))"
                ),
            },
            "plugin_uninstalling": {
                "description": "Fired before any plugin is deleted.",
                "parameters": ["slug"],
                "example": (
                    "add_action('plugin_uninstalling', "
                    "lambda slug: print(f'Uninstalling {slug}'))"
                ),
            },
            "plugin_uninstalling_{slug}": {
                "description": (
                    "Fired before a specific plugin is deleted. "
                    "Replace {slug} with the plugin's slug."
                ),
                "parameters": [],
                "example": (
                    "add_action('plugin_uninstalling_hello-world', "
                    "lambda: print('Hello World is being removed!'))"
                ),
            },

            # ===========================================================
            # TICKET LIFECYCLE
            # ===========================================================
            "ticket_before_create": {
                "description": "Fired before a ticket is persisted.",
                "parameters": ["validated_data", "request"],
                "example": (
                    "add_action('ticket_before_create', "
                    "lambda data, request: data.update({'channel': 'api'}))"
                ),
            },
            "ticket_created": {
                "description": "Fired after a ticket is created.",
                "parameters": ["ticket", "user"],
                "example": (
                    "add_action('ticket_created', "
                    "lambda ticket, user: print(ticket.reference))"
                ),
            },
            "ticket_before_update": {
                "description": "Fired before a ticket is updated.",
                "parameters": ["ticket", "validated_data", "request"],
                "example": (
                    "add_action('ticket_before_update', "
                    "lambda t, data, req: None)"
                ),
            },
            "ticket_updated": {
                "description": "Fired after a ticket is updated.",
                "parameters": ["ticket", "user", "changes"],
                "example": (
                    "add_action('ticket_updated', "
                    "lambda ticket, user, changes: None)"
                ),
            },
            "ticket_status_changed": {
                "description": "Fired when a ticket's status changes.",
                "parameters": ["ticket", "user", "old_status", "new_status"],
                "example": (
                    "add_action('ticket_status_changed', "
                    "lambda t, u, old, new: print(f'{old} -> {new}'))"
                ),
            },
            "ticket_assigned": {
                "description": "Fired when a ticket is assigned to an agent.",
                "parameters": ["ticket", "user", "agent"],
                "example": (
                    "add_action('ticket_assigned', "
                    "lambda t, u, a: print(f'Assigned to {a}'))"
                ),
            },
            "ticket_unassigned": {
                "description": "Fired when a ticket's assignment is removed.",
                "parameters": ["ticket", "user", "previous_agent"],
                "example": (
                    "add_action('ticket_unassigned', "
                    "lambda t, u, prev: None)"
                ),
            },
            "ticket_priority_changed": {
                "description": "Fired when a ticket's priority changes.",
                "parameters": ["ticket", "user", "old_priority", "new_priority"],
                "example": (
                    "add_action('ticket_priority_changed', "
                    "lambda t, u, old, new: None)"
                ),
            },
            "ticket_escalated": {
                "description": "Fired when a ticket is escalated.",
                "parameters": ["ticket", "user", "reason"],
                "example": (
                    "add_action('ticket_escalated', "
                    "lambda t, u, reason: None)"
                ),
            },
            "ticket_resolved": {
                "description": "Fired when a ticket is resolved.",
                "parameters": ["ticket", "user"],
                "example": (
                    "add_action('ticket_resolved', "
                    "lambda ticket, user: None)"
                ),
            },
            "ticket_closed": {
                "description": "Fired when a ticket is closed.",
                "parameters": ["ticket", "user"],
                "example": (
                    "add_action('ticket_closed', "
                    "lambda ticket, user: None)"
                ),
            },
            "ticket_reopened": {
                "description": "Fired when a ticket is reopened.",
                "parameters": ["ticket", "user"],
                "example": (
                    "add_action('ticket_reopened', "
                    "lambda ticket, user: None)"
                ),
            },
            "ticket_deleted": {
                "description": "Fired after a ticket is deleted.",
                "parameters": ["ticket", "user"],
                "example": (
                    "add_action('ticket_deleted', "
                    "lambda ticket, user: None)"
                ),
            },

            # ===========================================================
            # REPLY HOOKS
            # ===========================================================
            "reply_created": {
                "description": "Fired after a reply is added to a ticket.",
                "parameters": ["reply", "ticket", "user"],
                "example": (
                    "add_action('reply_created', "
                    "lambda reply, ticket, user: None)"
                ),
            },
            "internal_note_added": {
                "description": "Fired after an internal note is added.",
                "parameters": ["reply", "ticket", "user"],
                "example": (
                    "add_action('internal_note_added', "
                    "lambda reply, ticket, user: None)"
                ),
            },

            # ===========================================================
            # SLA HOOKS
            # ===========================================================
            "sla_breached": {
                "description": "Fired when an SLA deadline is breached.",
                "parameters": ["ticket", "breach_type"],
                "example": (
                    "add_action('sla_breached', "
                    "lambda ticket, breach_type: None)"
                ),
            },
            "sla_warning": {
                "description": "Fired when an SLA deadline is approaching.",
                "parameters": ["ticket", "warning_type", "remaining"],
                "example": (
                    "add_action('sla_warning', "
                    "lambda ticket, wtype, remaining: None)"
                ),
            },

            # ===========================================================
            # TAG HOOKS
            # ===========================================================
            "tag_added": {
                "description": "Fired when a tag is added to a ticket.",
                "parameters": ["tag", "ticket", "user"],
                "example": (
                    "add_action('tag_added', "
                    "lambda tag, ticket, user: None)"
                ),
            },
            "tag_removed": {
                "description": "Fired when a tag is removed from a ticket.",
                "parameters": ["tag", "ticket", "user"],
                "example": (
                    "add_action('tag_removed', "
                    "lambda tag, ticket, user: None)"
                ),
            },

            # ===========================================================
            # DEPARTMENT HOOKS
            # ===========================================================
            "department_changed": {
                "description": "Fired when a ticket is moved to a different department.",
                "parameters": ["ticket", "user", "old_department", "new_department"],
                "example": (
                    "add_action('department_changed', "
                    "lambda t, u, old, new: None)"
                ),
            },

            # ===========================================================
            # DASHBOARD HOOKS
            # ===========================================================
            "dashboard_viewed": {
                "description": "Fired when the agent dashboard is viewed.",
                "parameters": ["user"],
                "example": (
                    "add_action('dashboard_viewed', "
                    "lambda user: None)"
                ),
            },
        }

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    @staticmethod
    def get_filters():
        return {
            # ===========================================================
            # TICKET FILTERS
            # ===========================================================
            "ticket_subject": {
                "description": "Modify a ticket's subject before display.",
                "parameters": ["subject", "ticket"],
                "example": (
                    "add_filter('ticket_subject', "
                    "lambda subj, ticket: subj.upper())"
                ),
            },
            "ticket_description": {
                "description": "Modify a ticket's description before display.",
                "parameters": ["description", "ticket"],
                "example": (
                    "add_filter('ticket_description', "
                    "lambda desc, ticket: desc)"
                ),
            },
            "ticket_list_query": {
                "description": "Modify the ticket list queryset.",
                "parameters": ["queryset", "request"],
                "example": (
                    "add_filter('ticket_list_query', "
                    "lambda qs, req: qs.filter(priority='high'))"
                ),
            },
            "ticket_list_data": {
                "description": "Modify serialized ticket list before rendering.",
                "parameters": ["tickets", "request"],
                "example": (
                    "add_filter('ticket_list_data', "
                    "lambda tickets, req: tickets)"
                ),
            },
            "ticket_show_data": {
                "description": "Modify ticket data before displaying detail page.",
                "parameters": ["ticket_data", "ticket"],
                "example": (
                    "add_filter('ticket_show_data', "
                    "lambda data, t: data)"
                ),
            },
            "ticket_store_validation": {
                "description": "Modify validation rules for creating tickets.",
                "parameters": ["rules", "request"],
                "example": (
                    "add_filter('ticket_store_validation', "
                    "lambda rules, req: {**rules, 'custom_field': 'required'})"
                ),
            },
            "ticket_store_data": {
                "description": "Modify validated data before creating a ticket.",
                "parameters": ["validated_data", "request"],
                "example": (
                    "add_filter('ticket_store_data', "
                    "lambda data, req: data)"
                ),
            },
            "ticket_update_data": {
                "description": "Modify validated data before updating a ticket.",
                "parameters": ["validated_data", "ticket", "request"],
                "example": (
                    "add_filter('ticket_update_data', "
                    "lambda data, ticket, req: data)"
                ),
            },

            # ===========================================================
            # DASHBOARD FILTERS
            # ===========================================================
            "dashboard_stats_data": {
                "description": "Modify dashboard statistics before rendering.",
                "parameters": ["stats", "user"],
                "example": (
                    "add_filter('dashboard_stats_data', "
                    "lambda stats, user: {**stats, 'custom': 42})"
                ),
            },
            "dashboard_page_data": {
                "description": "Modify all data passed to the dashboard page.",
                "parameters": ["data", "user"],
                "example": (
                    "add_filter('dashboard_page_data', "
                    "lambda data, user: data)"
                ),
            },

            # ===========================================================
            # UI FILTERS
            # ===========================================================
            "navigation_menu": {
                "description": "Add or modify navigation menu items.",
                "parameters": ["menu_items", "user"],
                "example": (
                    "add_filter('navigation_menu', "
                    "lambda items, user: items + [{'label': 'Custom'}])"
                ),
            },
            "sidebar_menu": {
                "description": "Add or modify sidebar menu items.",
                "parameters": ["menu_items", "user"],
                "example": (
                    "add_filter('sidebar_menu', "
                    "lambda items, user: items)"
                ),
            },
            "user_permissions": {
                "description": "Modify user permissions.",
                "parameters": ["permissions", "user"],
                "example": (
                    "add_filter('user_permissions', "
                    "lambda perms, user: perms + ['custom_perm'])"
                ),
            },

            # ===========================================================
            # REPLY FILTERS
            # ===========================================================
            "reply_body": {
                "description": "Modify a reply body before display.",
                "parameters": ["body", "reply"],
                "example": (
                    "add_filter('reply_body', "
                    "lambda body, reply: body)"
                ),
            },

            # ===========================================================
            # NOTIFICATION FILTERS
            # ===========================================================
            "notification_channels": {
                "description": "Modify which channels a notification is sent through.",
                "parameters": ["channels", "event_type", "ticket"],
                "example": (
                    "add_filter('notification_channels', "
                    "lambda ch, evt, t: ch + ['slack'])"
                ),
            },
            "notification_recipients": {
                "description": "Modify the list of recipients for a notification.",
                "parameters": ["recipients", "event_type", "ticket"],
                "example": (
                    "add_filter('notification_recipients', "
                    "lambda recips, evt, t: recips)"
                ),
            },
        }

    # ------------------------------------------------------------------
    # Combined
    # ------------------------------------------------------------------

    @staticmethod
    def get_all_hooks():
        return {
            "actions": HookRegistry.get_actions(),
            "filters": HookRegistry.get_filters(),
        }
