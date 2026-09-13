import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from escalated.permissions import is_admin
from escalated.rendering import render_page
from escalated.services.workflow_engine import ACTION_TYPES, OPERATORS, WorkflowEngine
from escalated.workflow_models import Workflow, WorkflowLog

# The admin screen is driven by Inertia form visits, which follow a redirect
# and cannot consume a JSON 201. What a save has to say survives that redirect
# in the session: the success message for the index, validation errors for the
# form that was submitted. Each is shown once.
FLASH_SESSION_KEY = "escalated_workflows_flash"
ERRORS_SESSION_KEY = "escalated_workflows_errors"


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


def _redirect(request, url):
    # Inertia needs a 303 after PUT/PATCH/DELETE, or the browser repeats the
    # original method against the redirect target.
    response = HttpResponseRedirect(url)
    if request.method in ("PUT", "PATCH", "DELETE"):
        response.status_code = 303
    return response


def _redirect_to_index(request, message):
    request.session[FLASH_SESSION_KEY] = {"success": message}
    return _redirect(request, reverse("escalated:admin_workflows"))


def _redirect_back(request, errors, fallback):
    request.session[ERRORS_SESSION_KEY] = errors
    referer = request.META.get("HTTP_REFERER")
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return _redirect(request, referer)
    return _redirect(request, fallback)


def _request_data(request):
    """The submitted fields: a JSON object from the builder, or a form POST."""
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
    return request.POST


def _as_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes")
    return bool(value)


def _clean(data):
    """Validate the contract's create/update body.

    Returns ``(fields, errors)``. Keys are top-level: name, trigger_event,
    conditions, actions and is_active. There is no description column, so a
    description in the body is ignored.
    """
    errors = {}

    name = data.get("name")
    name = name.strip() if isinstance(name, str) else ""
    if not name:
        errors["name"] = _("The name field is required.")

    trigger_event = data.get("trigger_event")
    trigger_event = trigger_event.strip() if isinstance(trigger_event, str) else ""
    known_triggers = {value for value, _label in Workflow.TRIGGER_EVENTS} | set(Workflow.LEGACY_TRIGGER_EVENTS)
    if not trigger_event:
        errors["trigger_event"] = _("The trigger event field is required.")
    elif trigger_event not in known_triggers:
        errors["trigger_event"] = _("The selected trigger event is invalid.")

    actions = data.get("actions")
    if not isinstance(actions, list) or not actions:
        errors["actions"] = _("Add at least one action.")

    conditions = data.get("conditions")
    if not conditions:
        conditions = {"all": []}
    elif not isinstance(conditions, (dict, list)):
        errors["conditions"] = _("The conditions field is invalid.")

    fields = {
        "name": name,
        "trigger_event": trigger_event,
        "conditions": conditions,
        "actions": actions,
    }
    if "is_active" in data:
        fields["is_active"] = _as_bool(data.get("is_active"))
    return fields, errors


def _form_page(request, workflow=None):
    return render_page(
        request,
        "Escalated/Admin/Workflows/Form",
        {
            "workflow": _workflow_json(workflow) if workflow else None,
            "trigger_events": [{"value": value, "label": label} for value, label in Workflow.TRIGGER_EVENTS],
            "operators": OPERATORS,
            "action_types": ACTION_TYPES,
            "errors": request.session.pop(ERRORS_SESSION_KEY, {}),
        },
    )


def _store(request):
    fields, errors = _clean(_request_data(request))
    if errors:
        return _redirect_back(request, errors, reverse("escalated:admin_workflow_create"))
    Workflow.objects.create(**fields)
    return _redirect_to_index(request, _("Workflow created."))


@login_required
def workflow_list(request):
    if err := _require_admin(request):
        return err
    if request.method == "POST":
        return _store(request)
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])
    workflows = Workflow.objects.all().order_by("position", "name")
    return render_page(
        request,
        "Escalated/Admin/Workflows/Index",
        {
            "workflows": [_workflow_json(w) for w in workflows],
            "flash": request.session.pop(FLASH_SESSION_KEY, {}),
        },
    )


@login_required
def workflow_create(request):
    if err := _require_admin(request):
        return err
    if request.method == "POST":
        return _store(request)
    return _form_page(request)


@login_required
def workflow_update(request, workflow_id):
    """The edit form (GET), update (PUT, or POST from older clients) and delete (DELETE)."""
    if err := _require_admin(request):
        return err
    w = get_object_or_404(Workflow, pk=workflow_id)
    if request.method == "DELETE":
        w.delete()
        return _redirect_to_index(request, _("Workflow deleted."))
    if request.method in ("PUT", "PATCH", "POST"):
        fields, errors = _clean(_request_data(request))
        if errors:
            return _redirect_back(request, errors, reverse("escalated:admin_workflow_update", args=[w.pk]))
        for field, value in fields.items():
            setattr(w, field, value)
        w.save()
        return _redirect_to_index(request, _("Workflow updated."))
    return _form_page(request, w)


@login_required
@require_POST
def workflow_delete(request, workflow_id):
    if err := _require_admin(request):
        return err
    Workflow.objects.filter(pk=workflow_id).delete()
    return _redirect_to_index(request, _("Workflow deleted."))


@login_required
@require_POST
def workflow_toggle(request, workflow_id):
    if err := _require_admin(request):
        return err
    w = get_object_or_404(Workflow, pk=workflow_id)
    w.is_active = not w.is_active
    w.save()
    return _redirect_to_index(request, _("Workflow enabled.") if w.is_active else _("Workflow disabled."))


@login_required
@require_POST
def workflow_reorder(request):
    if err := _require_admin(request):
        return err
    workflow_ids = _request_data(request).get("workflow_ids")
    for idx, wid in enumerate(workflow_ids if isinstance(workflow_ids, list) else []):
        Workflow.objects.filter(pk=wid).update(position=idx)
    return _redirect_to_index(request, _("Workflows reordered."))


@login_required
def workflow_logs(request, workflow_id):
    if err := _require_admin(request):
        return err
    w = Workflow.objects.get(pk=workflow_id)
    logs = WorkflowLog.objects.filter(workflow=w).select_related("workflow", "ticket").order_by("-created_at")[:100]
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
