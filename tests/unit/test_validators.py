import json
import pytest
from django.test import RequestFactory

from escalated.validators import (
    CreateTicketValidator,
    UpdateTicketValidator,
    ReplyToTicketValidator,
    AssignTicketValidator,
    ChangeStatusValidator,
    ChangePriorityValidator,
    UpdateTagsValidator,
    BulkActionValidator,
    StoreDepartmentValidator,
    StoreTagValidator,
    StoreCannedResponseValidator,
    StoreMacroValidator,
    StoreSlaPolicyValidator,
    StoreEscalationRuleValidator,
)


@pytest.fixture
def rf():
    return RequestFactory()


def _make_request(rf, data):
    """Create a POST request with JSON body."""
    request = rf.post("/", json.dumps(data), content_type="application/json")
    return request


class TestCreateTicketValidator:
    def test_valid_input(self, rf):
        request = _make_request(rf, {"subject": "Help", "description": "I need help"})
        data, error = CreateTicketValidator.validate_request(request)
        assert error is None
        assert data["subject"] == "Help"
        assert data["description"] == "I need help"

    def test_missing_subject(self, rf):
        request = _make_request(rf, {"description": "I need help"})
        data, error = CreateTicketValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422

    def test_missing_description(self, rf):
        request = _make_request(rf, {"subject": "Help"})
        data, error = CreateTicketValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422

    def test_invalid_priority(self, rf):
        request = _make_request(rf, {
            "subject": "Help", "description": "I need help", "priority": "INVALID"
        })
        data, error = CreateTicketValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422

    def test_valid_priority(self, rf):
        request = _make_request(rf, {
            "subject": "Help", "description": "I need help", "priority": "high"
        })
        data, error = CreateTicketValidator.validate_request(request)
        assert error is None
        assert data["priority"] == "high"

    def test_default_priority(self, rf):
        request = _make_request(rf, {"subject": "Help", "description": "I need help"})
        data, error = CreateTicketValidator.validate_request(request)
        assert error is None
        assert data["priority"] == "medium"

    def test_empty_body(self, rf):
        request = rf.post("/", b"", content_type="application/json")
        data, error = CreateTicketValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422

    def test_invalid_json(self, rf):
        request = rf.post("/", b"not json", content_type="application/json")
        data, error = CreateTicketValidator.validate_request(request)
        assert data is None
        assert error.status_code == 400


class TestReplyToTicketValidator:
    def test_valid(self, rf):
        request = _make_request(rf, {"body": "Thanks for the help"})
        data, error = ReplyToTicketValidator.validate_request(request)
        assert error is None
        assert data["body"] == "Thanks for the help"
        assert data["is_internal_note"] is False

    def test_internal_note(self, rf):
        request = _make_request(rf, {"body": "Internal", "is_internal_note": True})
        data, error = ReplyToTicketValidator.validate_request(request)
        assert error is None
        assert data["is_internal_note"] is True

    def test_missing_body(self, rf):
        request = _make_request(rf, {})
        data, error = ReplyToTicketValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422


class TestChangeStatusValidator:
    def test_valid(self, rf):
        request = _make_request(rf, {"status": "resolved"})
        data, error = ChangeStatusValidator.validate_request(request)
        assert error is None
        assert data["status"] == "resolved"

    def test_invalid(self, rf):
        request = _make_request(rf, {"status": "nonexistent"})
        data, error = ChangeStatusValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422

    def test_missing(self, rf):
        request = _make_request(rf, {})
        data, error = ChangeStatusValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422


class TestChangePriorityValidator:
    def test_valid(self, rf):
        request = _make_request(rf, {"priority": "urgent"})
        data, error = ChangePriorityValidator.validate_request(request)
        assert error is None
        assert data["priority"] == "urgent"

    def test_invalid(self, rf):
        request = _make_request(rf, {"priority": "super_urgent"})
        data, error = ChangePriorityValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422


class TestAssignTicketValidator:
    def test_valid(self, rf):
        request = _make_request(rf, {"agent_id": 1})
        data, error = AssignTicketValidator.validate_request(request)
        assert error is None
        assert data["agent_id"] == 1

    def test_missing(self, rf):
        request = _make_request(rf, {})
        data, error = AssignTicketValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422


