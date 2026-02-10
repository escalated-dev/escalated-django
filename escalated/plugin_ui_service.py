"""
Service for plugins to register custom UI elements.

Plugins can register menu items, dashboard widgets, and page-slot components
that the host application renders at the appropriate locations.

Usage from a plugin::

    from escalated.plugin_ui_service import plugin_ui

    plugin_ui.add_menu_item({
        'label': 'My Plugin',
        'url': '/my-plugin/',
        'icon': 'puzzle',
        'position': 50,
    })

    plugin_ui.add_dashboard_widget({
        'title': 'My Widget',
        'component': 'MyPluginWidget',
        'data': {'message': 'Hello!'},
        'width': 'half',
    })

    plugin_ui.add_page_component('ticket.show', 'sidebar', {
        'component': 'MyPluginSidebar',
        'data': {'key': 'value'},
        'position': 10,
    })
"""

import uuid


class PluginUIService:
    """
    Central registry for plugin-contributed UI extensions.

    The host application queries this service to discover what extra menus,
    widgets, and slot components plugins have registered.
    """

    def __init__(self):
        self._menu_items = []
        self._dashboard_widgets = []
        self._page_components = {}  # {page: {slot: [component, ...]}}

    # ------------------------------------------------------------------
    # Menu Items
    # ------------------------------------------------------------------

    _MENU_DEFAULTS = {
        "label": "Custom Item",
        "route": None,
        "url": None,
        "icon": None,
        "permission": None,
        "position": 100,
        "parent": None,
        "badge": None,
        "active_routes": [],
        "submenu": [],
    }

    def add_menu_item(self, item):
        """
        Register a custom menu item.

        *item* is a dict that is merged with sensible defaults::

            {
                'label': 'My Page',
                'url': '/my-page/',
                'icon': 'puzzle',
                'position': 50,
            }
        """
        merged = {**self._MENU_DEFAULTS, **item}
        self._menu_items.append(merged)

    def add_menu_items(self, items):
        """Register multiple menu items at once."""
        for item in items:
            self.add_menu_item(item)

    def add_submenu_item(self, parent_label, submenu_item):
        """
        Append a submenu item to the menu item whose label is *parent_label*.
        """
        defaults = {
            "label": "Submenu Item",
            "route": None,
            "url": None,
            "icon": None,
            "permission": None,
            "active_routes": [],
        }
        merged = {**defaults, **submenu_item}

        for menu_item in self._menu_items:
            if menu_item["label"] == parent_label:
                if not isinstance(menu_item.get("submenu"), list):
                    menu_item["submenu"] = []
                menu_item["submenu"].append(merged)
                break

    def get_menu_items(self):
        """Return all registered menu items, sorted by position."""
        return sorted(self._menu_items, key=lambda m: m.get("position", 100))

    # ------------------------------------------------------------------
    # Dashboard Widgets
    # ------------------------------------------------------------------

    _WIDGET_DEFAULTS = {
        "title": "Custom Widget",
        "component": None,
        "data": {},
        "position": 100,
        "width": "full",  # 'full', 'half', 'third', 'quarter'
        "permission": None,
    }

    def add_dashboard_widget(self, widget):
        """
        Register a dashboard widget.

        *widget* is a dict merged with sensible defaults::

            {
                'title': 'My Widget',
                'component': 'MyWidget',
                'data': {},
                'width': 'half',
                'position': 20,
            }
        """
        merged = {**self._WIDGET_DEFAULTS, **widget}
        if "id" not in merged:
            merged["id"] = f"widget_{uuid.uuid4().hex[:8]}"
        self._dashboard_widgets.append(merged)

    def get_dashboard_widgets(self):
        """Return all registered dashboard widgets, sorted by position."""
        return sorted(self._dashboard_widgets, key=lambda w: w.get("position", 100))

    # ------------------------------------------------------------------
    # Page Components (Slots)
    # ------------------------------------------------------------------

    _COMPONENT_DEFAULTS = {
        "component": None,
        "data": {},
        "position": 100,
        "permission": None,
    }

    def add_page_component(self, page, slot, component):
        """
        Register a component to be injected into an existing page's slot.

        Args:
            page: Page identifier, e.g. ``'ticket.show'``, ``'dashboard'``.
            slot: Slot name, e.g. ``'sidebar'``, ``'header'``, ``'footer'``.
            component: Dict of component configuration.
        """
        merged = {**self._COMPONENT_DEFAULTS, **component}

        self._page_components.setdefault(page, {})
        self._page_components[page].setdefault(slot, [])
        self._page_components[page][slot].append(merged)

    def get_page_components(self, page, slot):
        """
        Return components registered for a specific page and slot,
        sorted by position.
        """
        components = self._page_components.get(page, {}).get(slot, [])
        return sorted(components, key=lambda c: c.get("position", 100))

    def get_all_page_components(self, page):
        """Return all slots and their components for a specific page."""
        return self._page_components.get(page, {})

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def clear(self):
        """Remove all registered UI elements. Useful for testing."""
        self._menu_items.clear()
        self._dashboard_widgets.clear()
        self._page_components.clear()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

plugin_ui = PluginUIService()


# ---------------------------------------------------------------------------
# Convenience functions for plugins
# ---------------------------------------------------------------------------


def register_menu_item(item):
    """Shortcut: register a menu item on the global PluginUIService."""
    plugin_ui.add_menu_item(item)


def register_dashboard_widget(widget):
    """Shortcut: register a dashboard widget on the global PluginUIService."""
    plugin_ui.add_dashboard_widget(widget)


def add_page_component(page, slot, component):
    """Shortcut: register a page-slot component on the global PluginUIService."""
    plugin_ui.add_page_component(page, slot, component)
