import logging

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger("escalated")


class EscalatedConfig(AppConfig):
    name = "escalated"
    verbose_name = _("Escalated Support")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        import escalated.handlers  # noqa: F401 - connects signal handlers
        import escalated.workflow_handlers  # noqa: F401 - connects WorkflowEngine to signals

        # Load active plugins on startup
        self._load_plugins()

        # Boot the SDK plugin bridge (Node.js runtime) if enabled
        self._boot_bridge()

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

    def _boot_bridge(self):
        """
        Boot the SDK plugin bridge (Node.js runtime).

        Wrapped in a try/except so a missing Node.js installation or a
        misconfigured runtime never prevents the Django app from starting.
        """
        try:
            from django.conf import settings

            from escalated.conf import get_setting

            escalated_settings = getattr(settings, "ESCALATED", {})

            # SDK bridge is opt-in — requires ESCALATED['SDK_ENABLED'] = True
            if not escalated_settings.get("SDK_ENABLED", False):
                return

            if not get_setting("PLUGINS_ENABLED"):
                return

            from escalated.bridge.plugin_bridge import get_bridge

            bridge = get_bridge()
            bridge.boot()
        except Exception as exc:
            logger.debug("Could not boot SDK plugin bridge on startup: %s", exc)
