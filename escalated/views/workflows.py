import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from escalated.permissions import is_admin
from escalated.rendering import render_page
from escalated.services.workflow_engine import ACTION_TYPES, OPERATORS, WorkflowEngine
from escalated.workflow_models import Workflow, WorkflowLog


def _require_admin(request):
    if not is_admin(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    return None


def _workflow_json(w):
    return {
        "id": w.id,
        "name": w.name,
        "trigger_event": w.trigger_event,
        "trigger": w.trigger,
        "conditions": w.conditions,
        "actions": w.actions,
        "is_active": w.is_active,
        "position": w.position,
        "created_at": w.created_at.isoformat(),
        "updated_at": w.updated_at.isoformat(),
    }


def _log_json(log):
    return {
        "id": log.id,
        "workflow_id": log.workflow_id,
        "ticket_id": log.ticket_id,
        "trigger_event": log.trigger_event,
        "event": log.event,
        "workflow_name": log.workflow_name,
        "ticket_reference": log.ticket_reference,
        "matched": log.matched,
        "actions_executed": log.actions_executed_count,
        "action_details": log.action_details,
        "duration_ms": log.duration_ms,
        "status": log.computed_status,
        "error_message": log.error_message,
        "created_at": log.created_at.isoformat(),
    }


@login_required
def workflow_list(request):
    if err := _require_admin(request):
        return err
    workflows = Workflow.objects.all().order_by("position", "name")
    return render_page(
        request,
        "Escalated/Admin/Workflows/Index",
        {"workflows": [_workflow_json(w) for w in workflows]},
    )


@login_required
def workflow_create(request):
    if err := _require_admin(request):
        return err
    if request.method == "POST":
        data = json.loads(request.body) if request.content_type == "application/json" else request.POST
        w = Workflow.objects.create(
            name=data.get("name", ""),
            trigger_event=data.get("trigger_event", ""),
            conditions=data.get("conditions", {}),
            actions=data.get("actions", []),
            is_active=data.get("is_active", True),
            position=data.get("position", 0),
        )
        return JsonResponse(_workflow_json(w), status=201)
    return render_page(
        request,
        "Escalated/Admin/Workflows/New",
        {
            "trigger_events": [e[0] for e in Workflow.TRIGGER_EVENTS],
            "operators": OPERATORS,
            "action_types": ACTION_TYPES,
        },
    )


@login_required
def workflow_update(request, workflow_id):
    if err := _require_admin(request):
        return err
    w = Workflow.objects.get(pk=workflow_id)
    if request.method == "POST":
        data = json.loads(request.body) if request.content_type == "application/json" else request.POST
        for field in ["name", "trigger_event", "conditions", "actions", "is_active", "position"]:
            if field in data:
                setattr(w, field, data[field])
        w.save()
        return JsonResponse(_workflow_json(w))
    return render_page(
        request,
        "Escalated/Admin/Workflows/Edit",
        {
            "workflow": _workflow_json(w),
            "trigger_events": [e[0] for e in Workflow.TRIGGER_EVENTS],
            "operators": OPERATORS,
            "action_types": ACTION_TYPES,
        },
    )


@login_required
@require_POST
def workflow_delete(request, workflow_id):
    if err := _require_admin(request):
        return err
    Workflow.objects.filter(pk=workflow_id).delete()
    return JsonResponse({"deleted": True})


@login_required
@require_POST
def workflow_toggle(request, workflow_id):
    if err := _require_admin(request):
        return err
    w = Workflow.objects.get(pk=workflow_id)
    w.is_active = not w.is_active
    w.save()
    return JsonResponse(_workflow_json(w))


@login_required
@require_POST
def workflow_reorder(request):
    if err := _require_admin(request):
        return err
    data = json.loads(request.body)
    for idx, wid in enumerate(data.get("workflow_ids", [])):
        Workflow.objects.filter(pk=wid).update(position=idx)
    return JsonResponse({"reordered": True})


@login_required
def workflow_logs(request, workflow_id):
    if err := _require_admin(request):
        return err
    w = Workflow.objects.get(pk=workflow_id)
    logs = (
        WorkflowLog.objects.filter(workflow=w)
        .select_related("workflow", "ticket")
        .order_by("-created_at")[:100]
    )
    return render_page(
        request,
        "Escalated/Admin/Workflows/Logs",
        {
            "workflow": _workflow_json(w),
            "logs": [_log_json(log) for log in logs],
        },
    )


@login_required
@require_POST
def workflow_dry_run(request, workflow_id):
    if err := _require_admin(request):
        return err
    from escalated.models import Ticket

    data = json.loads(request.body)
    w = Workflow.objects.get(pk=workflow_id)
    ticket = Ticket.objects.get(pk=data.get("ticket_id"))
    engine = WorkflowEngine()
    result = engine.dry_run(w, ticket)
    return JsonResponse(result)
