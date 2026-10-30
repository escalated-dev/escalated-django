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
        self._custom_pages = {}  # {route: page_config}
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
        "target": "agent",  # 'agent' or 'admin'
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

    def get_menu_items(self, target=None):
        """
        Return registered menu items, sorted by position.

        Args:
            target: Optional filter — ``'agent'`` or ``'admin'``.
                    When *None*, all items are returned.
        """
        items = self._menu_items
        if target is not None:
            items = [m for m in items if m.get("target") == target]
        return sorted(items, key=lambda m: m.get("position", 100))

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
        "target": "agent",  # 'agent' or 'admin'
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

    def get_dashboard_widgets(self, target=None):
        """
        Return registered dashboard widgets, sorted by position.

        Args:
            target: Optional filter — ``'agent'`` or ``'admin'``.
                    When *None*, all widgets are returned.
        """
        widgets = self._dashboard_widgets
        if target is not None:
            widgets = [w for w in widgets if w.get("target") == target]
        return sorted(widgets, key=lambda w: w.get("position", 100))

    # ------------------------------------------------------------------
    # Custom Pages
    # ------------------------------------------------------------------

    _PAGE_DEFAULTS = {
        "middleware": ["auth"],
        "permission": None,
        "title": "Custom Page",
    }

    def register_page(self, route, component, **options):
        """
        Register a custom page route that a plugin provides.

        Args:
            route: Route name / URL path, e.g. ``'/my-plugin/dashboard'``.
            component: Inertia component name to render.
            **options: Extra keys merged into the page config (e.g.
                       ``title``, ``permission``, ``middleware``).
        """
        merged = {
            **self._PAGE_DEFAULTS,
            "route": route,
            "component": component,
            **options,
        }
        self._custom_pages[route] = merged

    def get_custom_pages(self):
        """Return all registered custom pages as a dict keyed by route."""
        return dict(self._custom_pages)

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

    # ------------------------------------------------------------------
    # Shared with every page
    # ------------------------------------------------------------------

    def shared_extensions(self, is_admin=False, permissions=(), user=None):
        """
        ``escalated.plugins`` for the shared screens: the shape the frontend's
        usePluginExtensions() reads (domain-model/plugin-contract.md) --
        ``menuItems``, ``pageComponents`` (``"page.slot"`` to items) and
        ``dashboardWidgets`` -- from what active Python plugins registered
        plus the SDK plugins' manifests. Items whose permission or capability
        the viewer lacks are left out, and admin menu items go to admins
        only. ``{}`` when there is nothing to show.

        An SDK widget with a badge function (manifest ``hasBadge``) carries
        the plugin's ``badge`` answer, asked of the runtime as *user* (the
        viewer); ``None`` when that fails.
        """
        permissions = set(permissions or ())

        def allows(ability):
            return not ability or "*" in permissions or ability in permissions

        menu_items = []
        for item in self.get_menu_items():
            section = item.get("section") or item.get("target") or "admin"
            if (section == "admin" and not is_admin) or not allows(item.get("permission")):
                continue
            menu_items.append(
                {
                    "label": item.get("label"),
                    "route": item.get("url") or item.get("route"),
                    "icon": item.get("icon"),
                    "position": item.get("position", 100),
                    "section": section,
                    "plugin": item.get("plugin"),
                    "badge": item.get("badge"),
                    "submenu": item.get("submenu") or [],
                }
            )

        widgets = []
        for widget in self.get_dashboard_widgets():
            if (widget.get("target") == "admin" and not is_admin) or not allows(widget.get("permission")):
                continue
            widgets.append(
                {
                    "id": widget.get("id"),
                    "title": widget.get("title"),
                    "component": widget.get("component"),
                    "plugin": widget.get("plugin"),
                    "data": widget.get("data") or {},
                    "position": widget.get("position", 100),
                    "width": widget.get("width", "full"),
                }
            )

        slots = {}
        for page, by_slot in self._page_components.items():
            for slot in by_slot:
                for component in self.get_page_components(page, slot):
                    if not allows(component.get("permission")):
                        continue
                    slots.setdefault(f"{page}.{slot}", []).append(
                        {
                            "plugin": component.get("plugin"),
                            "component": component.get("component"),
                            "data": component.get("data") or {},
                            "position": component.get("position", 100),
                        }
                    )

        self._add_sdk_extensions(widgets, slots, allows, user)

        if not menu_items and not widgets and not slots:
            return {}

        return {
            "menuItems": sorted(menu_items, key=lambda m: m["position"]),
            "pageComponents": {key: sorted(items, key=lambda c: c["position"]) for key, items in slots.items()},
            "dashboardWidgets": sorted(widgets, key=lambda w: w["position"]),
        }

    @staticmethod
    def slug(name):
        """The contract's URL-safe slug: ``@escalated-dev/plugin-slack`` is ``escalated-dev--plugin-slack``."""
        import re

        return re.sub(r"[^A-Za-z0-9_-]", "-", str(name).removeprefix("@").replace("/", "--"))

    def _add_sdk_extensions(self, widgets, slots, allows, user=None):
        """
        SDK plugins' widget and slot declarations. Their pages are not mounted
        by this package yet, so their menu entries are not shared.
        """
        try:
            from escalated.bridge.plugin_bridge import get_bridge

            bridge = get_bridge()
            manifests = bridge.get_manifests() if bridge.is_booted() else {}
        except Exception:
            manifests = {}

        for name, manifest in manifests.items():
            slug = self.slug(name)
            for widget in manifest.get("widgets") or []:
                if not widget.get("component") or not allows(widget.get("capability")):
                    continue
                item = {
                    "id": f"{slug}.{widget['component']}",
                    "title": widget.get("label"),
                    "component": widget["component"],
                    "plugin": slug,
                    "position": widget.get("order", 100),
                    "width": widget.get("size", "half"),
                }
                if widget.get("hasBadge") is True:
                    item["badge"] = self._sdk_badge(bridge, name, widget["component"], user)
                widgets.append(item)
            for component in manifest.get("components") or []:
                if not (component.get("page") and component.get("slot") and component.get("component")):
                    continue
                if not allows(component.get("capability")):
                    continue
                slots.setdefault(f"{component['page']}.{component['slot']}", []).append(
                    {
                        "plugin": slug,
                        "component": component["component"],
                        "data": component.get("props") or {},
                        "position": component.get("order", 100),
                    }
                )

    @staticmethod
    def _sdk_badge(bridge, name, component, user):
        try:
            return bridge.badge(name, component, user)
        except Exception:
            return None

    def clear(self):
        """Remove all registered UI elements. Useful for testing."""
        self._menu_items.clear()
        self._dashboard_widgets.clear()
        self._custom_pages.clear()
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


def register_page(route, component, **options):
    """Shortcut: register a custom page on the global PluginUIService."""
    plugin_ui.register_page(route, component, **options)


def add_page_component(page, slot, component):
    """Shortcut: register a page-slot component on the global PluginUIService."""
    plugin_ui.add_page_component(page, slot, component)