class TestUpdateTagsValidator:
    def test_valid(self, rf):
        request = _make_request(rf, {"tag_ids": [1, 2, 3]})
        data, error = UpdateTagsValidator.validate_request(request)
        assert error is None
        assert data["tag_ids"] == [1, 2, 3]

    def test_not_a_list(self, rf):
        request = _make_request(rf, {"tag_ids": "not a list"})
        data, error = UpdateTagsValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422

    def test_missing(self, rf):
        request = _make_request(rf, {})
        data, error = UpdateTagsValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422


class TestStoreTagValidator:
    def test_valid(self, rf):
        request = _make_request(rf, {"name": "bug", "color": "#ef4444"})
        data, error = StoreTagValidator.validate_request(request)
        assert error is None
        assert data["name"] == "bug"
        assert data["color"] == "#ef4444"

    def test_invalid_hex_color(self, rf):
        request = _make_request(rf, {"name": "bug", "color": "not-a-color"})
        data, error = StoreTagValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422

    def test_missing_name(self, rf):
        request = _make_request(rf, {"color": "#ef4444"})
        data, error = StoreTagValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422


class TestStoreDepartmentValidator:
    def test_valid(self, rf):
        request = _make_request(rf, {"name": "Support"})
        data, error = StoreDepartmentValidator.validate_request(request)
        assert error is None
        assert data["name"] == "Support"

    def test_missing_name(self, rf):
        request = _make_request(rf, {})
        data, error = StoreDepartmentValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422


class TestStoreCannedResponseValidator:
    def test_valid(self, rf):
        request = _make_request(rf, {"title": "Greeting", "body": "Hello!"})
        data, error = StoreCannedResponseValidator.validate_request(request)
        assert error is None

    def test_missing_body(self, rf):
        request = _make_request(rf, {"title": "Greeting"})
        data, error = StoreCannedResponseValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422


class TestStoreMacroValidator:
    def test_valid(self, rf):
        request = _make_request(rf, {
            "name": "Close and Tag",
            "actions": [{"type": "change_status", "value": "closed"}],
        })
        data, error = StoreMacroValidator.validate_request(request)
        assert error is None

    def test_empty_actions(self, rf):
        request = _make_request(rf, {"name": "Empty", "actions": []})
        data, error = StoreMacroValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422


class TestStoreSlaPolicyValidator:
    def test_valid(self, rf):
        request = _make_request(rf, {
            "name": "Default SLA",
            "first_response_hours": {"low": 24, "medium": 8, "high": 4, "urgent": 1, "critical": 0.5},
            "resolution_hours": {"low": 72, "medium": 24, "high": 8, "urgent": 4, "critical": 2},
        })
        data, error = StoreSlaPolicyValidator.validate_request(request)
        assert error is None

    def test_missing_name(self, rf):
        request = _make_request(rf, {
            "first_response_hours": {"low": 24},
            "resolution_hours": {"low": 72},
        })
        data, error = StoreSlaPolicyValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422


class TestStoreEscalationRuleValidator:
    def test_valid(self, rf):
        request = _make_request(rf, {
            "trigger_type": "time_based",
            "conditions": [{"field": "priority", "operator": "eq", "value": "critical"}],
            "actions": [{"type": "assign", "value": 1}],
        })
        data, error = StoreEscalationRuleValidator.validate_request(request)
        assert error is None

    def test_invalid_trigger_type(self, rf):
        request = _make_request(rf, {
            "trigger_type": "invalid",
            "conditions": [],
            "actions": [],
        })
        data, error = StoreEscalationRuleValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422


class TestBulkActionValidator:
    def test_valid(self, rf):
        request = _make_request(rf, {
            "ticket_ids": [1, 2, 3],
            "action": "change_status",
            "value": "closed",
        })
        data, error = BulkActionValidator.validate_request(request)
        assert error is None

    def test_missing_ticket_ids(self, rf):
        request = _make_request(rf, {"action": "change_status"})
        data, error = BulkActionValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422

    def test_invalid_action(self, rf):
        request = _make_request(rf, {"ticket_ids": [1], "action": "destroy_everything"})
        data, error = BulkActionValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422


class TestUpdateTicketValidator:
    def test_all_optional(self, rf):
        request = _make_request(rf, {})
        data, error = UpdateTicketValidator.validate_request(request)
        assert error is None

    def test_partial_update(self, rf):
        request = _make_request(rf, {"subject": "Updated subject"})
        data, error = UpdateTicketValidator.validate_request(request)
        assert error is None
        assert data["subject"] == "Updated subject"

    def test_invalid_priority(self, rf):
        request = _make_request(rf, {"priority": "INVALID"})
        data, error = UpdateTicketValidator.validate_request(request)
        assert data is None
        assert error.status_code == 422
