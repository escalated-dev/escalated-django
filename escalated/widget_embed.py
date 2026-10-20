"""
Embedding the widget on other sites.

A site listed in ``ESCALATED["WIDGET_ALLOWED_ORIGINS"]`` or in the admin
setting ``widget_allowed_origins`` (one origin per line or comma separated)
may load ``{prefix}/widget/embed.js`` and call the widget endpoints from the
browser. :func:`widget_cors` wraps every widget view: it answers preflight
requests, adds CORS headers to every answer for an allowed origin and runs
such requests as an anonymous guest. Only those requests skip the host's CSRF
check: requests from any other origin, and same-origin requests, go through
the host's ``CsrfViewMiddleware`` exactly as any other view would.

:class:`WidgetMetadata` cleans the host parameters (order number, plan, page
URL, ...) the embedding page sends with a ticket or chat.
"""

import functools
import hashlib
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import DisallowedHost
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.utils.cache import patch_vary_headers
from django.utils.module_loading import import_string

from escalated.conf import get_setting

#: The standalone widget bundle built by ``@escalated-dev/escalated``.
EMBED_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "escalated" / "widget" / "escalated-widget.js"

#: Request attribute set to the Origin of a request from an allowed other site.
ORIGIN_ATTRIBUTE = "escalated_widget_origin"

ALLOW_METHODS = "GET, POST, OPTIONS"
ALLOW_HEADERS = "Accept, Authorization, Content-Type, X-Requested-With"

_PATTERN_RE = re.compile(r"(https?)://(\*\.)?([^/?#*]+?)/?", re.IGNORECASE)
_HOSTNAME_RE = re.compile(r"[a-z0-9._-]+")
_IPV6_RE = re.compile(r"[0-9a-f:.]+")
_SPLIT_RE = re.compile(r"[\s,]+")


