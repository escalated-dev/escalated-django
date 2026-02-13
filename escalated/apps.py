from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class EscalatedConfig(AppConfig):
    name = "escalated"
    verbose_name = _("Escalated Support")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        import escalated.handlers  # noqa: F401 - connects signal handlers
