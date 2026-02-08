from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Avg, F
from django.http import HttpResponseForbidden, HttpResponseNotFound
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.text import slugify
from inertia import render

from escalated.models import (
    Ticket,
    Tag,
    Department,
    SlaPolicy,
    EscalationRule,
    CannedResponse,
    EscalatedSetting,
)
from escalated.permissions import is_admin
from escalated.serializers import (
    TicketSerializer,
    TagSerializer,
    DepartmentSerializer,
    SlaPolicySerializer,
    EscalationRuleSerializer,
    CannedResponseSerializer,
    EscalatedSettingSerializer,
)


def _require_admin(request):
    """Return an error response if user is not admin, else None."""
    if not request.user.is_authenticated:
        return redirect("login")
    if not is_admin(request.user):
        return HttpResponseForbidden("Admin access required.")
    return None


# ---------------------------------------------------------------------------
# Reports / Analytics
# ---------------------------------------------------------------------------


@login_required
def reports(request):
    """Admin reports and analytics dashboard."""
    check = _require_admin(request)
    if check:
        return check

    now = timezone.now()
    thirty_days_ago = now - timezone.timedelta(days=30)

    total_tickets = Ticket.objects.count()
    open_tickets = Ticket.objects.open().count()
    resolved_last_30 = Ticket.objects.filter(
        resolved_at__gte=thirty_days_ago
    ).count()
    created_last_30 = Ticket.objects.filter(
        created_at__gte=thirty_days_ago
    ).count()
    sla_breaches = Ticket.objects.breached_sla().count()

    by_department = list(
        Department.objects.filter(is_active=True)
        .annotate(ticket_count=Count("tickets"))
        .values("name", "ticket_count")
    )

    by_priority = {
        p.value: Ticket.objects.filter(priority=p.value).count()
        for p in Ticket.Priority
    }

    by_status = {
        s.value: Ticket.objects.filter(status=s.value).count()
        for s in Ticket.Status
    }

    return render(request, "Escalated/Admin/Reports", props={
        "stats": {
            "total_tickets": total_tickets,
            "open_tickets": open_tickets,
            "resolved_last_30": resolved_last_30,
            "created_last_30": created_last_30,
            "sla_breaches": sla_breaches,
        },
        "by_department": by_department,
        "by_priority": by_priority,
        "by_status": by_status,
    })


# ---------------------------------------------------------------------------
# Departments CRUD
# ---------------------------------------------------------------------------


@login_required
def departments_index(request):
    check = _require_admin(request)
    if check:
        return check

    departments = Department.objects.annotate(
        agent_count=Count("agents"),
        ticket_count=Count("tickets"),
    )

    return render(request, "Escalated/Admin/Departments/Index", props={
        "departments": DepartmentSerializer.serialize_list(departments),
    })


@login_required
def departments_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        slug = slugify(request.POST.get("slug", "") or name)
        description = request.POST.get("description", "")
        is_active = request.POST.get("is_active", "true") == "true"

        if not name:
            return render(request, "Escalated/Admin/Departments/Create", props={
                "errors": {"name": "Name is required."},
            })

        Department.objects.create(
            name=name, slug=slug, description=description, is_active=is_active
        )
        return redirect("escalated:admin_departments_index")

    return render(request, "Escalated/Admin/Departments/Create", props={})


@login_required
def departments_edit(request, department_id):
    check = _require_admin(request)
    if check:
        return check

    try:
        department = Department.objects.get(pk=department_id)
    except Department.DoesNotExist:
        return HttpResponseNotFound("Department not found")

    if request.method == "POST":
        department.name = request.POST.get("name", department.name)
        department.slug = slugify(
            request.POST.get("slug", "") or department.name
        )
        department.description = request.POST.get(
            "description", department.description
        )
        department.is_active = request.POST.get("is_active", "true") == "true"
        department.save()

        # Update agents
        agent_ids = request.POST.getlist("agent_ids")
        if agent_ids is not None:
            department.agents.set(agent_ids)

        return redirect("escalated:admin_departments_index")

    from django.contrib.auth import get_user_model
    User = get_user_model()

    return render(request, "Escalated/Admin/Departments/Edit", props={
        "department": DepartmentSerializer.serialize(department),
        "all_agents": [
            {"id": u.pk, "name": u.get_full_name() or u.username, "email": u.email}
            for u in User.objects.filter(is_active=True)
        ],
        "current_agent_ids": list(department.agents.values_list("pk", flat=True)),
    })


