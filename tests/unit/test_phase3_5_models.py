import pytest
from django.db import IntegrityError

from escalated.models import (
    AgentProfile, Skill, AgentSkill, AgentCapacity,
    Webhook, WebhookDelivery, Automation,
    TwoFactor, CustomObject, CustomObjectRecord,
)
from tests.factories import (
    UserFactory, AgentProfileFactory, SkillFactory,
    AgentCapacityFactory, WebhookFactory, WebhookDeliveryFactory,
    AutomationFactory, TwoFactorFactory, CustomObjectFactory,
    CustomObjectRecordFactory,
)


# ---------------------------------------------------------------------------
# Phase 3: Agent & Routing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAgentProfileModel:
    def test_str_representation(self):
        user = UserFactory(username="agent_prof")
        profile = AgentProfileFactory(user=user)
        assert "agent_prof" in str(profile)

    def test_default_agent_type(self):
        profile = AgentProfileFactory()
        assert profile.agent_type == "full"

    def test_is_full_agent(self):
        profile = AgentProfileFactory(agent_type="full")
        assert profile.is_full_agent() is True
        assert profile.is_light_agent() is False

    def test_is_light_agent(self):
        profile = AgentProfileFactory(agent_type="light")
        assert profile.is_light_agent() is True
        assert profile.is_full_agent() is False

    def test_for_user_creates(self):
        user = UserFactory()
        profile = AgentProfile.for_user(user.pk)
        assert profile.user_id == user.pk
        assert profile.agent_type == "full"

    def test_for_user_returns_existing(self):
        user = UserFactory()
        p1 = AgentProfile.for_user(user.pk)
        p2 = AgentProfile.for_user(user.pk)
        assert p1.pk == p2.pk

    def test_unique_user(self):
        user = UserFactory()
        AgentProfileFactory(user=user)
        with pytest.raises(IntegrityError):
            AgentProfileFactory(user=user)


@pytest.mark.django_db
class TestSkillModel:
    def test_str_returns_name(self):
        skill = SkillFactory(name="Python")
        assert str(skill) == "Python"

    def test_auto_generates_slug(self):
        skill = SkillFactory(name="Customer Service", slug="")
        assert skill.slug != ""

    def test_agents_m2m(self):
        skill = SkillFactory(slug="skill-m2m")
        user = UserFactory()
        AgentSkill.objects.create(user=user, skill=skill, proficiency=3)

        assert user in skill.agents.all()

    def test_agent_skill_unique_together(self):
        skill = SkillFactory(slug="skill-uniq")
        user = UserFactory()
        AgentSkill.objects.create(user=user, skill=skill, proficiency=1)

        with pytest.raises(IntegrityError):
            AgentSkill.objects.create(user=user, skill=skill, proficiency=2)


@pytest.mark.django_db
class TestAgentCapacityModel:
    def test_has_capacity_true(self):
        cap = AgentCapacityFactory(max_concurrent=5, current_count=3)
        assert cap.has_capacity() is True

    def test_has_capacity_false(self):
        cap = AgentCapacityFactory(max_concurrent=5, current_count=5)
        assert cap.has_capacity() is False

    def test_load_percentage(self):
        cap = AgentCapacityFactory(max_concurrent=10, current_count=3)
        assert cap.load_percentage() == 30.0

    def test_load_percentage_zero_max(self):
        cap = AgentCapacityFactory(max_concurrent=0, current_count=0)
        assert cap.load_percentage() == 100.0

    def test_unique_together(self):
        user = UserFactory()
        AgentCapacityFactory(user=user, channel="default")
        with pytest.raises(IntegrityError):
            AgentCapacityFactory(user=user, channel="default")

    def test_default_values(self):
        cap = AgentCapacityFactory()
        assert cap.max_concurrent == 10
        assert cap.current_count == 0
        assert cap.channel == "default"


# ---------------------------------------------------------------------------
# Phase 4: Automation & Integration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWebhookModel:
    def test_str_returns_url(self):
        wh = WebhookFactory(url="https://example.com/hook")
        assert str(wh) == "https://example.com/hook"

    def test_subscribed_to(self):
        wh = WebhookFactory(events=["ticket.created", "ticket.updated"])
        assert wh.subscribed_to("ticket.created") is True
        assert wh.subscribed_to("ticket.deleted") is False

    def test_active_scope(self):
        active = WebhookFactory(active=True)
        inactive = WebhookFactory(active=False)

        active_webhooks = list(Webhook.objects.active())
        assert active in active_webhooks
        assert inactive not in active_webhooks

    def test_deliveries_relationship(self):
        wh = WebhookFactory()
        d1 = WebhookDeliveryFactory(webhook=wh)
        d2 = WebhookDeliveryFactory(webhook=wh)

        assert wh.deliveries.count() == 2
        assert d1 in wh.deliveries.all()


