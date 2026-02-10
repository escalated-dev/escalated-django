import logging

from django.apps import AppConfig

logger = logging.getLogger("escalated")


class EscalatedConfig(AppConfig):
    name = "escalated"
    verbose_name = "Escalated Support"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        import escalated.handlers  # noqa: F401 - connects signal handlers

        # Load active plugins on startup
        self._load_plugins()

    def _load_plugins(self):
        """
        Bootstrap the plugin system by loading all active plugins.

        Wrapped in a try/except so the application can still start even
        if the plugin table does not exist yet (e.g. before migrations).
        """
        try:
            from escalated.conf import get_setting

            if not get_setting("PLUGINS_ENABLED"):
                return

            from escalated.plugin_service import PluginService
            service = PluginService()
            service.load_active_plugins()
        except Exception as exc:
            logger.debug(
                "Could not load plugins on startup (migrations may not have run yet): %s",
                exc,
            )
