"""Integration tests for custom ticket actions (host-defined action buttons)."""

import json

import pytest

from escalated.action_registry import registry
from escalated.signals import custom_action_triggered
from escalated.views import api

from ..factories import ApiTokenFactory, DepartmentFactory, TicketFactory, UserFactory


def _api_post(rf, path, user, api_token, data=None):
    request = rf.post(path, data=json.dumps(data or {}), content_type="application/json")
    request.user = user
    request.api_token = api_token
    return request


def _api_get(rf, path, user, api_token):
    request = rf.get(path)
    request.user = user
    request.api_token = api_token
    return request


@pytest.fixture
def agent_user():
    user = UserFactory(username="custom_action_agent")
    department = DepartmentFactory()
    department.agents.add(user)
    return user


@pytest.fixture(autouse=True)
def _clear_registry():
    registry.clear()
    yield
    registry.clear()


@pytest.mark.django_db
class TestCustomTicketActions:
    def test_detail_response_exposes_visible_actions(self, rf, agent_user):
        registry.register({"key": "sync-crm", "label": "Sync CRM", "variant": "primary"})
        token = ApiTokenFactory(user=agent_user, abilities=["agent"])
        ticket = TicketFactory(requester=agent_user)

        request = _api_get(rf, f"/api/tickets/{ticket.reference}/", agent_user, token)
        response = api.ticket_show(request, ticket.reference)

        assert response.status_code == 200
        actions = json.loads(response.content)["data"]["custom_actions"]
        assert len(actions) == 1
        assert actions[0]["key"] == "sync-crm"
        assert actions[0]["method"] == "post"
        assert "/actions/sync-crm" in actions[0]["url"]

    def test_trigger_sends_signal(self, rf, agent_user):
        registry.register({"key": "sync-crm", "label": "Sync CRM"})
        token = ApiTokenFactory(user=agent_user, abilities=["agent"])
        ticket = TicketFactory(requester=agent_user)

        received = []

        def _receiver(sender, **kwargs):
            received.append(kwargs)

        custom_action_triggered.connect(_receiver, weak=False)
        try:
            request = _api_post(
                rf,
                f"/api/tickets/{ticket.reference}/actions/sync-crm/",
                agent_user,
                token,
                {"payload": {"force": True}},
            )
            response = api.ticket_custom_action(request, ticket.reference, "sync-crm")
        finally:
            custom_action_triggered.disconnect(_receiver)

        assert response.status_code == 200
        assert len(received) == 1
        assert received[0]["action_key"] == "sync-crm"
        assert received[0]["payload"] == {"force": True}

    def test_unknown_action_returns_404(self, rf, agent_user):
        token = ApiTokenFactory(user=agent_user, abilities=["agent"])
        ticket = TicketFactory(requester=agent_user)

        request = _api_post(rf, f"/api/tickets/{ticket.reference}/actions/nope/", agent_user, token)
        response = api.ticket_custom_action(request, ticket.reference, "nope")

        assert response.status_code == 404

    def test_disabled_action_returns_403(self, rf, agent_user):
        registry.register({"key": "sync-crm", "label": "Sync CRM", "enabled": False})
        token = ApiTokenFactory(user=agent_user, abilities=["agent"])
        ticket = TicketFactory(requester=agent_user)

        request = _api_post(rf, f"/api/tickets/{ticket.reference}/actions/sync-crm/", agent_user, token)
        response = api.ticket_custom_action(request, ticket.reference, "sync-crm")

        assert response.status_code == 403

    def test_registry_visible_for_filters_and_marks_disabled(self):
        registry.register({"key": "hidden", "label": "Hidden", "visible": False})
        registry.register({"key": "locked", "label": "Locked", "enabled": False})

        actions = registry.visible_for(ticket=object(), user=object())

        assert [a["key"] for a in actions] == ["locked"]
        assert actions[0]["disabled"] is True
