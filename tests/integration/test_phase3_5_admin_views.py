import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from escalated.models import (
    Automation,
    CustomObject,
    CustomObjectRecord,
    Skill,
    TwoFactor,
    Webhook,
)
from escalated.views import admin
from tests.factories import (
    AgentCapacityFactory,
    AutomationFactory,
    CustomObjectFactory,
    CustomObjectRecordFactory,
    SkillFactory,
    TwoFactorFactory,
    UserFactory,
    WebhookDeliveryFactory,
    WebhookFactory,
)


@pytest.fixture
def rf():
    return RequestFactory()


def _make_admin_request(rf, method, path, data=None, user=None, content_type=None):
    if user is None:
        user = UserFactory(username="admin_p35", is_staff=True, is_superuser=True)
    if method == "GET":
        request = rf.get(path)
    elif content_type == "application/json":
        request = rf.post(
            path,
            data=json.dumps(data or {}),
            content_type="application/json",
        )
    else:
        request = rf.post(path, data=data or {})
    request.user = user
    from django.contrib.sessions.backends.db import SessionStore

    request.session = SessionStore()
    return request


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSkillsAdminViews:
    @patch("escalated.views.admin.render_page")
    def test_index_returns_skills(self, mock_render, rf):
        SkillFactory(slug="skill-idx-test")
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", "/admin/skills/")
        admin.skills_index(request)

        mock_render.assert_called_once()
        args = mock_render.call_args
        assert args[0][1] == "Escalated/Admin/Skills/Index"
        props = args[1]["props"] if "props" in args[1] else args[0][2]
        assert "skills" in props

    def test_create_post(self, rf):
        request = _make_admin_request(
            rf,
            "POST",
            "/admin/skills/create/",
            data={
                "name": "Networking",
            },
        )
        response = admin.skills_create(request)
        assert response.status_code == 302
        assert Skill.objects.filter(name="Networking").exists()

    def test_edit_post(self, rf):
        skill = SkillFactory(name="Old Skill", slug="old-skill")
        request = _make_admin_request(
            rf,
            "POST",
            f"/admin/skills/{skill.pk}/edit/",
            data={
                "name": "New Skill",
            },
        )
        response = admin.skills_edit(request, skill.pk)
        assert response.status_code == 302
        skill.refresh_from_db()
        assert skill.name == "New Skill"

    def test_delete(self, rf):
        skill = SkillFactory(slug="skill-to-del")
        request = _make_admin_request(rf, "POST", f"/admin/skills/{skill.pk}/delete/")
        response = admin.skills_delete(request, skill.pk)
        assert response.status_code == 302
        assert not Skill.objects.filter(pk=skill.pk).exists()


# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCapacityAdminViews:
    @patch("escalated.views.admin.render_page")
    def test_index_returns_capacities(self, mock_render, rf):
        AgentCapacityFactory()
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", "/admin/capacity/")
        admin.capacity_index(request)

        mock_render.assert_called_once()
        props = (
            mock_render.call_args[1]["props"] if "props" in mock_render.call_args[1] else mock_render.call_args[0][2]
        )
        assert "capacities" in props

    def test_update(self, rf):
        cap = AgentCapacityFactory(max_concurrent=5)
        request = _make_admin_request(
            rf,
            "POST",
            f"/admin/capacity/{cap.pk}/update/",
            data={
                "max_concurrent": "20",
            },
        )
        response = admin.capacity_update(request, cap.pk)
        assert response.status_code == 302
        cap.refresh_from_db()
        assert cap.max_concurrent == 20


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWebhooksAdminViews:
    @patch("escalated.views.admin.render_page")
    def test_index_returns_webhooks(self, mock_render, rf):
        WebhookFactory()
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", "/admin/webhooks/")
        admin.webhooks_index(request)

        mock_render.assert_called_once()
        props = (
            mock_render.call_args[1]["props"] if "props" in mock_render.call_args[1] else mock_render.call_args[0][2]
        )
        assert "webhooks" in props
        assert "available_events" in props

    def test_create_post(self, rf):
        request = _make_admin_request(
            rf,
            "POST",
            "/admin/webhooks/create/",
            data={
                "url": "https://example.com/hook",
                "events": json.dumps(["ticket.created"]),
                "active": "true",
            },
        )
        response = admin.webhooks_create(request)
        assert response.status_code == 302
        assert Webhook.objects.filter(url="https://example.com/hook").exists()

    def test_edit_post(self, rf):
        wh = WebhookFactory(url="https://old.com/hook")
        request = _make_admin_request(
            rf,
            "POST",
            f"/admin/webhooks/{wh.pk}/edit/",
            data={
                "url": "https://new.com/hook",
                "events": json.dumps(["ticket.updated"]),
                "active": "true",
            },
        )
        response = admin.webhooks_edit(request, wh.pk)
        assert response.status_code == 302
        wh.refresh_from_db()
        assert wh.url == "https://new.com/hook"

    def test_delete(self, rf):
        wh = WebhookFactory()
        request = _make_admin_request(rf, "POST", f"/admin/webhooks/{wh.pk}/delete/")
        response = admin.webhooks_delete(request, wh.pk)
        assert response.status_code == 302
        assert not Webhook.objects.filter(pk=wh.pk).exists()

    @patch("escalated.views.admin.render_page")
    def test_deliveries(self, mock_render, rf):
        wh = WebhookFactory()
        WebhookDeliveryFactory(webhook=wh)
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", f"/admin/webhooks/{wh.pk}/deliveries/")
        admin.webhooks_deliveries(request, wh.pk)

        mock_render.assert_called_once()
        props = (
            mock_render.call_args[1]["props"] if "props" in mock_render.call_args[1] else mock_render.call_args[0][2]
        )
        assert "webhook" in props
        assert "deliveries" in props
        assert "pagination" in props


