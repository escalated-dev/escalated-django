"""
SDK plugin URLs sit inside ``include("escalated.urls")``, like every other
Escalated URL, as escalated-laravel's RouteRegistrar puts them under its
prefix: ``{prefix}/admin/plugins/...``, ``{prefix}/api/plugins/...`` and
``{prefix}/webhooks/plugins/...``. They used to repeat the prefix
(``/support/support/admin/plugins/...``).
"""

from unittest.mock import patch

from django.urls import reverse


class _Bridge:
    def get_plugin_urls(self):
        from escalated.bridge.route_registrar import RouteRegistrar

        registrar = RouteRegistrar(self)
        registrar.register_all(
            {
                "crm": {
                    "pages": [{"route": "settings", "component": "Settings"}],
                    "endpoints": {"GET /contacts": {}},
                    "webhooks": {"POST /incoming": {}},
                }
            }
        )
        return registrar.get_url_patterns()


def test_plugin_urls_are_under_the_include_once():
    from tests.embed_host import reload_urls

    try:
        with patch("escalated.bridge.plugin_bridge.get_bridge", return_value=_Bridge()):
            reload_urls()
            page = reverse("escalated:escalated.plugin.crm.page.settings")
            endpoint = reverse("escalated:escalated.plugin.crm.endpoint.get.contacts")
            webhook = reverse("escalated:escalated.plugin.crm.webhook.post.incoming")
    finally:
        reload_urls()

    assert page == "/support/admin/plugins/crm/settings"
    assert endpoint == "/support/api/plugins/crm/contacts"
    assert webhook == "/support/webhooks/plugins/crm/incoming"
