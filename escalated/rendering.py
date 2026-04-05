from django.utils.module_loading import import_string
from escalated.conf import get_setting


class UiRenderer:
    """Abstract base for rendering UI pages."""
    def render(self, request, component, props=None):
        raise NotImplementedError


class InertiaRenderer(UiRenderer):
    """Default renderer using inertia-django."""
    def render(self, request, component, props=None):
        from inertia import render
        return render(request, component, props=props or {})


_renderer_instance = None


def get_renderer():
    global _renderer_instance
    if _renderer_instance is None:
        custom = get_setting("UI_RENDERER") if get_setting("UI_ENABLED") else None
        if custom:
            cls = import_string(custom)
            _renderer_instance = cls()
        elif get_setting("UI_ENABLED"):
            _renderer_instance = InertiaRenderer()
        else:
            raise RuntimeError(
                "Escalated UI is disabled. Set UI_ENABLED=True or provide a custom UI_RENDERER."
            )
    return _renderer_instance


def render_page(request, component, props=None):
    """Convenience function used by views."""
    return get_renderer().render(request, component, props)
