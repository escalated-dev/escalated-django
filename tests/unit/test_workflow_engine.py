from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from escalated.outbound_security import UnsafeOutboundUrl
from escalated.services.workflow_engine import WorkflowEngine

PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 443))]


@pytest.mark.django_db
class TestWorkflowEngine:
    def _create_ticket(self, **kwargs):
        from escalated.models import Ticket

        defaults = {
            "subject": "Test ticket",
            "description": "Test description",
            "status": "open",
            "priority": "medium",
        }
        defaults.update(kwargs)
        return Ticket.objects.create(**defaults)

    def _create_workflow(self, **kwargs):
        from escalated.workflow_models import Workflow

        defaults = {
            "name": "Test Workflow",
            "trigger_event": "ticket.created",
            "conditions": {"all": [{"field": "status", "operator": "equals", "value": "open"}]},
            "actions": [{"type": "change_priority", "value": "high"}],
            "is_active": True,
            "position": 0,
        }
        defaults.update(kwargs)
        return Workflow.objects.create(**defaults)

    def setup_method(self):
        self.engine = WorkflowEngine()

    def test_evaluate_and_conditions(self):
        ticket = self._create_ticket(status="open", priority="medium")
        conditions = {
            "all": [
                {"field": "status", "operator": "equals", "value": "open"},
                {"field": "priority", "operator": "equals", "value": "medium"},
            ]
        }
        assert self.engine.evaluate_conditions(conditions, ticket) is True

    def test_evaluate_or_conditions(self):
        ticket = self._create_ticket(status="open")
        conditions = {
            "any": [
                {"field": "status", "operator": "equals", "value": "closed"},
                {"field": "status", "operator": "equals", "value": "open"},
            ]
        }
        assert self.engine.evaluate_conditions(conditions, ticket) is True

    def test_evaluate_not_equals(self):
        ticket = self._create_ticket(status="open")
        conditions = {"all": [{"field": "status", "operator": "not_equals", "value": "closed"}]}
        assert self.engine.evaluate_conditions(conditions, ticket) is True

    def test_evaluate_contains(self):
        ticket = self._create_ticket(subject="Important billing issue")
        conditions = {"all": [{"field": "subject", "operator": "contains", "value": "billing"}]}
        assert self.engine.evaluate_conditions(conditions, ticket) is True

    def test_evaluate_is_empty(self):
        ticket = self._create_ticket(ticket_type="")
        conditions = {"all": [{"field": "ticket_type", "operator": "is_empty", "value": ""}]}
        assert self.engine.evaluate_conditions(conditions, ticket) is True

    def test_process_event_executes_actions(self):
        from escalated.workflow_models import WorkflowLog

        ticket = self._create_ticket(status="open")
        self._create_workflow()
        self.engine.process_event("ticket.created", ticket)
        ticket.refresh_from_db()
        assert ticket.priority == "high"
        assert WorkflowLog.objects.count() == 1

    def test_process_event_skips_non_matching(self):
        from escalated.workflow_models import WorkflowLog

        ticket = self._create_ticket(status="closed")
        self._create_workflow()
        self.engine.process_event("ticket.created", ticket)
        ticket.refresh_from_db()
        assert ticket.priority == "medium"
        log = WorkflowLog.objects.first()
        assert log.status == "skipped"

    def test_dry_run(self):
        ticket = self._create_ticket(status="open")
        workflow = self._create_workflow(actions=[{"type": "add_note", "value": "Note for {{reference}}"}])
        result = self.engine.dry_run(workflow, ticket)
        assert result["matched"] is True
        assert result["actions"][0]["would_execute"] is True
        assert ticket.reference in result["actions"][0]["value"]

    def test_process_delayed_actions(self):
        from escalated.workflow_models import DelayedAction

        ticket = self._create_ticket(status="open")
        workflow = self._create_workflow()
        DelayedAction.objects.create(
            workflow=workflow,
            ticket=ticket,
            action_data={"type": "change_priority", "value": "urgent"},
            execute_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        self.engine.process_delayed_actions()
        ticket.refresh_from_db()
        assert ticket.priority == "urgent"

    def test_send_webhook_blocks_private_target(self):
        ticket = self._create_ticket(status="open")

        with pytest.raises(UnsafeOutboundUrl):
            self.engine._send_webhook(
                {"type": "send_webhook", "url": "http://169.254.169.254/latest/meta-data/"},
                ticket,
            )

    def test_send_webhook_does_not_follow_redirects_after_validation(self):
        ticket = self._create_ticket(status="open")

        with (
            patch("escalated.outbound_security.socket.getaddrinfo", return_value=PUBLIC_ADDRINFO),
            patch("escalated.services.workflow_engine.requests.post") as mock_post,
        ):
            mock_post.return_value = MagicMock(status_code=302, text="redirect")
            self.engine._send_webhook({"type": "send_webhook", "url": "https://example.com/hook"}, ticket)

        assert mock_post.call_args.kwargs["allow_redirects"] is False

    # --- workflow-admin-contract: conditions ---------------------------------

    @pytest.mark.parametrize("conditions", [{"all": []}, {"any": []}, [], {}, None])
    def test_empty_or_omitted_conditions_match_every_ticket(self, conditions):
        ticket = self._create_ticket(status="closed")
        assert self.engine.evaluate_conditions(conditions, ticket) is True

    # --- workflow-admin-contract: core action catalog ------------------------

    def test_insert_canned_reply_adds_a_public_reply(self):
        from escalated.models import Reply

        ticket = self._create_ticket(status="open")
        workflow = self._create_workflow(
            conditions={"all": []},
            actions=[{"type": "insert_canned_reply", "value": "Thanks, we are looking at {{reference}}."}],
        )

        self.engine.process_event("ticket.created", ticket)

        reply = Reply.objects.get(ticket=ticket)
        assert reply.is_internal_note is False
        assert reply.body == f"Thanks, we are looking at {ticket.reference}."
        assert workflow.logs.get().actions_executed == [{"type": "insert_canned_reply", "result": "executed"}]

    def test_add_tag_creates_distinct_new_tags(self):
        ticket = self._create_ticket(status="open")
        self._create_workflow(
            conditions={"all": []},
            actions=[{"type": "add_tag", "value": "billing"}, {"type": "add_tag", "value": "refund"}],
        )

        self.engine.process_event("ticket.created", ticket)

        assert sorted(ticket.tags.values_list("name", flat=True)) == ["billing", "refund"]

    def test_remove_tag_detaches_the_named_tag(self):
        from tests.factories import TagFactory

        ticket = self._create_ticket(status="open")
        ticket.tags.add(TagFactory(name="billing", slug="billing"))
        self._create_workflow(conditions={"all": []}, actions=[{"type": "remove_tag", "value": "billing"}])

        self.engine.process_event("ticket.created", ticket)

        assert not ticket.tags.exists()

    def test_core_actions_are_offered(self):
        from escalated.services.workflow_engine import ACTION_TYPES

        offered = {a["value"] if isinstance(a, dict) else a for a in ACTION_TYPES}
        assert {
            "change_status",
            "change_priority",
            "add_tag",
            "remove_tag",
            "set_department",
            "assign_agent",
            "add_note",
            "insert_canned_reply",
        } <= offered

    # --- shapes the engine must keep reading ---------------------------------

    def test_stored_ticket_replied_workflow_still_runs_on_reply_created(self):
        ticket = self._create_ticket(status="open")
        self._create_workflow(trigger_event="ticket.replied", conditions={"all": []})

        self.engine.process_event("reply.created", ticket)

        ticket.refresh_from_db()
        assert ticket.priority == "high"