# ---------------------------------------------------------------------------
# Automations
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAutomationsAdminViews:
    @patch("escalated.views.admin.render_page")
    def test_index_returns_automations(self, mock_render, rf):
        AutomationFactory()
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", "/admin/automations/")
        admin.automations_index(request)

        mock_render.assert_called_once()
        props = (
            mock_render.call_args[1]["props"] if "props" in mock_render.call_args[1] else mock_render.call_args[0][2]
        )
        assert "automations" in props

    def test_create_post(self, rf):
        request = _make_admin_request(
            rf,
            "POST",
            "/admin/automations/create/",
            data={
                "name": "Auto-close",
                "conditions": json.dumps([{"field": "status", "value": "open"}]),
                "actions": json.dumps([{"type": "change_status", "value": "closed"}]),
                "active": "true",
            },
        )
        response = admin.automations_create(request)
        assert response.status_code == 302
        assert Automation.objects.filter(name="Auto-close").exists()

    def test_edit_post(self, rf):
        auto = AutomationFactory(name="Old Name")
        request = _make_admin_request(
            rf,
            "POST",
            f"/admin/automations/{auto.pk}/edit/",
            data={
                "name": "New Name",
                "conditions": json.dumps(auto.conditions),
                "actions": json.dumps(auto.actions),
                "active": "true",
            },
        )
        response = admin.automations_edit(request, auto.pk)
        assert response.status_code == 302
        auto.refresh_from_db()
        assert auto.name == "New Name"

    def test_delete(self, rf):
        auto = AutomationFactory()
        request = _make_admin_request(rf, "POST", f"/admin/automations/{auto.pk}/delete/")
        response = admin.automations_delete(request, auto.pk)
        assert response.status_code == 302
        assert not Automation.objects.filter(pk=auto.pk).exists()