@login_required
def departments_delete(request, department_id):
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        department = Department.objects.get(pk=department_id)
        department.delete()
    except Department.DoesNotExist:
        pass

    return redirect("escalated:admin_departments_index")


# ---------------------------------------------------------------------------
# SLA Policies CRUD
# ---------------------------------------------------------------------------


@login_required
def sla_policies_index(request):
    check = _require_admin(request)
    if check:
        return check

    policies = SlaPolicy.objects.all()
    return render(request, "Escalated/Admin/SlaPolicies/Index", props={
        "policies": SlaPolicySerializer.serialize_list(policies),
    })


@login_required
def sla_policies_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        import json

        name = request.POST.get("name", "").strip()
        if not name:
            return render(request, "Escalated/Admin/SlaPolicies/Create", props={
                "errors": {"name": "Name is required."},
            })

        try:
            first_response_hours = json.loads(
                request.POST.get("first_response_hours", "{}")
            )
        except (json.JSONDecodeError, TypeError):
            first_response_hours = {}

        try:
            resolution_hours = json.loads(
                request.POST.get("resolution_hours", "{}")
            )
        except (json.JSONDecodeError, TypeError):
            resolution_hours = {}

        is_default = request.POST.get("is_default", "false") == "true"

        # If setting as default, unset other defaults
        if is_default:
            SlaPolicy.objects.filter(is_default=True).update(is_default=False)

        SlaPolicy.objects.create(
            name=name,
            description=request.POST.get("description", ""),
            is_default=is_default,
            first_response_hours=first_response_hours,
            resolution_hours=resolution_hours,
            business_hours_only=request.POST.get("business_hours_only", "false") == "true",
            is_active=request.POST.get("is_active", "true") == "true",
        )
        return redirect("escalated:admin_sla_policies_index")

    return render(request, "Escalated/Admin/SlaPolicies/Create", props={
        "priorities": [{"value": p.value, "label": p.label} for p in Ticket.Priority],
    })


@login_required
def sla_policies_edit(request, policy_id):
    check = _require_admin(request)
    if check:
        return check

    try:
        policy = SlaPolicy.objects.get(pk=policy_id)
    except SlaPolicy.DoesNotExist:
        return HttpResponseNotFound("SLA Policy not found")

    if request.method == "POST":
        import json

        policy.name = request.POST.get("name", policy.name)
        policy.description = request.POST.get("description", policy.description)
        policy.business_hours_only = (
            request.POST.get("business_hours_only", "false") == "true"
        )
        policy.is_active = request.POST.get("is_active", "true") == "true"

        is_default = request.POST.get("is_default", "false") == "true"
        if is_default and not policy.is_default:
            SlaPolicy.objects.filter(is_default=True).update(is_default=False)
        policy.is_default = is_default

        try:
            policy.first_response_hours = json.loads(
                request.POST.get("first_response_hours", "{}")
            )
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            policy.resolution_hours = json.loads(
                request.POST.get("resolution_hours", "{}")
            )
        except (json.JSONDecodeError, TypeError):
            pass

        policy.save()
        return redirect("escalated:admin_sla_policies_index")

    return render(request, "Escalated/Admin/SlaPolicies/Edit", props={
        "policy": SlaPolicySerializer.serialize(policy),
        "priorities": [{"value": p.value, "label": p.label} for p in Ticket.Priority],
    })


@login_required
def sla_policies_delete(request, policy_id):
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        policy = SlaPolicy.objects.get(pk=policy_id)
        policy.delete()
    except SlaPolicy.DoesNotExist:
        pass

    return redirect("escalated:admin_sla_policies_index")


