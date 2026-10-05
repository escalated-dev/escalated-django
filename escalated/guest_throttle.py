"""
Per-client-IP rate limit for the unauthenticated guest endpoints.

Every accepted guest ticket or reply writes rows and sends outbound mail, so an
uncapped endpoint lets anyone flood the helpdesk and the mail provider. The
limit is configured by ``ESCALATED["GUEST_RATE_LIMIT"]`` (see
``escalated.conf.DEFAULTS``): 5 ticket submissions and 10 replies per IP per
minute by default, counted in separate buckets. A request over the limit gets
``429`` with ``Retry-After``.

The client IP is ``request.META["REMOTE_ADDR"]``. Django does not rewrite it
from ``X-Forwarded-For``, so a host behind a reverse proxy or load balancer
must set ``REMOTE_ADDR`` from its trusted proxies (e.g. a small middleware or
the proxy's own real-IP module); otherwise every guest shares the proxy's
address and one limit.

Counters live in the Django cache named by ``GUEST_RATE_LIMIT["CACHE"]``. A
multi-process or multi-host deployment needs a shared backend there (Redis,
Memcached, database); the per-process ``LocMemCache`` counts per worker.
"""

import math
import time

from django.core.cache import caches
from django.http import HttpResponse, JsonResponse

from escalated.conf import get_setting

WINDOW_SECONDS = 60

TICKET = "ticket"
REPLY = "reply"

_LIMIT_KEYS = {TICKET: "TICKETS_PER_MINUTE", REPLY: "REPLIES_PER_MINUTE"}


def client_ip(request):
    return request.META.get("REMOTE_ADDR") or "unknown"


def check(request, scope):
    """
    Count this request against ``scope`` (``"ticket"`` or ``"reply"``) for the
    client IP. Returns ``None`` when it is allowed, or the seconds until the
    window resets when it is over the limit.

    The window is a fixed 60-second bucket, so the counter is a single atomic
    ``cache.incr`` on backends that support it.
    """
    config = get_setting("GUEST_RATE_LIMIT")
    if not config.get("ENABLED", True):
        return None

    limit = int(config[_LIMIT_KEYS[scope]])
    now = time.time()
    bucket = int(now // WINDOW_SECONDS)
    retry_after = max(1, math.ceil((bucket + 1) * WINDOW_SECONDS - now))

    store = caches[config.get("CACHE") or "default"]
    key = f"escalated.guest_throttle.{scope}.{client_ip(request)}.{bucket}"
    # add() is a no-op when the key exists; the timeout outlives the bucket so
    # a counter never expires mid-window.
    store.add(key, 0, WINDOW_SECONDS + 5)
    try:
        hits = store.incr(key)
    except ValueError:
        # Evicted between add() and incr(): this is the first hit again.
        store.set(key, 1, WINDOW_SECONDS + 5)
        hits = 1

    return retry_after if hits > limit else None


def too_many_requests(retry_after, json=False):
    message = "Too many requests. Please try again later."
    response = JsonResponse({"error": message}, status=429) if json else HttpResponse(message, status=429)
    response["Retry-After"] = str(retry_after)
    return response
