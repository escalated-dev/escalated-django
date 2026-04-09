import json
import logging
import re
import urllib.request

from django.utils import timezone

logger = logging.getLogger("escalated")

OPERATORS = [
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "greater_than",
    "less_than",
    "greater_or_equal",
    "less_or_equal",
    "is_empty",
    "is_not_empty",
]

ACTION_TYPES = [
    "change_status",
    "assign_agent",
    "change_priority",
    "add_tag",
    "remove_tag",
    "set_department",
    "add_note",
    "send_webhook",
    "set_type",
    "delay",
    "add_follower",
    "send_notification",
]


class WorkflowEngine:
    def process_event(self, event_name, ticket, context=None):
        from escalated.workflow_models import Workflow

        workflows = Workflow.objects.filter(trigger_event=event_name, is_active=True).order_by("position")
        for workflow in workflows:
            self._process_workflow(workflow, ticket, event_name, context or {})

    def dry_run(self, workflow, ticket):
        matched = self.evaluate_conditions(workflow.conditions, ticket)
        actions_preview = [
            {
                "type": a.get("type"),
                "value": self._interpolate(str(a.get("value", "")), ticket),
                "would_execute": matched,
            }
            for a in (workflow.actions or [])
        ]
        return {"matched": matched, "actions": actions_preview}

    def process_delayed_actions(self):
        from escalated.workflow_models import DelayedAction

        for delayed in DelayedAction.pending():
            try:
                self._execute_single_action(delayed.action_data, delayed.ticket, delayed.workflow)
                delayed.executed = True
                delayed.save()
            except Exception as e:
                logger.error(f"Escalated delayed action failed: {e}")

    def evaluate_conditions(self, conditions, ticket):
        if isinstance(conditions, dict):
            if "all" in conditions:
                return all(self._eval_single(c, ticket) for c in conditions["all"])
            if "any" in conditions:
                return any(self._eval_single(c, ticket) for c in conditions["any"])
            return self._eval_single(conditions, ticket)
        if isinstance(conditions, list):
            return all(self._eval_single(c, ticket) for c in conditions)
        return False

    def _process_workflow(self, workflow, ticket, event_name, context):
        matched = self.evaluate_conditions(workflow.conditions, ticket)
        if not matched:
            self._log(workflow, ticket, event_name, "skipped", [])
            return
        try:
            executed = self._execute_actions(workflow, ticket, context)
            self._log(workflow, ticket, event_name, "success", executed)
        except Exception as e:
            self._log(workflow, ticket, event_name, "failure", [], str(e))
            logger.error(f"Escalated workflow {workflow.id} failed: {e}")

    def _eval_single(self, condition, ticket):
        field = condition.get("field", "")
        operator = condition.get("operator", "equals")
        expected = condition.get("value")
        actual = self._resolve_field(field, ticket)
        return self._apply_operator(operator, actual, expected)

    def _resolve_field(self, field, ticket):
        mapping = {
            "status": ticket.status,
            "priority": ticket.priority,
            "assigned_to": getattr(ticket, "assigned_to_id", None),
            "department_id": getattr(ticket, "department_id", None),
            "channel": getattr(ticket, "channel", None),
            "ticket_type": getattr(ticket, "ticket_type", None),
            "subject": ticket.subject,
            "description": ticket.description,
            "sla_breached": getattr(ticket, "sla_first_response_breached", False)
            or getattr(ticket, "sla_resolution_breached", False),
        }
        if field == "tags":
            return ",".join(ticket.tags.values_list("name", flat=True))
        if field == "hours_since_created":
            return round((timezone.now() - ticket.created_at).total_seconds() / 3600, 1)
        if field == "hours_since_updated":
            return round((timezone.now() - ticket.updated_at).total_seconds() / 3600, 1)
        return mapping.get(field)

    def _apply_operator(self, operator, actual, expected):
        actual_s = str(actual) if actual is not None else ""
        expected_s = str(expected) if expected is not None else ""

        ops = {
            "equals": actual_s == expected_s,
            "not_equals": actual_s != expected_s,
            "contains": expected_s in actual_s,
            "not_contains": expected_s not in actual_s,
            "starts_with": actual_s.startswith(expected_s),
            "ends_with": actual_s.endswith(expected_s),
            "greater_than": self._to_float(actual) > self._to_float(expected),
            "less_than": self._to_float(actual) < self._to_float(expected),
            "greater_or_equal": self._to_float(actual) >= self._to_float(expected),
            "less_or_equal": self._to_float(actual) <= self._to_float(expected),
            "is_empty": not actual_s.strip(),
            "is_not_empty": bool(actual_s.strip()),
        }
        return ops.get(operator, False)

    def _to_float(self, val):
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    def _execute_actions(self, workflow, ticket, context):
        executed = []
        for action in workflow.actions or []:
            result = self._execute_single_action(action, ticket, workflow)
            executed.append({"type": action.get("type"), "result": result})
        return executed

    def _execute_single_action(self, action, ticket, workflow):
        from escalated.models import Reply, Tag

        action_type = action.get("type", "")
        value = action.get("value")

        try:
            if action_type == "change_status":
                ticket.status = value
                ticket.save()
            elif action_type == "assign_agent":
                ticket.assigned_to_id = int(value)
                ticket.save()
            elif action_type == "change_priority":
                ticket.priority = value
                ticket.save()
            elif action_type == "add_tag":
                tag, _ = Tag.objects.get_or_create(name=value)
                ticket.tags.add(tag)
            elif action_type == "remove_tag":
                tag = Tag.objects.filter(name=value).first()
                if tag:
                    ticket.tags.remove(tag)
            elif action_type == "set_department":
                ticket.department_id = int(value)
                ticket.save()
            elif action_type == "add_note":
                Reply.objects.create(
                    ticket=ticket,
                    body=self._interpolate(str(value), ticket),
                    is_internal_note=True,
                )
            elif action_type == "send_webhook":
                self._send_webhook(action, ticket)
            elif action_type == "set_type":
                ticket.ticket_type = value
                ticket.save()
            elif action_type == "delay":
                self._handle_delay(action, ticket, workflow)
                return "delayed"
            elif action_type == "add_follower":
                ticket.followers.add(int(value))
            elif action_type == "send_notification":
                logger.info(f"Workflow notification: {self._interpolate(str(value), ticket)}")
            return "executed"
        except Exception as e:
            logger.warning(f"Workflow action {action_type} failed: {e}")
            return "failed"

    def _handle_delay(self, action, ticket, workflow):
        from escalated.workflow_models import DelayedAction

        delay_minutes = int(action.get("value", 0))
        for remaining in action.get("remaining_actions", []):
            DelayedAction.objects.create(
                workflow=workflow,
                ticket=ticket,
                action_data=remaining,
                execute_at=timezone.now() + timezone.timedelta(minutes=delay_minutes),
            )

    def _send_webhook(self, action, ticket):
        url = action.get("url") or action.get("value")
        body = json.dumps(
            {
                "event": "workflow_action",
                "ticket": {
                    "id": ticket.id,
                    "reference": ticket.reference,
                    "subject": ticket.subject,
                    "status": ticket.status,
                },
                "payload": self._interpolate(str(action.get("payload", "")), ticket),
            }
        ).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        req.method = "POST"
        urllib.request.urlopen(req, timeout=10)

    def _interpolate(self, text, ticket):
        def replacer(match):
            var = match.group(1)
            mapping = {
                "ticket_id": str(ticket.id),
                "ticket_ref": ticket.reference,
                "reference": ticket.reference,
                "subject": ticket.subject,
                "status": ticket.status,
                "priority": ticket.priority,
                "requester": getattr(ticket, "requester_name", "Unknown"),
            }
            return mapping.get(var, match.group(0))

        return re.sub(r"\{\{(\w+)\}\}", replacer, text)

    def _log(self, workflow, ticket, event_name, status, actions, error=None):
        from escalated.workflow_models import WorkflowLog

        WorkflowLog.objects.create(
            workflow=workflow,
            ticket=ticket,
            trigger_event=event_name,
            status=status,
            actions_executed=actions,
            error_message=error,
        )