# ---------------------------------------------------------------------------
# Two Factor Auth
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTwoFactorAdminViews:
    def test_setup_creates_two_factor(self, rf):
        user = UserFactory(username="2fa_admin", is_staff=True, is_superuser=True)
        request = _make_admin_request(rf, "POST", "/admin/settings/two-factor/setup/", user=user)

        response = admin.two_factor_setup(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "qr_uri" in data
        assert "recovery_codes" in data
        assert TwoFactor.objects.filter(user=user).exists()

    def test_confirm_validates_code(self, rf):
        user = UserFactory(username="2fa_confirm", is_staff=True, is_superuser=True)
        # First setup
        setup_request = _make_admin_request(rf, "POST", "/admin/settings/two-factor/setup/", user=user)
        admin.two_factor_setup(setup_request)

        # Try invalid code
        confirm_request = _make_admin_request(
            rf,
            "POST",
            "/admin/settings/two-factor/confirm/",
            data={"code": "000000"},
            user=user,
            content_type="application/json",
        )
        response = admin.two_factor_confirm(confirm_request)
        assert response.status_code == 400

    def test_disable_removes_two_factor(self, rf):
        user = UserFactory(username="2fa_disable", is_staff=True, is_superuser=True)
        TwoFactorFactory(user=user)

        request = _make_admin_request(rf, "POST", "/admin/settings/two-factor/disable/", user=user)
        response = admin.two_factor_disable(request)
        assert response.status_code == 200
        assert not TwoFactor.objects.filter(user=user).exists()


# ---------------------------------------------------------------------------
# Custom Objects
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCustomObjectsAdminViews:
    @patch("escalated.views.admin.render_page")
    def test_index_returns_objects(self, mock_render, rf):
        CustomObjectFactory()
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", "/admin/custom-objects/")
        admin.custom_objects_index(request)

        mock_render.assert_called_once()
        props = (
            mock_render.call_args[1]["props"] if "props" in mock_render.call_args[1] else mock_render.call_args[0][2]
        )
        assert "custom_objects" in props

    def test_create_post(self, rf):
        request = _make_admin_request(
            rf,
            "POST",
            "/admin/custom-objects/create/",
            data={
                "name": "Company",
                "slug": "company",
                "fields_schema": json.dumps([{"name": "name", "type": "text"}]),
            },
        )
        response = admin.custom_objects_create(request)
        assert response.status_code == 302
        assert CustomObject.objects.filter(name="Company").exists()

    def test_edit_post(self, rf):
        obj = CustomObjectFactory(name="Old Obj", slug="old-obj")
        request = _make_admin_request(
            rf,
            "POST",
            f"/admin/custom-objects/{obj.pk}/edit/",
            data={
                "name": "New Obj",
                "fields_schema": json.dumps([{"name": "updated", "type": "text"}]),
            },
        )
        response = admin.custom_objects_edit(request, obj.pk)
        assert response.status_code == 302
        obj.refresh_from_db()
        assert obj.name == "New Obj"

    def test_delete(self, rf):
        obj = CustomObjectFactory(slug="obj-to-del")
        request = _make_admin_request(rf, "POST", f"/admin/custom-objects/{obj.pk}/delete/")
        response = admin.custom_objects_delete(request, obj.pk)
        assert response.status_code == 302
        assert not CustomObject.objects.filter(pk=obj.pk).exists()

    @patch("escalated.views.admin.render_page")
    def test_records_list(self, mock_render, rf):
        obj = CustomObjectFactory()
        CustomObjectRecordFactory(object=obj)
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", f"/admin/custom-objects/{obj.pk}/records/")
        admin.custom_object_records(request, obj.pk)

        mock_render.assert_called_once()
        props = (
            mock_render.call_args[1]["props"] if "props" in mock_render.call_args[1] else mock_render.call_args[0][2]
        )
        assert "records" in props
        assert "custom_object" in props

    def test_records_store(self, rf):
        obj = CustomObjectFactory()
        request = _make_admin_request(
            rf,
            "POST",
            f"/admin/custom-objects/{obj.pk}/records/store/",
            data={"data": {"field1": "value1"}},
            content_type="application/json",
        )
        response = admin.custom_object_records_store(request, obj.pk)
        assert response.status_code == 200
        assert obj.records.count() == 1

    def test_records_update(self, rf):
        obj = CustomObjectFactory()
        record = CustomObjectRecordFactory(object=obj, data={"field1": "old"})
        request = _make_admin_request(
            rf,
            "POST",
            f"/admin/custom-objects/{obj.pk}/records/{record.pk}/update/",
            data={"data": {"field1": "new"}},
            content_type="application/json",
        )
        response = admin.custom_object_records_update(request, obj.pk, record.pk)
        assert response.status_code == 200
        record.refresh_from_db()
        assert record.data == {"field1": "new"}

    def test_records_delete(self, rf):
        obj = CustomObjectFactory()
        record = CustomObjectRecordFactory(object=obj)
        request = _make_admin_request(
            rf,
            "POST",
            f"/admin/custom-objects/{obj.pk}/records/{record.pk}/delete/",
        )
        response = admin.custom_object_records_delete(request, obj.pk, record.pk)
        assert response.status_code == 200
        assert not CustomObjectRecord.objects.filter(pk=record.pk).exists()

    def test_non_admin_forbidden(self, rf):
        user = UserFactory(username="nonadmin_co", is_staff=False)
        request = _make_admin_request(rf, "GET", "/admin/custom-objects/", user=user)
        response = admin.custom_objects_index(request)
        assert response.status_code == 403
