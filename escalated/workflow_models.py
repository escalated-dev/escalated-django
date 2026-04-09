"""Workflow automation models - imported into models.py namespace."""

from django.db import models
from django.utils import timezone

from escalated.conf import get_table_name


class Workflow(models.Model):
    TRIGGER_EVENTS = [
        ("ticket.created", "Ticket Created"),
        ("ticket.updated", "Ticket Updated"),
        ("ticket.status_changed", "Status Changed"),
        ("ticket.assigned", "Ticket Assigned"),
        ("ticket.priority_changed", "Priority Changed"),
        ("ticket.tagged", "Ticket Tagged"),
        ("ticket.department_changed", "Department Changed"),
        ("reply.created", "Reply Created"),
        ("reply.agent_reply", "Agent Reply"),
        ("sla.warning", "SLA Warning"),
        ("sla.breached", "SLA Breached"),
        ("ticket.reopened", "Ticket Reopened"),
    ]

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


class WorkflowLog(models.Model):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="logs")
    ticket = models.ForeignKey("escalated.Ticket", on_delete=models.CASCADE, related_name="workflow_logs")
    trigger_event = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="success")
    actions_executed = models.JSONField(default=list)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = get_table_name("workflow_logs")
        ordering = ["-created_at"]

    def __str__(self):
        return f"WorkflowLog {self.id}: {self.status}"


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