class WidgetOrigins:
    """Decides which other sites may embed the widget."""

    @staticmethod
    def normalize(origin):
        """``scheme://host[:port]``, lowercased, default ports dropped; None if not a bare http(s) origin."""
        if not isinstance(origin, str):
            return None
        try:
            parts = urlsplit(origin.strip())
            port = parts.port
        except ValueError:
            return None
        scheme = parts.scheme.lower()
        host = (parts.hostname or "").lower()
        if (
            scheme not in ("http", "https")
            or not host
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or parts.path not in ("", "/")
            or "?" in origin
            or "#" in origin
        ):
            return None
        if ":" in host:
            if not _IPV6_RE.fullmatch(host):
                return None
            host = f"[{host}]"
        elif not _HOSTNAME_RE.fullmatch(host):
            return None

        if port is None or (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
            return f"{scheme}://{host}"
        return f"{scheme}://{host}:{port}"

    @classmethod
    def normalize_pattern(cls, entry):
        """Normalise an admin-entered origin or ``https://*.example.com`` pattern; None when invalid."""
        match = _PATTERN_RE.fullmatch(str(entry).strip())
        if not match:
            return None
        host = cls.normalize(f"{match.group(1).lower()}://{match.group(3)}")
        if host is None:
            return None
        return host.replace("://", "://*.", 1) if match.group(2) else host

    @classmethod
    def patterns(cls, entries):
        patterns = []
        for entry in entries:
            pattern = cls.normalize_pattern(entry)
            if pattern is not None and pattern not in patterns:
                patterns.append(pattern)
        return patterns

    @staticmethod
    def split(value):
        """Entries of a newline/comma separated list."""
        return [entry for entry in _SPLIT_RE.split(value or "") if entry]

    @classmethod
    def configured(cls):
        """The allowed origins and patterns: the ESCALATED setting plus the admin setting."""
        from escalated.models import EscalatedSetting

        entries = get_setting("WIDGET_ALLOWED_ORIGINS") or []
        entries = cls.split(entries) if isinstance(entries, str) else list(entries)
        entries += cls.split(EscalatedSetting.get("widget_allowed_origins", "") or "")
        return cls.patterns(entries)

    @staticmethod
    def matches(pattern, origin):
        if "://*." not in pattern:
            return pattern == origin
        scheme, suffix = pattern.split("://*.", 1)
        if not origin.startswith(f"{scheme}://"):
            return False
        host = origin[len(scheme) + 3 :]
        return host.endswith(f".{suffix}") and len(host) > len(suffix) + 1

    @classmethod
    def allows(cls, origin):
        origin = cls.normalize(origin)
        if origin is None:
            return False
        return any(cls.matches(pattern, origin) for pattern in cls.configured())

    @classmethod
    def cross_origin(cls, request):
        """The request's Origin when it names another site, else None."""
        raw = request.META.get("HTTP_ORIGIN")
        if not raw or raw == "null":
            return None
        origin = cls.normalize(raw)
        if origin is None:
            return None
        try:
            own = cls.normalize(f"{request.scheme}://{request.get_host()}")
        except DisallowedHost:
            own = None
        return None if origin == own else origin


def _with_cors_headers(response, origin):
    response["Access-Control-Allow-Origin"] = origin
    response["Access-Control-Expose-Headers"] = "Retry-After"
    patch_vary_headers(response, ("Origin",))
    return response


def _host_csrf_middleware():
    """The host's CSRF middleware class, when it installed one."""
    for path in getattr(settings, "MIDDLEWARE", None) or []:
        try:
            middleware = import_string(path)
        except ImportError:
            continue
        if isinstance(middleware, type) and issubclass(middleware, CsrfViewMiddleware):
            return middleware
    return None


def _csrf_rejection(request, view, args, kwargs):
    """
    The host's CSRF answer for a request that is not from an allowed embedding
    site, else None. Mirrors Laravel's WidgetCsrf: an allowed cross-origin
    request carries no session cookie and runs as a guest, so it has no token
    to send and nothing to protect; every other request is checked as usual.
    """
    middleware = _host_csrf_middleware()
    if middleware is None:
        return None
    return middleware(lambda req: None).process_view(request, view, args, kwargs)


def widget_cors(view):
    """
    CORS for a widget view. Only allowed origins get CORS headers, and such
    requests always run as an anonymous guest: a cross-site embed never acts
    as whoever is signed in to Escalated in the same browser.
    """

    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        origin = WidgetOrigins.cross_origin(request)
        allowed = origin is not None and WidgetOrigins.allows(origin)

        if request.method == "OPTIONS" and "HTTP_ACCESS_CONTROL_REQUEST_METHOD" in request.META:
            response = HttpResponse(status=204)
            patch_vary_headers(response, ("Origin",))
            if allowed:
                response["Access-Control-Allow-Methods"] = ALLOW_METHODS
                response["Access-Control-Allow-Headers"] = ALLOW_HEADERS
                response["Access-Control-Max-Age"] = str(int(get_setting("WIDGET_PREFLIGHT_MAX_AGE")))
                _with_cors_headers(response, origin)
            return response

        if not allowed:
            rejection = _csrf_rejection(request, view, args, kwargs)
            if rejection is not None:
                return rejection
            return view(request, *args, **kwargs)

        setattr(request, ORIGIN_ATTRIBUTE, origin)
        request.user = AnonymousUser()
        return _with_cors_headers(view(request, *args, **kwargs), origin)

    # The host's middleware skips these views; the check above decides instead.
    wrapped.csrf_exempt = True
    return wrapped


class WidgetMetadata:
    """
    Host parameters an embedding page sends with a widget ticket or chat.
    They come from the visitor's browser, so only a flat map of short scalar
    values is kept.
    """

    MAX_ENTRIES = 25
    MAX_KEYS = 50
    MAX_VALUE_LENGTH = 500
    MAX_URL_LENGTH = 2048
    KEY_RE = re.compile(r"[A-Za-z0-9_.:-]{1,64}")

    @classmethod
    def error(cls, raw):
        """A validation message when ``metadata`` is present but unusable, else None."""
        if raw is None:
            return None
        if not isinstance(raw, dict):
            return "The metadata field must be an object."
        if len(raw) > cls.MAX_KEYS:
            return f"The metadata field must not have more than {cls.MAX_KEYS} keys."
        return None

    @classmethod
    def clean(cls, raw, request=None):
        """The kept entries, with ``embedded_on`` set from an allowed Origin; None when empty."""
        clean = {}
        for key, value in (raw if isinstance(raw, dict) else {}).items():
            if len(clean) >= cls.MAX_ENTRIES:
                break
            if not isinstance(key, str) or not cls.KEY_RE.fullmatch(key):
                continue
            if isinstance(value, str):
                value = value.strip()
                # Checked before the cut, so a page_url over the limit is dropped, not shortened.
                if key == "page_url" and not cls._is_web_url(value):
                    continue
                value = value[: cls.MAX_VALUE_LENGTH]
            elif key == "page_url":
                continue
            elif isinstance(value, float):
                if not math.isfinite(value):
                    continue
            elif not isinstance(value, (bool, int)):
                continue
            clean[key] = value

        # Recorded by the server from the request's Origin header, so the
        # page cannot claim another site.
        clean.pop("embedded_on", None)
        origin = getattr(request, ORIGIN_ATTRIBUTE, None) if request is not None else None
        if isinstance(origin, str):
            clean["embedded_on"] = origin

        return clean or None

    @classmethod
    def _is_web_url(cls, value):
        if not isinstance(value, str) or len(value) > cls.MAX_URL_LENGTH or re.search(r"\s", value):
            return False
        try:
            parts = urlsplit(value)
        except ValueError:
            return False
        return parts.scheme.lower() in ("http", "https") and bool(parts.hostname)


_script_cache = {}


def embed_script():
    """``(bytes, etag)`` of the bundle, or None when it is missing. Re-read when the file changes."""
    try:
        mtime = EMBED_SCRIPT_PATH.stat().st_mtime_ns
    except OSError:
        return None
    cached = _script_cache.get("script")
    if cached is None or cached[0] != mtime:
        content = EMBED_SCRIPT_PATH.read_bytes()
        cached = (mtime, content, '"' + hashlib.md5(content, usedforsecurity=False).hexdigest() + '"')
        _script_cache["script"] = cached
    return cached[1], cached[2]
