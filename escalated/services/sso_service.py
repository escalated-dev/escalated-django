class SsoService:
    CONFIG_KEYS = [
        "sso_provider",
        "sso_entity_id",
        "sso_url",
        "sso_certificate",
        "sso_attr_email",
        "sso_attr_name",
        "sso_attr_role",
        "sso_jwt_secret",
        "sso_jwt_algorithm",
    ]

    DEFAULTS = {
        "sso_provider": "none",
        "sso_entity_id": "",
        "sso_url": "",
        "sso_certificate": "",
        "sso_attr_email": "email",
        "sso_attr_name": "name",
        "sso_attr_role": "role",
        "sso_jwt_secret": "",
        "sso_jwt_algorithm": "HS256",
    }

    def get_config(self):
        """Get all SSO configuration values."""
        from escalated.models import EscalatedSetting

        config = {}
        for key in self.CONFIG_KEYS:
            try:
                setting = EscalatedSetting.objects.get(key=key)
                config[key] = setting.value
            except EscalatedSetting.DoesNotExist:
                config[key] = self.DEFAULTS.get(key, "")
        return config

    def save_config(self, data):
        """Save SSO configuration values."""
        from escalated.models import EscalatedSetting

        for key in self.CONFIG_KEYS:
            if key in data:
                EscalatedSetting.objects.update_or_create(
                    key=key,
                    defaults={"value": data[key]},
                )

    def is_enabled(self):
        """Check if SSO is enabled (provider != 'none')."""
        return self.get_provider() != "none"

    def get_provider(self):
        """Get the current SSO provider."""
        from escalated.models import EscalatedSetting

        try:
            return EscalatedSetting.objects.get(key="sso_provider").value
        except EscalatedSetting.DoesNotExist:
            return "none"
