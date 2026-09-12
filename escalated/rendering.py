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
            raise RuntimeError("Escalated UI is disabled. Set UI_ENABLED=True or provide a custom UI_RENDERER.")
    return _renderer_instance


def render_page(request, component, props=None):
    """Convenience function used by views."""
    return get_renderer().render(request, component, props)


def paginated(request, page, rows):
    """A page of records, shaped the way the frontend list components read it.

    They were written against a paginator that carries its own links: they
    iterate ``records.links`` for ``{url, label, active}``, read the rows off
    ``records.data`` and gate the pagination control on ``records.last_page``.
    Handed a bare list and a sibling ``pagination`` dict they find no ``data``
    at all and render as empty -- which on a ticket queue reads as a quiet day
    rather than as a wiring fault.

    ``page`` is a Django ``Page``; ``rows`` is the already-serialised list.
    """
    paginator = page.paginator
    current = page.number
    last = paginator.num_pages

    def url_for(number):
        query = request.GET.copy()
        query["page"] = number
        return f"{request.path}?{query.urlencode()}"

    links = []
    if last > 1:
        # Previous / page numbers / Next, with a null url on the ones that lead
        # nowhere -- the component styles those as inert rather than hiding them.
        links.append(
            {"url": url_for(current - 1) if page.has_previous() else None, "label": "&laquo; Previous", "active": False}
        )
        links += [{"url": url_for(n), "label": str(n), "active": n == current} for n in paginator.page_range]
        links.append(
            {"url": url_for(current + 1) if page.has_next() else None, "label": "Next &raquo;", "active": False}
        )

    return {
        "data": rows,
        "current_page": current,
        "last_page": last,
        "per_page": paginator.per_page,
        "total": paginator.count,
        "links": links,
    }
