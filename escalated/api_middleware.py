import hashlib
import json
import time

from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone

from escalated.conf import get_setting
from escalated.models import ApiToken


class AuthenticateApiToken:
    """
    Middleware that authenticates API requests using Bearer tokens.

    Extracts the token from the Authorization header, hashes it with SHA-256,
    looks up the token in the database, checks expiration, resolves the user,
    and updates last_used_at / last_used_ip.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Extract Bearer token from Authorization header
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return JsonResponse({"message": "Unauthenticated."}, status=401)

        plain_text = auth_header[7:]
        if not plain_text:
            return JsonResponse({"message": "Unauthenticated."}, status=401)

        # Look up token
        api_token = ApiToken.find_by_plain_text(plain_text)
        if api_token is None:
            return JsonResponse({"message": "Invalid token."}, status=401)

        # Check expiration
        if api_token.is_expired:
            return JsonResponse({"message": "Token has expired."}, status=401)

        # Resolve the token's owner
        user = api_token.tokenable
        if user is None:
            return JsonResponse({"message": "Token owner not found."}, status=401)

        # Update last used info
        api_token.last_used_at = timezone.now()
        api_token.last_used_ip = _get_client_ip(request)
        api_token.save(update_fields=["last_used_at", "last_used_ip", "updated_at"])

        # Attach user and token to request
        request.user = user
        request.api_token = api_token

        return None


class ApiRateLimit:
    """
    Per-token rate limiting middleware for API requests.

    Uses Django's cache framework with a sliding window per minute.
    Adds X-RateLimit-Limit and X-RateLimit-Remaining headers to responses.
    Returns 429 with Retry-After header when limit is exceeded.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        max_attempts = get_setting("API_RATE_LIMIT")

        # Determine rate-limit key (by token ID or IP)
        api_token = getattr(request, "api_token", None)
        if api_token:
            key = f"escalated_api:{api_token.pk}"
        else:
            key = f"escalated_api:{_get_client_ip(request)}"

        # Get current hit count
        current = cache.get(key)

        if current is not None and current >= max_attempts:
            # Calculate retry_after: TTL remaining on the cache key
            retry_after = cache.ttl(key) if hasattr(cache, "ttl") else 60

            response = JsonResponse(
                {"message": "Too many requests.", "retry_after": retry_after},
                status=429,
            )
            response["Retry-After"] = str(retry_after)
            response["X-RateLimit-Limit"] = str(max_attempts)
            response["X-RateLimit-Remaining"] = "0"
            return response

        return None

    def process_response(self, request, response):
        # Only add rate-limit headers to API responses
        if not hasattr(request, "api_token") and not request.path.startswith(
            "/" + get_setting("API_PREFIX")
        ):
            return response

        max_attempts = get_setting("API_RATE_LIMIT")

        api_token = getattr(request, "api_token", None)
        if api_token:
            key = f"escalated_api:{api_token.pk}"
        else:
            key = f"escalated_api:{_get_client_ip(request)}"

        # Increment the counter (60-second window)
        current = cache.get(key)
        if current is None:
            cache.set(key, 1, 60)
            current = 1
        else:
            try:
                current = cache.incr(key)
            except ValueError:
                cache.set(key, 1, 60)
                current = 1

        remaining = max(0, max_attempts - current)
        response["X-RateLimit-Limit"] = str(max_attempts)
        response["X-RateLimit-Remaining"] = str(remaining)

        return response


def _get_client_ip(request):
    """Extract the client IP from the request."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")
