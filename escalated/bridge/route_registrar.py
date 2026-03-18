"""
Reads plugin manifests returned by the runtime and generates Django URL
patterns.

Three route categories are generated per plugin:

  - Pages      → HTML views: admin/plugins/{plugin}/{route}
  - Endpoints  → JSON API:   api/plugins/{plugin}/{path}
  - Webhooks   → Public:     webhooks/plugins/{plugin}/{path}

All patterns are collected lazily (after the manifest exchange during bridge
boot) and injected into the main urlconf via include() in urls.py.
"""

import logging

from django.http import JsonResponse
from django.urls import path, re_path
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger("escalated.bridge")

VALID_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


class RouteRegistrar:
    """
    Builds and stores Django URL patterns derived from plugin manifests.

    The patterns are stored on the instance and retrieved via
    get_url_patterns(), which is called by PluginBridge.get_plugin_urls()
    and ultimately included in the main URL configuration.
    """

    def __init__(self, bridge):
        self._bridge = bridge
        self._url_patterns: list = []

    def register_all(self, manifests: dict[str, dict]) -> None:
        """Generate URL patterns for every plugin in *manifests*."""
        for plugin_name, manifest in manifests.items():
            self._register_plugin(plugin_name, manifest)

    def get_url_patterns(self) -> list:
        """Return the accumulated URL patterns."""
        return list(self._url_patterns)

    # ------------------------------------------------------------------
    # Per-plugin registration
    # ------------------------------------------------------------------

    def _register_plugin(self, plugin_name: str, manifest: dict) -> None:
        from escalated.conf import get_setting

        prefix = get_setting("ROUTE_PREFIX").strip("/")

        self._register_pages(plugin_name, manifest.get("pages") or [], prefix)
        self._register_endpoints(plugin_name, manifest.get("endpoints") or {}, prefix)
        self._register_webhooks(plugin_name, manifest.get("webhooks") or {}, prefix)

    # ------------------------------------------------------------------
    # Pages — rendered HTML views (Inertia or plain template)
    # ------------------------------------------------------------------

    def _register_pages(
        self, plugin_name: str, pages: list, prefix: str
    ) -> None:
        if not pages:
            return

        for page in pages:
            route = (page.get("route") or "").lstrip("/")
            component = page.get("component", "")
            layout = page.get("layout", "admin")
            capability = page.get("capability")

            if not route or not component:
                logger.warning(
                    "Escalated PluginBridge: skipping page with missing route or "
                    "component for plugin '%s': %s",
                    plugin_name,
                    page,
                )
                continue

            url_pattern = f"{prefix}/admin/plugins/{plugin_name}/{route}"
            view = self._make_page_view(plugin_name, component, layout, capability)
            name = f"escalated.plugin.{plugin_name}.page.{route.replace('/', '.')}"

            self._url_patterns.append(path(url_pattern, view, name=name))
            logger.debug(
                "Escalated PluginBridge: registered page route GET /%s (plugin %s)",
                url_pattern,
                plugin_name,
            )

    def _make_page_view(
        self,
        plugin_name: str,
        component: str,
        layout: str,
        capability: str | None,
    ):
        """Return a Django view function for a plugin page."""
        bridge = self._bridge

        def page_view(request):
            from django.contrib.auth.decorators import login_required
            from django.http import HttpResponseForbidden

            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())

            if not getattr(request.user, "is_staff", False):
                return HttpResponseForbidden("Admin access required.")

            if capability and not request.user.has_perm(capability):
                return HttpResponseForbidden(f"Missing permission: {capability}")

            # Fetch initial props from the plugin's GET endpoint (best-effort)
            props = {}
            try:
                props = bridge.call_endpoint(plugin_name, "GET", f"/{component}", {})
            except Exception:
                pass  # No matching endpoint — props remain empty

            # Try to use django-inertia if available; fall back to JsonResponse
            try:
                from inertia import render as inertia_render
                return inertia_render(
                    request,
                    "Escalated/Plugin/Page",
                    props={
                        "plugin": plugin_name,
                        "component": component,
                        "layout": layout,
                        "props": props,
                    },
                )
            except ImportError:
                pass

            return JsonResponse(
                {
                    "plugin": plugin_name,
                    "component": component,
                    "layout": layout,
                    "props": props,
                }
            )

        page_view.__name__ = f"plugin_{plugin_name}_{component}_page"
        return page_view

    # ------------------------------------------------------------------
    # Endpoints — authenticated JSON API
    # ------------------------------------------------------------------

    def _register_endpoints(
        self, plugin_name: str, endpoints: dict, prefix: str
    ) -> None:
        if not endpoints:
            return

        for signature, definition in endpoints.items():
            http_method, ep_path = self._parse_signature(signature)
            if http_method is None:
                continue

            capability = (definition or {}).get("capability") if isinstance(definition, dict) else None
            url_pattern = f"{prefix}/api/plugins/{plugin_name}/{ep_path.lstrip('/')}"
            view = self._make_endpoint_view(plugin_name, http_method, ep_path, capability)
            slug = f"{http_method.lower()}{ep_path.replace('/', '.')}"
            name = f"escalated.plugin.{plugin_name}.endpoint.{slug}"

            self._url_patterns.append(path(url_pattern, view, name=name))
            logger.debug(
                "Escalated PluginBridge: registered endpoint %s /%s (plugin %s)",
                http_method,
                url_pattern,
                plugin_name,
            )

    def _make_endpoint_view(
        self,
        plugin_name: str,
        http_method: str,
        ep_path: str,
        capability: str | None,
    ):
        bridge = self._bridge

        @csrf_exempt
        def endpoint_view(request, **kwargs):
            from django.http import HttpResponseForbidden, HttpResponseNotAllowed

            if request.method.upper() != http_method:
                return HttpResponseNotAllowed([http_method])

            if not request.user.is_authenticated:
                return JsonResponse({"detail": "Authentication required."}, status=401)

            if not getattr(request.user, "is_staff", False):
                return HttpResponseForbidden("Admin access required.")

            if capability and not request.user.has_perm(capability):
                return HttpResponseForbidden(f"Missing permission: {capability}")

            try:
                import json as _json
                try:
                    body = _json.loads(request.body) if request.body else {}
                except ValueError:
                    body = {}

                result = bridge.call_endpoint(
                    plugin_name,
                    http_method,
                    ep_path,
                    {
                        "body": body,
                        "params": dict(request.GET),
                        "headers": dict(request.headers),
                    },
                )
                return JsonResponse(result if isinstance(result, (dict, list)) else {"result": result}, safe=False)
            except RuntimeError as exc:
                return JsonResponse({"detail": str(exc)}, status=503)
            except Exception as exc:
                logger.exception(
                    "Escalated PluginBridge: endpoint %s %s raised: %s",
                    http_method,
                    ep_path,
                    exc,
                )
                return JsonResponse({"detail": "Internal plugin error."}, status=500)

        endpoint_view.__name__ = f"plugin_{plugin_name}_{http_method.lower()}_{ep_path.replace('/', '_')}_endpoint"
        return endpoint_view

    # ------------------------------------------------------------------
    # Webhooks — public (no auth)
    # ------------------------------------------------------------------

    def _register_webhooks(
        self, plugin_name: str, webhooks: dict, prefix: str
    ) -> None:
        if not webhooks:
            return

        for signature, _definition in webhooks.items():
            http_method, wh_path = self._parse_signature(signature)
            if http_method is None:
                continue

            url_pattern = f"{prefix}/webhooks/plugins/{plugin_name}/{wh_path.lstrip('/')}"
            view = self._make_webhook_view(plugin_name, http_method, wh_path)
            slug = f"{http_method.lower()}{wh_path.replace('/', '.')}"
            name = f"escalated.plugin.{plugin_name}.webhook.{slug}"

            self._url_patterns.append(path(url_pattern, view, name=name))
            logger.debug(
                "Escalated PluginBridge: registered webhook %s /%s (plugin %s)",
                http_method,
                url_pattern,
                plugin_name,
            )

    def _make_webhook_view(
        self, plugin_name: str, http_method: str, wh_path: str
    ):
        bridge = self._bridge

        @csrf_exempt
        def webhook_view(request, **kwargs):
            from django.http import HttpResponseNotAllowed
            import json as _json

            if request.method.upper() != http_method:
                return HttpResponseNotAllowed([http_method])

            try:
                try:
                    body = _json.loads(request.body) if request.body else {}
                except ValueError:
                    body = {}

                result = bridge.call_webhook(
                    plugin_name,
                    http_method,
                    wh_path,
                    body,
                    dict(request.headers),
                )
                return JsonResponse(
                    result if isinstance(result, (dict, list)) else (result or {}),
                    safe=False,
                )
            except RuntimeError as exc:
                return JsonResponse({"detail": str(exc)}, status=503)
            except Exception as exc:
                logger.exception(
                    "Escalated PluginBridge: webhook %s %s raised: %s",
                    http_method,
                    wh_path,
                    exc,
                )
                return JsonResponse({"detail": "Internal plugin error."}, status=500)

        webhook_view.__name__ = f"plugin_{plugin_name}_{http_method.lower()}_{wh_path.replace('/', '_')}_webhook"
        return webhook_view

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_signature(signature: str) -> tuple[str | None, str]:
        """
        Parse an endpoint signature like "GET /settings" into (method, path).

        Returns (None, "/") if the signature is invalid.
        """
        parts = signature.strip().split(" ", 1)
        if len(parts) != 2:
            logger.warning(
                "Escalated PluginBridge: could not parse endpoint signature '%s'",
                signature,
            )
            return None, "/"

        method = parts[0].upper()
        ep_path = parts[1]

        if method not in VALID_HTTP_METHODS:
            logger.warning(
                "Escalated PluginBridge: unsupported HTTP method '%s' in '%s'",
                method,
                signature,
            )
            return None, ep_path

        return method, ep_path
