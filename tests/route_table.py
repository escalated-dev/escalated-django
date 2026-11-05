"""
Every Escalated URL the host's URLconf serves, as plain data: the full path,
the namespaced name, the view, and the layers Escalated wraps it in (access
guard, ticket access context, verb adapters, widget CORS), plus the flags
those layers leave on it.

``tests/fixtures/embed/default-routes.json`` is this table for the test
settings, taken from the code before the embeddable admin existed (ADR
2026-11-05-embeddable-admin). With no ``ESCALATED["EMBED"]`` the live table
must still equal it. Regenerate only for a deliberate route change:

    python -m tests.route_table > tests/fixtures/embed/default-routes.json
"""

import json
import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "escalated"


def _layers(view):
    """Escalated's own wrappers, outermost first, then the view itself."""
    layers = []
    current = view
    while current is not None:
        code = getattr(current, "__code__", None)
        wrapped = getattr(current, "__wrapped__", None)
        if code is not None and wrapped is not None:
            filename = Path(code.co_filename).resolve()
            # Django's own decorators (login_required, csrf_exempt...) change
            # their inner names between releases; only Escalated's are listed.
            if PACKAGE in filename.parents:
                layers.append(f"{filename.relative_to(PACKAGE.parent).as_posix()}:{code.co_name}")
        if wrapped is None:
            target = getattr(current, "view_class", None) or current
            layers.append(f"{target.__module__}.{target.__qualname__}")
        current = wrapped
    return layers


def _walk(patterns, prefix="", namespace=""):
    from django.urls import URLPattern, URLResolver

    for entry in patterns:
        if isinstance(entry, URLResolver):
            ns = namespace
            if entry.namespace:
                ns = f"{namespace}{entry.namespace}:"
            yield from _walk(entry.url_patterns, prefix + str(entry.pattern), ns)
        elif isinstance(entry, URLPattern):
            yield prefix + str(entry.pattern), (namespace + entry.name) if entry.name else None, entry


def route_table(urlconf=None):
    """``[{path, name, view, layers, group, accepts, csrf_exempt, kwargs}]`` in URLconf order."""
    from django.urls import get_resolver

    rows = []
    for route, name, pattern in _walk(get_resolver(urlconf).url_patterns):
        if not (name or "").startswith("escalated"):
            continue
        callback = pattern.callback
        rows.append(
            {
                "path": route,
                "name": name,
                "layers": _layers(callback),
                "group": getattr(callback, "escalated_access_group", None),
                "accepts": list(getattr(callback, "escalated_accepts", ()) or ()),
                "csrf_exempt": bool(getattr(callback, "csrf_exempt", False)),
                "kwargs": pattern.default_args or {},
            }
        )
    return rows


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
    import django

    django.setup()
    print(json.dumps(route_table(), indent=1))
