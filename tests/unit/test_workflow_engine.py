import pytest
from django.utils import timezone

from escalated.services.workflow_engine import WorkflowEngine


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
        ticket = self._create_ticket(ticket_type=None)
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
