from django.apps import AppConfig


class EscalatedConfig(AppConfig):
    name = "escalated"
    verbose_name = "Escalated Support"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        import escalated.handlers  # noqa: F401 - connects signal handlers
