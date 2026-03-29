import pytest
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from tests.factories import UserFactory, ApiTokenFactory, WebhookFactory


@pytest.mark.django_db
class TestInstallCommand:
    def test_no_input_runs_cleanly(self):
        out = StringIO()
        call_command("install", "--no-input", stdout=out)
        output = out.getvalue()
        assert "Installation complete" in output

    def test_seeds_permissions(self):
        from escalated.models import Permission

        out = StringIO()
        call_command("install", "--no-input", stdout=out)
        assert Permission.objects.count() > 0

    def test_creates_default_department(self):
        from escalated.models import Department

        out = StringIO()
        call_command("install", "--no-input", stdout=out)
        assert Department.objects.filter(slug="general").exists()

    def test_creates_default_sla_policy(self):
        from escalated.models import SlaPolicy

        out = StringIO()
        call_command("install", "--no-input", stdout=out)
        assert SlaPolicy.objects.filter(is_default=True).exists()

    def test_idempotent(self):
        out = StringIO()
        call_command("install", "--no-input", stdout=out)
        call_command("install", "--no-input", stdout=out)
        from escalated.models import Department

        assert Department.objects.filter(slug="general").count() == 1


@pytest.mark.django_db
class TestPurgeExpiredDataCommand:
    def test_dry_run(self):
        out = StringIO()
        call_command("purge_expired_data", "--dry-run", stdout=out)
        assert "DRY RUN" in out.getvalue()

    def test_purges_expired_tokens(self, db):
        from escalated.models import ApiToken

        user = UserFactory()
        expired = ApiTokenFactory(user=user)
        ApiToken.objects.filter(pk=expired.pk).update(
            expires_at=timezone.now() - timedelta(days=1)
        )

        out = StringIO()
        call_command("purge_expired_data", stdout=out)
        assert not ApiToken.objects.filter(pk=expired.pk).exists()

    def test_purges_old_webhook_deliveries(self, db):
        from escalated.models import WebhookDelivery

        webhook = WebhookFactory()
        old = WebhookDelivery.objects.create(
            webhook=webhook,
            event="ticket.created",
            payload={"test": True},
            response_code=200,
        )
        WebhookDelivery.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=60)
        )

        out = StringIO()
        call_command("purge_expired_data", "--days", "30", stdout=out)
        assert not WebhookDelivery.objects.filter(pk=old.pk).exists()

    def test_keeps_fresh_data(self, db):
        from escalated.models import ApiToken

        user = UserFactory()
        fresh = ApiTokenFactory(user=user)
        # No expiry set — should be kept
        out = StringIO()
        call_command("purge_expired_data", stdout=out)
        assert ApiToken.objects.filter(pk=fresh.pk).exists()


@pytest.mark.django_db
class TestPluginCommand:
    def test_list_empty(self):
        out = StringIO()
        call_command("plugin", "list", stdout=out)
        output = out.getvalue()
        assert "No plugins" in output or "0 plugins" in output.lower()

    def test_list_with_plugin(self, db):
        from escalated.plugin_models import EscalatedPlugin

        EscalatedPlugin.objects.create(slug="test-plugin", is_active=True)
        out = StringIO()
        call_command("plugin", "list", stdout=out)
        assert "test-plugin" in out.getvalue()

    def test_activate_nonexistent(self):
        with pytest.raises(CommandError, match="not found"):
            call_command("plugin", "activate", "nonexistent")

    def test_deactivate(self, db):
        from escalated.plugin_models import EscalatedPlugin

        EscalatedPlugin.objects.create(slug="test-plugin", is_active=True)
        out = StringIO()
        call_command("plugin", "deactivate", "test-plugin", stdout=out)
        plugin = EscalatedPlugin.objects.get(slug="test-plugin")
        assert plugin.is_active is False
