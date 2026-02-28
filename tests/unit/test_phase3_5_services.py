import pytest
from unittest.mock import patch, MagicMock

from escalated.services.capacity_service import CapacityService
from escalated.services.two_factor_service import TwoFactorService
from escalated.services.sso_service import SsoService
from escalated.services.automation_runner import AutomationRunner
from escalated.models import AgentCapacity, Ticket, Reply, Tag, Automation
from tests.factories import (
    UserFactory, TicketFactory, TagFactory, AgentCapacityFactory,
    AutomationFactory, SkillFactory,
)


# ---------------------------------------------------------------------------
# Capacity Service
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCapacityService:
    def setup_method(self):
        self.service = CapacityService()

    def test_can_accept_ticket_true(self):
        user = UserFactory()
        AgentCapacityFactory(user=user, max_concurrent=5, current_count=2)
        assert self.service.can_accept_ticket(user.pk) is True

    def test_can_accept_ticket_false(self):
        user = UserFactory()
        AgentCapacityFactory(user=user, max_concurrent=5, current_count=5)
        assert self.service.can_accept_ticket(user.pk) is False

    def test_can_accept_ticket_creates_default(self):
        user = UserFactory()
        assert self.service.can_accept_ticket(user.pk) is True
        assert AgentCapacity.objects.filter(user=user).exists()

    def test_increment_load(self):
        user = UserFactory()
        AgentCapacityFactory(user=user, current_count=0)
        self.service.increment_load(user.pk)

        cap = AgentCapacity.objects.get(user=user, channel="default")
        assert cap.current_count == 1

    def test_decrement_load(self):
        user = UserFactory()
        AgentCapacityFactory(user=user, current_count=3)
        self.service.decrement_load(user.pk)

        cap = AgentCapacity.objects.get(user=user, channel="default")
        assert cap.current_count == 2

    def test_decrement_load_floor_zero(self):
        user = UserFactory()
        AgentCapacityFactory(user=user, current_count=0)
        self.service.decrement_load(user.pk)

        cap = AgentCapacity.objects.get(user=user, channel="default")
        assert cap.current_count == 0

    def test_get_all_capacities(self):
        AgentCapacityFactory()
        AgentCapacityFactory()
        capacities = self.service.get_all_capacities()
        assert capacities.count() == 2


# ---------------------------------------------------------------------------
# Two Factor Service
# ---------------------------------------------------------------------------


class TestTwoFactorService:
    def setup_method(self):
        self.service = TwoFactorService()

    def test_generate_secret(self):
        secret = self.service.generate_secret()
        assert isinstance(secret, str)
        assert len(secret) == 16

    def test_generate_qr_uri(self):
        uri = self.service.generate_qr_uri("JBSWY3DPEHPK3PXP", "user@example.com")
        assert uri.startswith("otpauth://totp/")
        assert "user@example.com" in uri
        assert "JBSWY3DPEHPK3PXP" in uri

    def test_verify_valid_code(self):
        secret = self.service.generate_secret()
        # Generate a code for the current time step
        import time
        time_step = int(time.time()) // 30
        code = self.service._generate_totp(secret, time_step)
        assert self.service.verify(secret, code) is True

    def test_verify_invalid_code(self):
        secret = self.service.generate_secret()
        assert self.service.verify(secret, "000000") is False

    def test_generate_recovery_codes(self):
        codes = self.service.generate_recovery_codes()
        assert len(codes) == 8
        for code in codes:
            assert "-" in code
            parts = code.split("-")
            assert len(parts) == 2
            assert len(parts[0]) == 8
            assert len(parts[1]) == 8


# ---------------------------------------------------------------------------
# SSO Service
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSsoService:
    def setup_method(self):
        self.service = SsoService()

    def test_get_config_defaults(self):
        config = self.service.get_config()
        assert config["sso_provider"] == "none"
        assert config["sso_jwt_algorithm"] == "HS256"

    def test_save_and_get_config(self):
        self.service.save_config({"sso_provider": "saml", "sso_entity_id": "test-entity"})
        config = self.service.get_config()
        assert config["sso_provider"] == "saml"
        assert config["sso_entity_id"] == "test-entity"

    def test_is_enabled_false_by_default(self):
        assert self.service.is_enabled() is False

    def test_is_enabled_true(self):
        self.service.save_config({"sso_provider": "jwt"})
        assert self.service.is_enabled() is True

    def test_get_provider(self):
        assert self.service.get_provider() == "none"
        self.service.save_config({"sso_provider": "saml"})
        assert self.service.get_provider() == "saml"


# ---------------------------------------------------------------------------
# Automation Runner
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAutomationRunner:
    def setup_method(self):
        self.runner = AutomationRunner()

    def test_run_changes_status(self):
        ticket = TicketFactory(status="open")
        AutomationFactory(
            conditions=[{"field": "status", "value": "open"}],
            actions=[{"type": "change_status", "value": "in_progress"}],
            active=True,
        )

        affected = self.runner.run()
        assert affected >= 1

        ticket.refresh_from_db()
        assert ticket.status == "in_progress"

    def test_run_adds_tag(self):
        ticket = TicketFactory(status="open")
        tag = TagFactory(name="urgent", slug="urgent-auto")
        AutomationFactory(
            conditions=[{"field": "status", "value": "open"}],
            actions=[{"type": "add_tag", "value": "urgent"}],
            active=True,
        )

        self.runner.run()
        assert tag in ticket.tags.all()

    def test_run_adds_note(self):
        ticket = TicketFactory(status="open")
        AutomationFactory(
            conditions=[{"field": "status", "value": "open"}],
            actions=[{"type": "add_note", "value": "Auto follow-up"}],
            active=True,
        )

        self.runner.run()
        notes = Reply.objects.filter(ticket=ticket, is_internal_note=True)
        assert notes.filter(body="Auto follow-up").exists()

    def test_run_skips_inactive(self):
        TicketFactory(status="open")
        AutomationFactory(
            conditions=[{"field": "status", "value": "open"}],
            actions=[{"type": "change_status", "value": "closed"}],
            active=False,
        )

        affected = self.runner.run()
        assert affected == 0

    def test_run_filters_unassigned(self):
        t_unassigned = TicketFactory(status="open", assigned_to=None)
        t_assigned = TicketFactory(status="open", assigned_to=UserFactory())
        AutomationFactory(
            conditions=[{"field": "assigned", "value": "unassigned"}],
            actions=[{"type": "change_priority", "value": "high"}],
            active=True,
        )

        self.runner.run()
        t_unassigned.refresh_from_db()
        t_assigned.refresh_from_db()
        assert t_unassigned.priority == "high"
        # assigned ticket should not be changed
        assert t_assigned.priority != "high"

    def test_run_updates_last_run_at(self):
        AutomationFactory(active=True)
        self.runner.run()
        automation = Automation.objects.first()
        assert automation.last_run_at is not None
