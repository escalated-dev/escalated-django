import pytest

from escalated.plugin_models import EscalatedPlugin


@pytest.mark.django_db
class TestPluginService:
    def test_get_activated_plugins(self):
        from escalated.plugin_service import PluginService

        EscalatedPlugin.objects.create(slug="active-plugin", is_active=True)
        EscalatedPlugin.objects.create(slug="inactive-plugin", is_active=False)
        service = PluginService()
        active = service.get_activated_plugins()
        assert "active-plugin" in active
        assert "inactive-plugin" not in active

    def test_activate_plugin(self):
        from escalated.plugin_service import PluginService

        EscalatedPlugin.objects.create(slug="test-plugin", is_active=False)
        service = PluginService()
        service.activate_plugin("test-plugin")
        plugin = EscalatedPlugin.objects.get(slug="test-plugin")
        assert plugin.is_active is True

    def test_deactivate_plugin(self):
        from escalated.plugin_service import PluginService

        EscalatedPlugin.objects.create(slug="test-plugin", is_active=True)
        service = PluginService()
        service.deactivate_plugin("test-plugin")
        plugin = EscalatedPlugin.objects.get(slug="test-plugin")
        assert plugin.is_active is False

    def test_get_all_plugins_returns_list(self):
        from escalated.plugin_service import PluginService

        service = PluginService()
        result = service.get_all_plugins()
        assert isinstance(result, list)
