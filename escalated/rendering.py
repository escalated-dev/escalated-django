from django.http import HttpResponseRedirect, JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.module_loading import import_string
from django.utils.translation import gettext as _

from escalated.conf import get_setting

# Field errors a page visit was sent back with, for the next page's `errors`
# prop (escalated-laravel's validation errors in the session).
ERRORS_SESSION_KEY = "escalated_errors"


class UiRenderer:
    """Abstract base for rendering UI pages."""

    def render(self, request, component, props=None):
        raise NotImplementedError


class InertiaRenderer(UiRenderer):
    """Default renderer using inertia-django."""

    def render(self, request, component, props=None):
        from inertia import render

        from escalated import embed
        from escalated.route_list import share_ziggy

        # The route() table the shared pages resolve their links with; a
        # ziggy prop the host shared is merged over it name by name.
        share_ziggy(request)
        props = dict(props or {})
        session = getattr(request, "session", None)
        if session is not None and ERRORS_SESSION_KEY in session:
            errors = session.pop(ERRORS_SESSION_KEY)
            if not props.get("errors"):
                props["errors"] = errors
        # A server-rendered host's admin template, on embedded admin pages
        # only (ESCALATED["EMBED"]["ROOT_VIEW"]; ADR 2026-11-05).
        root_view = embed.root_view_for(request)
        if root_view:
            return render(request, component, props=props, template_data={"inertia_layout": root_view})
        return render(request, component, props=props)


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


def wants_json(request):
    """A JSON client rather than a screen visit (Inertia or a browser)."""
    if request.headers.get("X-Inertia"):
        return False
    return "application/json" in request.headers.get("Accept", "")


def invalid(request, errors, fallback):
    """Malformed input, as escalated-laravel's ``$request->validate()``.

    A JSON client gets a 422 with the field errors. A screen visit goes back to
    the referring page (else ``fallback``) with the errors for the next page's
    ``errors`` prop -- a raw 422 is what the Inertia client shows as an error
    modal. ``errors`` maps a field to a message or a list of messages.
    """
    if wants_json(request):
        listed = {field: value if isinstance(value, list) else [value] for field, value in errors.items()}
        first = next(iter(listed.values()))[0]
        return JsonResponse({"message": first or _("The given data was invalid."), "errors": listed}, status=422)

    session = getattr(request, "session", None)
    if session is not None:
        session[ERRORS_SESSION_KEY] = {
            field: (value[0] if isinstance(value, list) and value else value) for field, value in errors.items()
        }
    referer = request.META.get("HTTP_REFERER")
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return HttpResponseRedirect(referer)
    return HttpResponseRedirect(fallback)


def account_filter_errors(params):
    """escalated-laravel's required_with rule on the account_type/account_id pair."""
    from escalated.ticket_access import account_options

    if not account_options()["ENABLED"] or not ({"account_type", "account_id"} & set(params.keys())):
        return {}
    errors = {}
    if not params.get("account_type"):
        errors["account_type"] = [_("The account type field is required when account id is present.")]
    if not params.get("account_id"):
        errors["account_id"] = [_("The account id field is required when account type is present.")]
    return errors


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