# ---------------------------------------------------------------------------
# Escalation Rules CRUD
# ---------------------------------------------------------------------------


@login_required
def escalation_rules_index(request):
    check = _require_admin(request)
    if check:
        return check

    rules = EscalationRule.objects.all()
    return render(request, "Escalated/Admin/EscalationRules/Index", props={
        "rules": EscalationRuleSerializer.serialize_list(rules),
    })


@login_required
def escalation_rules_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        import json

        name = request.POST.get("name", "").strip()
        if not name:
            return render(request, "Escalated/Admin/EscalationRules/Create", props={
                "errors": {"name": "Name is required."},
                "trigger_types": [
                    {"value": t.value, "label": t.label}
                    for t in EscalationRule.TriggerType
                ],
            })

        try:
            conditions = json.loads(request.POST.get("conditions", "{}"))
        except (json.JSONDecodeError, TypeError):
            conditions = {}

        try:
            actions = json.loads(request.POST.get("actions", "{}"))
        except (json.JSONDecodeError, TypeError):
            actions = {}

        EscalationRule.objects.create(
            name=name,
            description=request.POST.get("description", ""),
            trigger_type=request.POST.get("trigger_type", EscalationRule.TriggerType.SLA_BREACH),
            conditions=conditions,
            actions=actions,
            order=int(request.POST.get("order", 0)),
            is_active=request.POST.get("is_active", "true") == "true",
        )
        return redirect("escalated:admin_escalation_rules_index")

    return render(request, "Escalated/Admin/EscalationRules/Create", props={
        "trigger_types": [
            {"value": t.value, "label": t.label}
            for t in EscalationRule.TriggerType
        ],
    })