@pytest.mark.django_db
class TestWebhookDeliveryModel:
    def test_is_success_true(self):
        d = WebhookDeliveryFactory(response_code=200)
        assert d.is_success() is True

    def test_is_success_201(self):
        d = WebhookDeliveryFactory(response_code=201)
        assert d.is_success() is True

    def test_is_success_false_400(self):
        d = WebhookDeliveryFactory(response_code=400)
        assert d.is_success() is False

    def test_is_success_false_500(self):
        d = WebhookDeliveryFactory(response_code=500)
        assert d.is_success() is False

    def test_is_success_false_none(self):
        d = WebhookDeliveryFactory(response_code=None)
        assert d.is_success() is False

    def test_cascade_delete_with_webhook(self):
        wh = WebhookFactory()
        WebhookDeliveryFactory(webhook=wh)
        wh_pk = wh.pk
        wh.delete()
        assert not WebhookDelivery.objects.filter(webhook_id=wh_pk).exists()


@pytest.mark.django_db
class TestAutomationModel:
    def test_str_returns_name(self):
        a = AutomationFactory(name="Auto Close Old Tickets")
        assert str(a) == "Auto Close Old Tickets"

    def test_active_scope(self):
        active = AutomationFactory(active=True, position=1)
        inactive = AutomationFactory(active=False, position=0)

        active_list = list(Automation.objects.active())
        assert active in active_list
        assert inactive not in active_list

    def test_active_scope_ordered_by_position(self):
        a2 = AutomationFactory(active=True, position=2)
        a1 = AutomationFactory(active=True, position=1)

        active_list = list(Automation.objects.active())
        assert active_list[0] == a1
        assert active_list[1] == a2

    def test_json_conditions_and_actions(self):
        a = AutomationFactory(
            conditions=[{"field": "status", "value": "open"}],
            actions=[{"type": "add_note", "value": "Follow up needed"}],
        )
        a.refresh_from_db()
        assert a.conditions == [{"field": "status", "value": "open"}]
        assert a.actions == [{"type": "add_note", "value": "Follow up needed"}]


# ---------------------------------------------------------------------------
# Phase 5: Security & Enterprise
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTwoFactorModel:
    def test_is_confirmed_false(self):
        tf = TwoFactorFactory(confirmed_at=None)
        assert tf.is_confirmed() is False

    def test_is_confirmed_true(self):
        from django.utils import timezone
        tf = TwoFactorFactory(confirmed_at=timezone.now())
        assert tf.is_confirmed() is True

    def test_unique_user(self):
        user = UserFactory()
        TwoFactorFactory(user=user)
        with pytest.raises(IntegrityError):
            TwoFactorFactory(user=user)

    def test_stores_recovery_codes(self):
        tf = TwoFactorFactory(recovery_codes=["CODE1-CODE2", "CODE3-CODE4"])
        tf.refresh_from_db()
        assert tf.recovery_codes == ["CODE1-CODE2", "CODE3-CODE4"]


@pytest.mark.django_db
class TestCustomObjectModel:
    def test_str_returns_name(self):
        obj = CustomObjectFactory(name="Company")
        assert str(obj) == "Company"

    def test_fields_schema_json(self):
        schema = [
            {"name": "name", "type": "text", "required": True},
            {"name": "size", "type": "number", "required": False},
        ]
        obj = CustomObjectFactory(fields_schema=schema)
        obj.refresh_from_db()
        assert obj.fields_schema == schema

    def test_records_relationship(self):
        obj = CustomObjectFactory()
        r1 = CustomObjectRecordFactory(object=obj)
        r2 = CustomObjectRecordFactory(object=obj)

        assert obj.records.count() == 2
        assert r1 in obj.records.all()

    def test_cascade_delete(self):
        obj = CustomObjectFactory()
        CustomObjectRecordFactory(object=obj)
        obj_pk = obj.pk
        obj.delete()
        assert not CustomObjectRecord.objects.filter(object_id=obj_pk).exists()


@pytest.mark.django_db
class TestCustomObjectRecordModel:
    def test_data_json(self):
        record = CustomObjectRecordFactory(data={"name": "Acme", "size": 100})
        record.refresh_from_db()
        assert record.data == {"name": "Acme", "size": 100}
