"""Workflow automation models - imported into models.py namespace."""

from django.db import models
from django.utils import timezone

from escalated.conf import get_table_name


class Workflow(models.Model):
    # Exactly the events escalated/workflow_handlers.py passes to the engine.
    # The admin form offers this list, so a trigger listed here but never fired
    # would save a workflow that can never run.
    TRIGGER_EVENTS = [
        ("ticket.created", "Ticket Created"),
        ("ticket.updated", "Ticket Updated"),
        ("ticket.status_changed", "Status Changed"),
        ("ticket.assigned", "Ticket Assigned"),
        ("ticket.priority_changed", "Priority Changed"),
        ("ticket.escalated", "Ticket Escalated"),
        ("reply.created", "Reply Created"),
        ("sla.warning", "SLA Warning"),
        ("sla.breached", "SLA Breached"),
    ]

    # Trigger names earlier releases fired, mapped to the event that fires in
    # their place. Workflows already stored under them keep running.
    LEGACY_TRIGGER_EVENTS = {"ticket.replied": "reply.created"}

    name = models.CharField(max_length=255)
    trigger_event = models.CharField(max_length=100, choices=TRIGGER_EVENTS)
    conditions = models.JSONField(default=dict)
    actions = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("workflows")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name

    @property
    def trigger(self):
        """Alias for frontend compatibility: the frontend uses `trigger` instead of `trigger_event`."""
        return self.trigger_event


class WorkflowLog(models.Model):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="logs")
    ticket = models.ForeignKey("escalated.Ticket", on_delete=models.CASCADE, related_name="workflow_logs")
    trigger_event = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="success")
    actions_executed = models.JSONField(default=list)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    conditions_matched = models.BooleanField(default=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = get_table_name("workflow_logs")
        ordering = ["-created_at"]

    def __str__(self):
        return f"WorkflowLog {self.id}: {self.status}"

    # --- Computed fields expected by the frontend ---

    @property
    def event(self):
        """Alias: frontend reads `event` instead of `trigger_event`."""
        return self.trigger_event

    @property
    def matched(self):
        """Boolean alias for conditions_matched."""
        return self.conditions_matched

    @property
    def action_details(self):
        """Raw actions array for the expanded detail view."""
        return self.actions_executed or []

    @property
    def actions_executed_count(self):
        """Integer count of executed actions."""
        return len(self.actions_executed) if self.actions_executed else 0

    @property
    def duration_ms(self):
        """Milliseconds between started_at and completed_at."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None

    @property
    def computed_status(self):
        """Computed status: 'failed' when an error is present, otherwise 'success'."""
        return "failed" if self.error_message else "success"

    @property
    def workflow_name(self):
        """Eager-loaded workflow name."""
        return self.workflow.name if self.workflow_id else None

    @property
    def ticket_reference(self):
        """Eager-loaded ticket reference."""
        return self.ticket.reference if self.ticket_id else None


class DelayedAction(models.Model):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="delayed_actions")
    ticket = models.ForeignKey("escalated.Ticket", on_delete=models.CASCADE, related_name="delayed_actions")
    action_data = models.JSONField()
    execute_at = models.DateTimeField()
    executed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = get_table_name("delayed_actions")

    def __str__(self):
        return f"DelayedAction {self.id}: execute_at={self.execute_at}"

    @classmethod
    def pending(cls):
        return cls.objects.filter(executed=False, execute_at__lte=timezone.now())