@login_required
def escalation_rules_edit(request, rule_id):
    check = _require_admin(request)
    if check:
        return check

    try:
        rule = EscalationRule.objects.get(pk=rule_id)
    except EscalationRule.DoesNotExist:
        return HttpResponseNotFound("Escalation rule not found")

    if request.method == "POST":
        import json

        rule.name = request.POST.get("name", rule.name)
        rule.description = request.POST.get("description", rule.description)
        rule.trigger_type = request.POST.get("trigger_type", rule.trigger_type)
        rule.order = int(request.POST.get("order", rule.order))
        rule.is_active = request.POST.get("is_active", "true") == "true"

        try:
            rule.conditions = json.loads(request.POST.get("conditions", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            rule.actions = json.loads(request.POST.get("actions", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass

        rule.save()
        return redirect("escalated:admin_escalation_rules_index")

    return render(request, "Escalated/Admin/EscalationRules/Edit", props={
        "rule": EscalationRuleSerializer.serialize(rule),
        "trigger_types": [
            {"value": t.value, "label": t.label}
            for t in EscalationRule.TriggerType
        ],
    })


@login_required
def escalation_rules_delete(request, rule_id):
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        rule = EscalationRule.objects.get(pk=rule_id)
        rule.delete()
    except EscalationRule.DoesNotExist:
        pass

    return redirect("escalated:admin_escalation_rules_index")


# ---------------------------------------------------------------------------
# Tags CRUD
# ---------------------------------------------------------------------------


@login_required
def tags_index(request):
    check = _require_admin(request)
    if check:
        return check

    tags = Tag.objects.annotate(ticket_count=Count("tickets"))
    return render(request, "Escalated/Admin/Tags/Index", props={
        "tags": [
            {**TagSerializer.serialize(t), "ticket_count": t.ticket_count}
            for t in tags
        ],
    })


@login_required
def tags_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            return render(request, "Escalated/Admin/Tags/Create", props={
                "errors": {"name": "Name is required."},
            })

        Tag.objects.create(
            name=name,
            slug=slugify(request.POST.get("slug", "") or name),
            color=request.POST.get("color", "#6b7280"),
        )
        return redirect("escalated:admin_tags_index")

    return render(request, "Escalated/Admin/Tags/Create", props={})


@login_required
def tags_edit(request, tag_id):
    check = _require_admin(request)
    if check:
        return check

    try:
        tag = Tag.objects.get(pk=tag_id)
    except Tag.DoesNotExist:
        return HttpResponseNotFound("Tag not found")

    if request.method == "POST":
        tag.name = request.POST.get("name", tag.name)
        tag.slug = slugify(request.POST.get("slug", "") or tag.name)
        tag.color = request.POST.get("color", tag.color)
        tag.save()
        return redirect("escalated:admin_tags_index")

    return render(request, "Escalated/Admin/Tags/Edit", props={
        "tag": TagSerializer.serialize(tag),
    })


@login_required
def tags_delete(request, tag_id):
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        tag = Tag.objects.get(pk=tag_id)
        tag.delete()
    except Tag.DoesNotExist:
        pass

    return redirect("escalated:admin_tags_index")


# ---------------------------------------------------------------------------
# Canned Responses CRUD
# ---------------------------------------------------------------------------


@login_required
def canned_responses_index(request):
    check = _require_admin(request)
    if check:
        return check

    responses = CannedResponse.objects.select_related("created_by")
    return render(request, "Escalated/Admin/CannedResponses/Index", props={
        "canned_responses": CannedResponseSerializer.serialize_list(responses),
    })


@login_required
def canned_responses_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        if not title:
            return render(request, "Escalated/Admin/CannedResponses/Create", props={
                "errors": {"title": "Title is required."},
            })

        CannedResponse.objects.create(
            title=title,
            body=request.POST.get("body", ""),
            category=request.POST.get("category", ""),
            created_by=request.user,
            is_shared=request.POST.get("is_shared", "true") == "true",
        )
        return redirect("escalated:admin_canned_responses_index")

    return render(request, "Escalated/Admin/CannedResponses/Create", props={})


@login_required
def canned_responses_edit(request, response_id):
    check = _require_admin(request)
    if check:
        return check

    try:
        canned = CannedResponse.objects.get(pk=response_id)
    except CannedResponse.DoesNotExist:
        return HttpResponseNotFound("Canned response not found")

    if request.method == "POST":
        canned.title = request.POST.get("title", canned.title)
        canned.body = request.POST.get("body", canned.body)
        canned.category = request.POST.get("category", canned.category)
        canned.is_shared = request.POST.get("is_shared", "true") == "true"
        canned.save()
        return redirect("escalated:admin_canned_responses_index")

    return render(request, "Escalated/Admin/CannedResponses/Edit", props={
        "canned_response": CannedResponseSerializer.serialize(canned),
    })


@login_required
def canned_responses_delete(request, response_id):
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    try:
        canned = CannedResponse.objects.get(pk=response_id)
        canned.delete()
    except CannedResponse.DoesNotExist:
        pass

    return redirect("escalated:admin_canned_responses_index")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@login_required
def settings_index(request):
    """Display and manage Escalated settings."""
    check = _require_admin(request)
    if check:
        return check

    all_settings = EscalatedSetting.objects.all()

    return render(request, "Escalated/Admin/Settings", props={
        "settings": EscalatedSettingSerializer.serialize_as_dict(all_settings),
    })


@login_required
def settings_update(request):
    """Update Escalated settings."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    # Boolean settings (sent as "1"/"0" or absent)
    bool_keys = ["guest_tickets_enabled", "allow_customer_close"]
    for key in bool_keys:
        value = "1" if request.POST.get(key) in ("1", "true", "on") else "0"
        EscalatedSetting.set(key, value)

    # Integer settings
    int_keys = [
        "auto_close_resolved_after_days",
        "max_attachments_per_reply",
        "max_attachment_size_kb",
    ]
    for key in int_keys:
        raw = request.POST.get(key)
        if raw is not None:
            try:
                value = str(max(0, int(raw)))
                EscalatedSetting.set(key, value)
            except (ValueError, TypeError):
                pass

    return redirect("escalated:admin_settings")
