import json
import re as re_module

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Q, Avg, F, Max
from django.http import HttpResponseForbidden, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _
from inertia import render

from escalated.models import (
    Ticket,
    Tag,
    Department,
    SlaPolicy,
    EscalationRule,
    CannedResponse,
    EscalatedSetting,
    Macro,
    Reply,
    SatisfactionRating,
    AuditLog,
    TicketStatus,
    BusinessSchedule,
    Holiday,
    Role,
    Permission,
    CustomField,
    CustomFieldValue,
    TicketLink,
    SideConversation,
    SideConversationReply,
    ArticleCategory,
    Article,
    AgentProfile,
    Skill,
    AgentSkill,
    AgentCapacity,
    Webhook,
    WebhookDelivery,
    Automation,
    TwoFactor,
    CustomObject,
    CustomObjectRecord,
)
from escalated.permissions import is_admin, is_agent
from escalated.serializers import (
    TicketSerializer,
    ReplySerializer,
    TagSerializer,
    DepartmentSerializer,
    SlaPolicySerializer,
    EscalationRuleSerializer,
    CannedResponseSerializer,
    EscalatedSettingSerializer,
    ActivitySerializer,
    AttachmentSerializer,
    MacroSerializer,
    SatisfactionRatingSerializer,
    AuditLogSerializer,
    TicketStatusSerializer,
    BusinessScheduleSerializer,
    HolidaySerializer,
    RoleSerializer,
    PermissionSerializer,
    CustomFieldSerializer,
    TicketLinkSerializer,
    SideConversationSerializer,
    SideConversationReplySerializer,
    ArticleCategorySerializer,
    ArticleSerializer,
    AgentProfileSerializer,
    SkillSerializer,
    AgentCapacitySerializer,
    WebhookSerializer,
    WebhookDeliverySerializer,
    AutomationSerializer,
    CustomObjectSerializer,
    CustomObjectRecordSerializer,
)
from escalated.services.ticket_service import TicketService

User = get_user_model()


def _require_admin(request):
    """Return an error response if user is not admin, else None."""
    if not request.user.is_authenticated:
        return redirect("login")
    if not is_admin(request.user):
        return HttpResponseForbidden(_("Admin access required."))
    return None


# Keys whose values should be masked in the settings response
_SENSITIVE_SETTING_KEYS = {
    "mailgun_signing_key",
    "postmark_inbound_token",
    "imap_password",
}


def _mask_secret(value: str) -> str:
    """Mask a secret value, showing only the first 3 characters."""
    if not value:
        return ''
    if len(value) <= 6:
        return '*' * len(value)
    return value[:3] + '*' * min(len(value) - 3, 12)


def _is_masked_value(value: str | None) -> bool:
    """Return True if the value looks like a masked secret (e.g. 'abc************')."""
    if not value:
        return False
    return bool(re_module.match(r'^.{0,3}\*{3,}$', value))


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

    # CSAT stats
    csat_ratings = SatisfactionRating.objects.filter(
        created_at__gte=thirty_days_ago
    )
    avg_csat = csat_ratings.aggregate(avg_rating=Avg("rating"))["avg_rating"]
    total_ratings = csat_ratings.count()
    csat_breakdown = {}
    for r in range(1, 6):
        csat_breakdown[str(r)] = csat_ratings.filter(rating=r).count()

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
        "csat": {
            "average": round(avg_csat, 1) if avg_csat else None,
            "total": total_ratings,
            "breakdown": csat_breakdown,
        },
    })


# ---------------------------------------------------------------------------
# Tickets (List + Detail + Actions)
# ---------------------------------------------------------------------------


def _get_agents():
    """Return list of users who are agents or admins."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    users = User.objects.filter(is_active=True)
    return [
        {"id": u.pk, "name": u.get_full_name() or u.username, "email": u.email}
        for u in users
        if is_agent(u) or is_admin(u)
    ]


@login_required
def tickets_index(request):
    """List all tickets with filters for admin."""
    check = _require_admin(request)
    if check:
        return check

    tickets = Ticket.objects.select_related(
        "assigned_to", "department"
    ).prefetch_related("tags")

    # Apply filters
    status = request.GET.get("status")
    if status:
        tickets = tickets.filter(status=status)

    priority = request.GET.get("priority")
    if priority:
        tickets = tickets.filter(priority=priority)

    assigned = request.GET.get("assigned")
    if assigned == "unassigned":
        tickets = tickets.filter(assigned_to__isnull=True)
    elif assigned:
        tickets = tickets.filter(assigned_to_id=assigned)

    department = request.GET.get("department")
    if department:
        tickets = tickets.filter(department_id=department)

    tag = request.GET.get("tag")
    if tag:
        tickets = tickets.filter(tags__slug=tag)

    ticket_type = request.GET.get("ticket_type")
    if ticket_type:
        tickets = tickets.filter(ticket_type=ticket_type)

    search = request.GET.get("search")
    if search:
        tickets = tickets.search(search)

    # Following filter
    following = request.GET.get("following")
    if following:
        tickets = tickets.filter(ticket_followers__user=request.user)

    sort = request.GET.get("sort", "-created_at")
    allowed_sorts = [
        "created_at", "-created_at", "priority", "-priority",
        "updated_at", "-updated_at",
    ]
    if sort in allowed_sorts:
        tickets = tickets.order_by(sort)

    paginator = Paginator(tickets, 25)
    page = paginator.get_page(request.GET.get("page", 1))

    return render(request, "Escalated/Admin/Tickets/Index", props={
        "tickets": TicketSerializer.serialize_list(page.object_list),
        "pagination": {
            "current_page": page.number,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
        },
        "filters": {
            "status": status,
            "priority": priority,
            "assigned": assigned,
            "department": department,
            "tag": tag,
            "search": search,
            "sort": sort,
            "following": following,
        },
        "departments": DepartmentSerializer.serialize_list(
            Department.objects.filter(is_active=True)
        ),
        "tags": TagSerializer.serialize_list(Tag.objects.all()),
        "agents": _get_agents(),
    })


@login_required
def tickets_show(request, ticket_id):
    """Show a ticket with all details for admin."""
    check = _require_admin(request)
    if check:
        return check

    try:
        ticket = Ticket.objects.select_related(
            "assigned_to", "department", "sla_policy"
        ).prefetch_related(
            "tags",
            "replies__author",
            "replies__attachments",
            "activities",
            "attachments",
        ).get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    replies = ticket.replies.filter(is_deleted=False).select_related("author")
    activities = ticket.activities.all()[:50]

    canned_responses = CannedResponse.objects.filter(
        Q(is_shared=True) | Q(created_by=request.user)
    )

    # Macros available to this user (shared + own)
    macros = Macro.objects.filter(
        Q(is_shared=True) | Q(created_by=request.user)
    ).order_by("order")

    # Pinned notes
    pinned_notes = ticket.replies.filter(
        is_deleted=False, is_internal_note=True, is_pinned=True
    ).select_related("author")

    # Satisfaction rating
    try:
        satisfaction_rating = ticket.satisfaction_rating
        satisfaction_data = SatisfactionRatingSerializer.serialize(satisfaction_rating)
    except SatisfactionRating.DoesNotExist:
        satisfaction_data = None

    return render(request, "Escalated/Admin/Tickets/Show", props={
        "ticket": TicketSerializer.serialize(ticket),
        "replies": ReplySerializer.serialize_list(replies),
        "activities": [ActivitySerializer.serialize(a) for a in activities],
        "attachments": AttachmentSerializer.serialize_list(ticket.attachments.all()),
        "agents": _get_agents(),
        "departments": DepartmentSerializer.serialize_list(
            Department.objects.filter(is_active=True)
        ),
        "tags": TagSerializer.serialize_list(Tag.objects.all()),
        "canned_responses": CannedResponseSerializer.serialize_list(canned_responses),
        "macros": MacroSerializer.serialize_list(macros),
        "statuses": [{"value": s.value, "label": s.label} for s in Ticket.Status],
        "priorities": [{"value": p.value, "label": p.label} for p in Ticket.Priority],
        "is_following": ticket.is_followed_by(request.user.pk),
        "followers_count": ticket.followers_count,
        "pinned_notes": ReplySerializer.serialize_list(pinned_notes),
        "satisfaction_rating": satisfaction_data,
    })


@login_required
def tickets_reply(request, ticket_id):
    """Admin reply to a ticket."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    body = request.POST.get("body", "").strip()
    if not body:
        return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)

    service = TicketService()
    reply = service.reply(ticket, request.user, {"body": body})

    files = request.FILES.getlist("attachments")
    if files:
        from escalated.services.attachment_service import AttachmentService
        from escalated.conf import get_setting
        for f in files[:get_setting("MAX_ATTACHMENTS")]:
            try:
                AttachmentService.attach(reply, f)
            except Exception:
                pass

    return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)


@login_required
def tickets_note(request, ticket_id):
    """Add an internal note to a ticket (admin)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    body = request.POST.get("body", "").strip()
    if not body:
        return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)

    service = TicketService()
    service.add_note(ticket, request.user, body)

    return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)


@login_required
def tickets_assign(request, ticket_id):
    """Assign a ticket to an agent (admin)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    from django.contrib.auth import get_user_model
    User = get_user_model()

    agent_id = request.POST.get("agent_id")
    if not agent_id:
        service = TicketService()
        service.unassign(ticket, request.user)
    else:
        try:
            agent = User.objects.get(pk=agent_id)
        except User.DoesNotExist:
            return HttpResponseNotFound(_("Agent not found"))

        service = TicketService()
        service.assign(ticket, request.user, agent)

    return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)


@login_required
def tickets_status(request, ticket_id):
    """Change ticket status (admin)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    new_status = request.POST.get("status")
    valid_statuses = [s.value for s in Ticket.Status]
    if new_status not in valid_statuses:
        return HttpResponseForbidden(_("Invalid status."))

    service = TicketService()
    service.change_status(ticket, request.user, new_status)

    return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)


@login_required
def tickets_priority(request, ticket_id):
    """Change ticket priority (admin)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    new_priority = request.POST.get("priority")
    valid_priorities = [p.value for p in Ticket.Priority]
    if new_priority not in valid_priorities:
        return HttpResponseForbidden(_("Invalid priority."))

    service = TicketService()
    service.change_priority(ticket, request.user, new_priority)

    return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)


@login_required
def tickets_tags(request, ticket_id):
    """Add or remove tags from a ticket (admin)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    service = TicketService()

    add_tags = request.POST.getlist("add_tags")
    if add_tags:
        service.add_tags(ticket, request.user, [int(t) for t in add_tags])

    remove_tags = request.POST.getlist("remove_tags")
    if remove_tags:
        service.remove_tags(ticket, request.user, [int(t) for t in remove_tags])

    return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)


@login_required
def tickets_department(request, ticket_id):
    """Change ticket department (admin)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    department_id = request.POST.get("department_id")
    try:
        department = Department.objects.get(pk=department_id)
    except Department.DoesNotExist:
        return HttpResponseNotFound(_("Department not found"))

    service = TicketService()
    service.change_department(ticket, request.user, department)

    return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)


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
                "errors": {"name": _("Name is required.")},
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
        return HttpResponseNotFound(_("Department not found"))

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
        return HttpResponseForbidden(_("Method not allowed"))

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
                "errors": {"name": _("Name is required.")},
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
        return HttpResponseNotFound(_("SLA Policy not found"))

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
        return HttpResponseForbidden(_("Method not allowed"))

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
                "errors": {"name": _("Name is required.")},
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
        return HttpResponseNotFound(_("Escalation rule not found"))

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
        return HttpResponseForbidden(_("Method not allowed"))

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
                "errors": {"name": _("Name is required.")},
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
        return HttpResponseNotFound(_("Tag not found"))

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
        return HttpResponseForbidden(_("Method not allowed"))

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
                "errors": {"title": _("Title is required.")},
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
        return HttpResponseNotFound(_("Canned response not found"))

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
        return HttpResponseForbidden(_("Method not allowed"))

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
    settings_dict = EscalatedSettingSerializer.serialize_as_dict(all_settings)

    # Mask sensitive values before sending to frontend
    for key in _SENSITIVE_SETTING_KEYS:
        if key in settings_dict and settings_dict[key]:
            settings_dict[key] = _mask_secret(settings_dict[key])

    return render(request, "Escalated/Admin/Settings", props={
        "settings": settings_dict,
    })


@login_required
def settings_update(request):
    """Update Escalated settings."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    # Boolean settings (sent as "1"/"0" or absent)
    bool_keys = [
        "guest_tickets_enabled",
        "allow_customer_close",
        "inbound_email_enabled",
        "show_powered_by",
    ]
    for key in bool_keys:
        value = "1" if request.POST.get(key) in ("1", "true", "on") else "0"
        EscalatedSetting.set(key, value)

    # Integer settings
    int_keys = [
        "auto_close_resolved_after_days",
        "max_attachments_per_reply",
        "max_attachment_size_kb",
        "imap_port",
    ]
    for key in int_keys:
        raw = request.POST.get(key)
        if raw is not None:
            try:
                value = str(max(0, int(raw)))
                EscalatedSetting.set(key, value)
            except (ValueError, TypeError):
                pass

    # String settings
    prefix = request.POST.get("ticket_reference_prefix", "").strip()
    if prefix and prefix.isalnum() and len(prefix) <= 10:
        EscalatedSetting.set("ticket_reference_prefix", prefix)

    # Inbound email string settings
    inbound_str_keys = [
        "inbound_email_adapter",
        "inbound_email_address",
        "mailgun_signing_key",
        "postmark_inbound_token",
        "ses_region",
        "ses_topic_arn",
        "imap_host",
        "imap_encryption",
        "imap_username",
        "imap_password",
        "imap_mailbox",
    ]
    for key in inbound_str_keys:
        raw = request.POST.get(key)
        if raw is not None:
            stripped = raw.strip()
            # Skip saving sensitive fields that still contain masked values
            if key in _SENSITIVE_SETTING_KEYS and _is_masked_value(stripped):
                continue
            EscalatedSetting.set(key, stripped)

    return redirect("escalated:admin_settings")


# ---------------------------------------------------------------------------
# Bulk Actions (Admin)
# ---------------------------------------------------------------------------


@login_required
def tickets_bulk_action(request):
    """Perform bulk actions on multiple tickets (admin)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        body = request.POST

    action = body.get("action", "")
    ticket_ids = body.get("ticket_ids", [])
    value = body.get("value")

    if not action or not ticket_ids:
        return redirect("escalated:admin_tickets_index")

    service = TicketService()
    user = request.user
    success_count = 0

    tickets = Ticket.objects.filter(pk__in=ticket_ids)

    for ticket in tickets:
        try:
            if action == "assign":
                if value:
                    try:
                        agent = User.objects.get(pk=int(value))
                        service.assign(ticket, user, agent)
                    except User.DoesNotExist:
                        continue
                else:
                    service.unassign(ticket, user)
            elif action == "status":
                valid_statuses = [s.value for s in Ticket.Status]
                if value in valid_statuses:
                    service.change_status(ticket, user, value)
            elif action == "priority":
                valid_priorities = [p.value for p in Ticket.Priority]
                if value in valid_priorities:
                    service.change_priority(ticket, user, value)
            elif action == "tag":
                tag_ids = value if isinstance(value, list) else [value]
                service.add_tags(ticket, user, [int(t) for t in tag_ids])
            elif action == "close":
                service.close(ticket, user)
            elif action == "delete":
                ticket.delete()
            else:
                continue
            success_count += 1
        except Exception:
            pass

    return redirect("escalated:admin_tickets_index")


# ---------------------------------------------------------------------------
# Apply Macro (Admin)
# ---------------------------------------------------------------------------


@login_required
def tickets_apply_macro(request, ticket_id):
    """Apply a macro to a ticket (admin)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    macro_id = request.POST.get("macro_id")
    if not macro_id:
        return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)

    try:
        macro = Macro.objects.filter(
            Q(is_shared=True) | Q(created_by=request.user)
        ).get(pk=macro_id)
    except Macro.DoesNotExist:
        return HttpResponseNotFound(_("Macro not found"))

    from escalated.services.macro_service import MacroService
    macro_service = MacroService()
    macro_service.apply(macro, ticket, request.user)

    return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)


# ---------------------------------------------------------------------------
# Follow / Unfollow (Admin)
# ---------------------------------------------------------------------------


@login_required
def tickets_follow(request, ticket_id):
    """Toggle follow/unfollow on a ticket (admin)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    user_id = request.user.pk

    if ticket.is_followed_by(user_id):
        ticket.unfollow(user_id)
    else:
        ticket.follow(user_id)

    return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)


# ---------------------------------------------------------------------------
# Presence Indicators (Admin)
# ---------------------------------------------------------------------------


@login_required
def tickets_presence(request, ticket_id):
    """Report presence on a ticket and return other viewers (admin)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    user_id = request.user.pk
    user_name = request.user.get_full_name() or request.user.username
    cache_key = f"escalated.presence.{ticket.pk}.{user_id}"

    # Store this user's presence with 30s TTL
    cache.set(cache_key, {"id": user_id, "name": user_name}, 30)

    # Track active user IDs for this ticket (with 120s TTL)
    list_key = f"escalated.presence_list.{ticket.pk}"
    active_ids = cache.get(list_key, [])
    if user_id not in active_ids:
        active_ids.append(user_id)
    cache.set(list_key, active_ids, 120)

    # Collect viewers (other users who are still present)
    viewers = []
    for uid in active_ids:
        if uid != user_id:
            viewer_data = cache.get(f"escalated.presence.{ticket.pk}.{uid}")
            if viewer_data:
                viewers.append(viewer_data)

    return JsonResponse({"viewers": viewers})


# ---------------------------------------------------------------------------
# Pin / Unpin Reply (Admin)
# ---------------------------------------------------------------------------


@login_required
def tickets_pin_reply(request, ticket_id, reply_id):
    """Toggle pin on an internal note (admin)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    try:
        reply = Reply.objects.get(pk=reply_id, ticket=ticket)
    except Reply.DoesNotExist:
        return HttpResponseNotFound(_("Reply not found"))

    if not reply.is_internal_note:
        return HttpResponseForbidden(_("Only internal notes can be pinned."))

    reply.is_pinned = not reply.is_pinned
    reply.save(update_fields=["is_pinned", "updated_at"])

    return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)


# ---------------------------------------------------------------------------
# Macros CRUD
# ---------------------------------------------------------------------------


@login_required
def macros_index(request):
    """List all macros."""
    check = _require_admin(request)
    if check:
        return check

    macros = Macro.objects.select_related("created_by").order_by("order")
    return render(request, "Escalated/Admin/Macros/Index", props={
        "macros": MacroSerializer.serialize_list(macros),
    })


@login_required
def macros_create(request):
    """Create a new macro."""
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            return render(request, "Escalated/Admin/Macros/Create", props={
                "errors": {"name": _("Name is required.")},
            })

        try:
            actions = json.loads(request.POST.get("actions", "[]"))
        except (json.JSONDecodeError, TypeError):
            actions = []

        Macro.objects.create(
            name=name,
            description=request.POST.get("description", ""),
            actions=actions,
            is_shared=request.POST.get("is_shared", "true") == "true",
            order=int(request.POST.get("order", 0)),
            created_by=request.user,
        )
        return redirect("escalated:admin_macros_index")

    return render(request, "Escalated/Admin/Macros/Create", props={})


@login_required
def macros_edit(request, macro_id):
    """Edit an existing macro."""
    check = _require_admin(request)
    if check:
        return check

    try:
        macro = Macro.objects.get(pk=macro_id)
    except Macro.DoesNotExist:
        return HttpResponseNotFound(_("Macro not found"))

    if request.method == "POST":
        macro.name = request.POST.get("name", macro.name)
        macro.description = request.POST.get("description", macro.description)
        macro.is_shared = request.POST.get("is_shared", "true") == "true"
        macro.order = int(request.POST.get("order", macro.order))

        try:
            macro.actions = json.loads(request.POST.get("actions", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass

        macro.save()
        return redirect("escalated:admin_macros_index")

    return render(request, "Escalated/Admin/Macros/Edit", props={
        "macro": MacroSerializer.serialize(macro),
    })


@login_required
def macros_delete(request, macro_id):
    """Delete a macro."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        macro = Macro.objects.get(pk=macro_id)
        macro.delete()
    except Macro.DoesNotExist:
        pass

    return redirect("escalated:admin_macros_index")


# ---------------------------------------------------------------------------
# Audit Logs (read-only)
# ---------------------------------------------------------------------------


@login_required
def audit_logs_index(request):
    check = _require_admin(request)
    if check:
        return check

    logs = AuditLog.objects.select_related("user", "auditable_content_type")

    user_id = request.GET.get("user_id")
    if user_id:
        logs = logs.filter(user_id=user_id)

    action = request.GET.get("action")
    if action:
        logs = logs.filter(action=action)

    auditable_type = request.GET.get("auditable_type")
    if auditable_type:
        logs = logs.filter(auditable_content_type__model=auditable_type)

    date_from = request.GET.get("date_from")
    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)

    date_to = request.GET.get("date_to")
    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)

    paginator = Paginator(logs, 50)
    page = paginator.get_page(request.GET.get("page", 1))

    return render(request, "Escalated/Admin/AuditLog/Index", props={
        "logs": AuditLogSerializer.serialize_list(page.object_list),
        "pagination": {
            "current_page": page.number,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
        },
        "filters": {
            "user_id": user_id,
            "action": action,
            "auditable_type": auditable_type,
            "date_from": date_from,
            "date_to": date_to,
        },
        "users": [
            {"id": u.pk, "name": u.get_full_name() or u.username}
            for u in User.objects.filter(is_active=True)
        ],
        "actions": ["created", "updated", "deleted"],
        "resource_types": list(
            AuditLog.objects.values_list(
                "auditable_content_type__model", flat=True
            ).distinct()
        ),
    })


# ---------------------------------------------------------------------------
# Ticket Statuses CRUD
# ---------------------------------------------------------------------------


@login_required
def statuses_index(request):
    check = _require_admin(request)
    if check:
        return check

    statuses = TicketStatus.objects.all()
    return render(request, "Escalated/Admin/Statuses/Index", props={
        "statuses": TicketStatusSerializer.serialize_list(statuses),
        "categories": ["new", "open", "pending", "on_hold", "solved"],
    })


@login_required
def statuses_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        label = request.POST.get("label", "").strip()
        if not label:
            return render(request, "Escalated/Admin/Statuses/Form", props={
                "errors": {"label": _("Label is required.")},
                "categories": ["new", "open", "pending", "on_hold", "solved"],
            })

        category = request.POST.get("category", "open")
        is_default = request.POST.get("is_default", "false") == "true"

        if is_default:
            TicketStatus.objects.filter(category=category).update(is_default=False)

        TicketStatus.objects.create(
            label=label,
            category=category,
            color=request.POST.get("color", "#6b7280"),
            description=request.POST.get("description", ""),
            position=int(request.POST.get("position", 0)),
            is_default=is_default,
        )
        return redirect("escalated:admin_statuses_index")

    return render(request, "Escalated/Admin/Statuses/Form", props={
        "categories": ["new", "open", "pending", "on_hold", "solved"],
    })


@login_required
def statuses_edit(request, status_id):
    check = _require_admin(request)
    if check:
        return check

    try:
        status = TicketStatus.objects.get(pk=status_id)
    except TicketStatus.DoesNotExist:
        return HttpResponseNotFound(_("Status not found"))

    if request.method == "POST":
        status.label = request.POST.get("label", status.label)
        status.category = request.POST.get("category", status.category)
        status.color = request.POST.get("color", status.color)
        status.description = request.POST.get("description", status.description)
        status.position = int(request.POST.get("position", status.position))

        is_default = request.POST.get("is_default", "false") == "true"
        if is_default and not status.is_default:
            TicketStatus.objects.filter(category=status.category).exclude(
                pk=status.pk
            ).update(is_default=False)
        status.is_default = is_default

        status.save()
        return redirect("escalated:admin_statuses_index")

    return render(request, "Escalated/Admin/Statuses/Form", props={
        "status": TicketStatusSerializer.serialize(status),
        "categories": ["new", "open", "pending", "on_hold", "solved"],
    })


@login_required
def statuses_delete(request, status_id):
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        status = TicketStatus.objects.get(pk=status_id)
        status.delete()
    except TicketStatus.DoesNotExist:
        pass

    return redirect("escalated:admin_statuses_index")


# ---------------------------------------------------------------------------
# Business Hours CRUD
# ---------------------------------------------------------------------------


@login_required
def business_hours_index(request):
    check = _require_admin(request)
    if check:
        return check

    schedules = BusinessSchedule.objects.prefetch_related("holidays").all()
    return render(request, "Escalated/Admin/BusinessHours/Index", props={
        "schedules": BusinessScheduleSerializer.serialize_list(schedules),
    })


@login_required
def business_hours_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            return render(request, "Escalated/Admin/BusinessHours/Form", props={
                "errors": {"name": _("Name is required.")},
            })

        is_default = request.POST.get("is_default", "false") == "true"
        if is_default:
            BusinessSchedule.objects.filter(is_default=True).update(is_default=False)

        try:
            schedule_data = json.loads(request.POST.get("schedule", "{}"))
        except (json.JSONDecodeError, TypeError):
            schedule_data = {}

        sched = BusinessSchedule.objects.create(
            name=name,
            timezone=request.POST.get("timezone", "UTC"),
            is_default=is_default,
            schedule=schedule_data,
        )

        try:
            holidays = json.loads(request.POST.get("holidays", "[]"))
        except (json.JSONDecodeError, TypeError):
            holidays = []

        for h in holidays:
            Holiday.objects.create(
                schedule=sched,
                name=h.get("name", ""),
                date=h.get("date"),
                recurring=h.get("recurring", False),
            )

        return redirect("escalated:admin_business_hours_index")

    from zoneinfo import available_timezones
    return render(request, "Escalated/Admin/BusinessHours/Form", props={
        "timezones": sorted(available_timezones()),
    })


@login_required
def business_hours_edit(request, schedule_id):
    check = _require_admin(request)
    if check:
        return check

    try:
        sched = BusinessSchedule.objects.prefetch_related("holidays").get(pk=schedule_id)
    except BusinessSchedule.DoesNotExist:
        return HttpResponseNotFound(_("Business schedule not found"))

    if request.method == "POST":
        sched.name = request.POST.get("name", sched.name)
        sched.timezone = request.POST.get("timezone", sched.timezone)

        is_default = request.POST.get("is_default", "false") == "true"
        if is_default and not sched.is_default:
            BusinessSchedule.objects.filter(is_default=True).exclude(
                pk=sched.pk
            ).update(is_default=False)
        sched.is_default = is_default

        try:
            sched.schedule = json.loads(request.POST.get("schedule", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass

        sched.save()

        # Sync holidays
        sched.holidays.all().delete()
        try:
            holidays = json.loads(request.POST.get("holidays", "[]"))
        except (json.JSONDecodeError, TypeError):
            holidays = []

        for h in holidays:
            Holiday.objects.create(
                schedule=sched,
                name=h.get("name", ""),
                date=h.get("date"),
                recurring=h.get("recurring", False),
            )

        return redirect("escalated:admin_business_hours_index")

    from zoneinfo import available_timezones
    return render(request, "Escalated/Admin/BusinessHours/Edit", props={
        "schedule": BusinessScheduleSerializer.serialize(sched),
        "timezones": sorted(available_timezones()),
    })


@login_required
def business_hours_delete(request, schedule_id):
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        sched = BusinessSchedule.objects.get(pk=schedule_id)
        sched.delete()
    except BusinessSchedule.DoesNotExist:
        pass

    return redirect("escalated:admin_business_hours_index")


# ---------------------------------------------------------------------------
# Roles CRUD
# ---------------------------------------------------------------------------


@login_required
def roles_index(request):
    check = _require_admin(request)
    if check:
        return check

    roles = Role.objects.annotate(users__count=Count("users"))
    return render(request, "Escalated/Admin/Roles/Index", props={
        "roles": RoleSerializer.serialize_list(roles),
    })


@login_required
def roles_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            return render(request, "Escalated/Admin/Roles/Form", props={
                "errors": {"name": _("Name is required.")},
                "permissions": PermissionSerializer.serialize_grouped(Permission.objects.all()),
            })

        role = Role.objects.create(
            name=name,
            description=request.POST.get("description", ""),
        )

        permission_ids = request.POST.getlist("permissions")
        if permission_ids:
            role.permissions.set(permission_ids)

        return redirect("escalated:admin_roles_index")

    return render(request, "Escalated/Admin/Roles/Form", props={
        "permissions": PermissionSerializer.serialize_grouped(Permission.objects.all()),
    })


@login_required
def roles_edit(request, role_id):
    check = _require_admin(request)
    if check:
        return check

    try:
        role = Role.objects.prefetch_related("permissions").get(pk=role_id)
    except Role.DoesNotExist:
        return HttpResponseNotFound(_("Role not found"))

    if request.method == "POST":
        role.name = request.POST.get("name", role.name)
        role.description = request.POST.get("description", role.description)
        role.save()

        permission_ids = request.POST.getlist("permissions")
        role.permissions.set(permission_ids)

        return redirect("escalated:admin_roles_index")

    return render(request, "Escalated/Admin/Roles/Form", props={
        "role": RoleSerializer.serialize(role, include_permissions=True),
        "permissions": PermissionSerializer.serialize_grouped(Permission.objects.all()),
    })


@login_required
def roles_delete(request, role_id):
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        role = Role.objects.get(pk=role_id)
        if role.is_system:
            return HttpResponseForbidden(_("System roles cannot be deleted."))
        role.delete()
    except Role.DoesNotExist:
        pass

    return redirect("escalated:admin_roles_index")


# ---------------------------------------------------------------------------
# Custom Fields CRUD
# ---------------------------------------------------------------------------


@login_required
def custom_fields_index(request):
    """List all custom fields."""
    check = _require_admin(request)
    if check:
        return check

    fields = CustomField.objects.all().order_by("position")
    return render(request, "Escalated/Admin/CustomFields/Index", props={
        "custom_fields": CustomFieldSerializer.serialize_list(fields),
    })


@login_required
def custom_fields_create(request):
    """Create a new custom field."""
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            return render(request, "Escalated/Admin/CustomFields/Create", props={
                "errors": {"name": _("Name is required.")},
                "contexts": [
                    {"value": c.value, "label": c.label}
                    for c in CustomField.Context
                ],
            })

        try:
            options = json.loads(request.POST.get("options", "null"))
        except (json.JSONDecodeError, TypeError):
            options = None

        try:
            validation_rules = json.loads(
                request.POST.get("validation_rules", "null")
            )
        except (json.JSONDecodeError, TypeError):
            validation_rules = None

        try:
            conditions = json.loads(request.POST.get("conditions", "null"))
        except (json.JSONDecodeError, TypeError):
            conditions = None

        CustomField.objects.create(
            name=name,
            slug=slugify(request.POST.get("slug", "") or name),
            type=request.POST.get("type", CustomField.FieldType.TEXT),
            context=request.POST.get("context", CustomField.Context.TICKET),
            options=options,
            required=request.POST.get("required", "false") == "true",
            placeholder=request.POST.get("placeholder", ""),
            description=request.POST.get("description", ""),
            validation_rules=validation_rules,
            conditions=conditions,
            position=int(request.POST.get("position", 0)),
            active=request.POST.get("active", "true") == "true",
        )
        return redirect("escalated:admin_custom_fields_index")

    return render(request, "Escalated/Admin/CustomFields/Create", props={
        "contexts": [
            {"value": c.value, "label": c.label}
            for c in CustomField.Context
        ],
    })


@login_required
def custom_fields_edit(request, field_id):
    """Edit an existing custom field."""
    check = _require_admin(request)
    if check:
        return check

    try:
        field = CustomField.objects.get(pk=field_id)
    except CustomField.DoesNotExist:
        return HttpResponseNotFound(_("Custom field not found"))

    if request.method == "POST":
        field.name = request.POST.get("name", field.name)
        field.slug = slugify(request.POST.get("slug", "") or field.name)
        field.type = request.POST.get("type", field.type)
        field.context = request.POST.get("context", field.context)
        field.required = request.POST.get("required", "false") == "true"
        field.placeholder = request.POST.get("placeholder", field.placeholder)
        field.description = request.POST.get("description", field.description)
        field.position = int(request.POST.get("position", field.position))
        field.active = request.POST.get("active", "true") == "true"

        try:
            field.options = json.loads(request.POST.get("options", "null"))
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            field.validation_rules = json.loads(
                request.POST.get("validation_rules", "null")
            )
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            field.conditions = json.loads(
                request.POST.get("conditions", "null")
            )
        except (json.JSONDecodeError, TypeError):
            pass

        field.save()
        return redirect("escalated:admin_custom_fields_index")

    return render(request, "Escalated/Admin/CustomFields/Edit", props={
        "custom_field": CustomFieldSerializer.serialize(field),
        "contexts": [
            {"value": c.value, "label": c.label}
            for c in CustomField.Context
        ],
    })


@login_required
def custom_fields_delete(request, field_id):
    """Delete a custom field."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        field = CustomField.objects.get(pk=field_id)
        field.delete()
    except CustomField.DoesNotExist:
        pass

    return redirect("escalated:admin_custom_fields_index")


@login_required
def custom_fields_reorder(request):
    """Reorder custom fields via JSON body."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    positions = body.get("positions", [])
    for item in positions:
        CustomField.objects.filter(pk=item.get("id")).update(
            position=item.get("position", 0)
        )

    return JsonResponse({"success": True})


# ---------------------------------------------------------------------------
# Ticket Links (JSON API)
# ---------------------------------------------------------------------------


@login_required
def ticket_links_index(request, ticket_id):
    """List all links for a ticket."""
    check = _require_admin(request)
    if check:
        return check

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return JsonResponse({"error": "Ticket not found"}, status=404)

    parent_links = ticket.links_as_parent.select_related("child_ticket").all()
    child_links = ticket.links_as_child.select_related("parent_ticket").all()

    links = []
    for link in parent_links:
        links.append(TicketLinkSerializer.serialize(link, direction='parent'))
    for link in child_links:
        links.append(TicketLinkSerializer.serialize(link, direction='child'))

    return JsonResponse({"links": links})


@login_required
def ticket_links_store(request, ticket_id):
    """Create a link between two tickets."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return JsonResponse({"error": "Ticket not found"}, status=404)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    target_reference = body.get("target_reference", "").strip()
    link_type = body.get("link_type", TicketLink.LinkType.RELATED)

    if not target_reference:
        return JsonResponse({"error": "target_reference is required"}, status=400)

    try:
        target = Ticket.objects.get(reference=target_reference)
    except Ticket.DoesNotExist:
        return JsonResponse({"error": "Target ticket not found"}, status=404)

    # Prevent self-linking
    if target.pk == ticket.pk:
        return JsonResponse({"error": "Cannot link a ticket to itself"}, status=400)

    # Prevent duplicates
    exists = TicketLink.objects.filter(
        parent_ticket=ticket, child_ticket=target, link_type=link_type
    ).exists() or TicketLink.objects.filter(
        parent_ticket=target, child_ticket=ticket, link_type=link_type
    ).exists()

    if exists:
        return JsonResponse({"error": "Link already exists"}, status=400)

    link = TicketLink.objects.create(
        parent_ticket=ticket,
        child_ticket=target,
        link_type=link_type,
    )

    return JsonResponse({
        "link": TicketLinkSerializer.serialize(link, direction='parent'),
    })


@login_required
def ticket_links_destroy(request, ticket_id, link_id):
    """Delete a ticket link."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        link = TicketLink.objects.get(pk=link_id)
        # Verify the link belongs to this ticket (as parent or child)
        if link.parent_ticket_id != ticket_id and link.child_ticket_id != ticket_id:
            return JsonResponse({"error": "Link not found for this ticket"}, status=404)
        link.delete()
    except TicketLink.DoesNotExist:
        return JsonResponse({"error": "Link not found"}, status=404)

    return JsonResponse({"success": True})


# ---------------------------------------------------------------------------
# Ticket Merging
# ---------------------------------------------------------------------------


@login_required
def ticket_merge_search(request):
    """Search for merge target tickets."""
    check = _require_admin(request)
    if check:
        return check

    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"tickets": []})

    tickets = (
        Ticket.objects.filter(merged_into__isnull=True)
        .filter(
            Q(reference__icontains=q)
            | Q(subject__icontains=q)
        )
        .order_by("-created_at")[:10]
    )

    return JsonResponse({
        "tickets": [
            {
                "id": t.pk,
                "reference": t.reference,
                "subject": t.subject,
                "status": t.status,
            }
            for t in tickets
        ]
    })


@login_required
def ticket_merge(request, ticket_id):
    """Merge a ticket into a target ticket."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        source = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    target_reference = body.get("target_reference", "").strip()
    if not target_reference:
        return JsonResponse({"error": "target_reference is required"}, status=400)

    try:
        target = Ticket.objects.get(reference=target_reference)
    except Ticket.DoesNotExist:
        return JsonResponse({"error": "Target ticket not found"}, status=404)

    if target.pk == source.pk:
        return JsonResponse({"error": "Cannot merge a ticket into itself"}, status=400)

    from escalated.services.ticket_merge_service import TicketMergeService
    merge_service = TicketMergeService()
    merge_service.merge(source, target, merged_by_user_id=request.user.pk)

    return JsonResponse({"success": True, "merged_into": target.reference})


# ---------------------------------------------------------------------------
# Side Conversations
# ---------------------------------------------------------------------------


@login_required
def side_conversations_index(request, ticket_id):
    """List all side conversations for a ticket."""
    check = _require_admin(request)
    if check:
        return check

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return JsonResponse({"error": "Ticket not found"}, status=404)

    conversations = (
        ticket.side_conversations
        .select_related("created_by")
        .prefetch_related("replies__author")
        .all()
    )

    return JsonResponse({
        "side_conversations": SideConversationSerializer.serialize_list(conversations),
    })


@login_required
def side_conversations_store(request, ticket_id):
    """Create a new side conversation with an initial reply."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return JsonResponse({"error": "Ticket not found"}, status=404)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    subject = body.get("subject", "").strip()
    message_body = body.get("body", "").strip()
    channel = body.get("channel", SideConversation.Channel.INTERNAL)

    if not subject:
        return JsonResponse({"error": "subject is required"}, status=400)

    conversation = SideConversation.objects.create(
        ticket=ticket,
        subject=subject,
        channel=channel,
        created_by=request.user,
    )

    if message_body:
        SideConversationReply.objects.create(
            side_conversation=conversation,
            body=message_body,
            author=request.user,
        )

    # Re-fetch with relations for serialization
    conversation = (
        SideConversation.objects
        .select_related("created_by")
        .prefetch_related("replies__author")
        .get(pk=conversation.pk)
    )

    return JsonResponse({
        "side_conversation": SideConversationSerializer.serialize(conversation),
    })


@login_required
def side_conversations_reply(request, ticket_id, conversation_id):
    """Add a reply to a side conversation."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return JsonResponse({"error": "Ticket not found"}, status=404)

    try:
        conversation = SideConversation.objects.get(
            pk=conversation_id, ticket=ticket
        )
    except SideConversation.DoesNotExist:
        return JsonResponse({"error": "Side conversation not found"}, status=404)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    message_body = body.get("body", "").strip()
    if not message_body:
        return JsonResponse({"error": "body is required"}, status=400)

    reply = SideConversationReply.objects.create(
        side_conversation=conversation,
        body=message_body,
        author=request.user,
    )

    return JsonResponse({
        "reply": SideConversationReplySerializer.serialize(reply),
    })


@login_required
def side_conversations_close(request, ticket_id, conversation_id):
    """Close a side conversation."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return JsonResponse({"error": "Ticket not found"}, status=404)

    try:
        conversation = SideConversation.objects.get(
            pk=conversation_id, ticket=ticket
        )
    except SideConversation.DoesNotExist:
        return JsonResponse({"error": "Side conversation not found"}, status=404)

    conversation.status = "closed"
    conversation.save(update_fields=["status", "updated_at"])

    return JsonResponse({"success": True})


# ---------------------------------------------------------------------------
# Knowledge Base - Articles CRUD
# ---------------------------------------------------------------------------


@login_required
def articles_index(request):
    """List all KB articles with filters."""
    check = _require_admin(request)
    if check:
        return check

    articles = Article.objects.select_related("category", "author")

    search = request.GET.get("search")
    if search:
        articles = articles.search(search)

    status_filter = request.GET.get("status")
    if status_filter:
        articles = articles.filter(status=status_filter)

    category_filter = request.GET.get("category")
    if category_filter:
        articles = articles.filter(category_id=category_filter)

    paginator = Paginator(articles, 20)
    page = paginator.get_page(request.GET.get("page", 1))

    return render(request, "Escalated/Admin/KB/Articles/Index", props={
        "articles": ArticleSerializer.serialize_list(page.object_list),
        "pagination": {
            "current_page": page.number,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
        },
        "filters": {
            "search": search,
            "status": status_filter,
            "category": category_filter,
        },
        "categories": ArticleCategorySerializer.serialize_list(
            ArticleCategory.objects.ordered()
        ),
    })


@login_required
def articles_create(request):
    """Create a new KB article."""
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        if not title:
            return render(request, "Escalated/Admin/KB/Articles/Create", props={
                "errors": {"title": _("Title is required.")},
                "categories": ArticleCategorySerializer.serialize_list(
                    ArticleCategory.objects.ordered()
                ),
            })

        status = request.POST.get("status", Article.Status.DRAFT)
        published_at = None
        if status == Article.Status.PUBLISHED:
            published_at = timezone.now()

        category_id = request.POST.get("category_id")

        Article.objects.create(
            title=title,
            slug=slugify(request.POST.get("slug", "") or title),
            body=request.POST.get("body", ""),
            status=status,
            category_id=category_id if category_id else None,
            author=request.user,
            published_at=published_at,
        )
        return redirect("escalated:admin_articles_index")

    return render(request, "Escalated/Admin/KB/Articles/Create", props={
        "categories": ArticleCategorySerializer.serialize_list(
            ArticleCategory.objects.ordered()
        ),
    })


@login_required
def articles_edit(request, article_id):
    """Edit a KB article."""
    check = _require_admin(request)
    if check:
        return check

    try:
        article = Article.objects.select_related("category", "author").get(
            pk=article_id
        )
    except Article.DoesNotExist:
        return HttpResponseNotFound(_("Article not found"))

    if request.method == "POST":
        article.title = request.POST.get("title", article.title)
        article.slug = slugify(request.POST.get("slug", "") or article.title)
        article.body = request.POST.get("body", article.body)

        new_status = request.POST.get("status", article.status)
        if new_status == Article.Status.PUBLISHED and article.status != Article.Status.PUBLISHED:
            article.published_at = timezone.now()
        article.status = new_status

        category_id = request.POST.get("category_id")
        article.category_id = category_id if category_id else None

        article.save()
        return redirect("escalated:admin_articles_index")

    return render(request, "Escalated/Admin/KB/Articles/Edit", props={
        "article": ArticleSerializer.serialize(article),
        "categories": ArticleCategorySerializer.serialize_list(
            ArticleCategory.objects.ordered()
        ),
    })


@login_required
def articles_delete(request, article_id):
    """Delete a KB article."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        article = Article.objects.get(pk=article_id)
        article.delete()
    except Article.DoesNotExist:
        pass

    return redirect("escalated:admin_articles_index")


# ---------------------------------------------------------------------------
# Knowledge Base - Categories CRUD
# ---------------------------------------------------------------------------


@login_required
def kb_categories_index(request):
    """List all KB categories with article counts."""
    check = _require_admin(request)
    if check:
        return check

    categories = ArticleCategory.objects.annotate(
        articles_count=Count("articles")
    ).order_by("position", "name")

    return render(request, "Escalated/Admin/KB/Categories/Index", props={
        "categories": ArticleCategorySerializer.serialize_list(categories),
    })


@login_required
def kb_categories_store(request):
    """Create a new KB category."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Name is required"}, status=400)

    parent_id = request.POST.get("parent_id")

    ArticleCategory.objects.create(
        name=name,
        slug=slugify(name),
        parent_id=parent_id if parent_id else None,
        position=int(request.POST.get("position", 0)),
        description=request.POST.get("description", ""),
    )

    return redirect("escalated:admin_kb_categories_index")


@login_required
def kb_categories_update(request, category_id):
    """Update a KB category."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        category = ArticleCategory.objects.get(pk=category_id)
    except ArticleCategory.DoesNotExist:
        return HttpResponseNotFound(_("Category not found"))

    category.name = request.POST.get("name", category.name)
    category.slug = slugify(request.POST.get("slug", "") or category.name)
    category.description = request.POST.get("description", category.description)
    category.position = int(request.POST.get("position", category.position))

    parent_id = request.POST.get("parent_id")
    category.parent_id = parent_id if parent_id else None

    category.save()

    return redirect("escalated:admin_kb_categories_index")


@login_required
def kb_categories_delete(request, category_id):
    """Delete a KB category."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        category = ArticleCategory.objects.get(pk=category_id)
        category.delete()
    except ArticleCategory.DoesNotExist:
        pass

    return redirect("escalated:admin_kb_categories_index")


# ---------------------------------------------------------------------------
# Skills CRUD
# ---------------------------------------------------------------------------


@login_required
def skills_index(request):
    check = _require_admin(request)
    if check:
        return check
    skills = Skill.objects.annotate(agents_count=Count("agents")).order_by("name")
    return render(request, "Escalated/Admin/Skills/Index", props={"skills": SkillSerializer.serialize_list(skills)})


@login_required
def skills_create(request):
    check = _require_admin(request)
    if check:
        return check
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            return render(request, "Escalated/Admin/Skills/Form", props={"errors": {"name": _("Name is required.")}})
        Skill.objects.create(name=name)
        return redirect("escalated:admin_skills_index")
    return render(request, "Escalated/Admin/Skills/Form", props={})


@login_required
def skills_edit(request, skill_id):
    check = _require_admin(request)
    if check:
        return check
    try:
        skill = Skill.objects.get(pk=skill_id)
    except Skill.DoesNotExist:
        return HttpResponseNotFound(_("Skill not found"))
    if request.method == "POST":
        skill.name = request.POST.get("name", skill.name)
        skill.save()
        return redirect("escalated:admin_skills_index")
    return render(request, "Escalated/Admin/Skills/Form", props={"skill": SkillSerializer.serialize(skill)})


@login_required
def skills_delete(request, skill_id):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))
    try:
        Skill.objects.get(pk=skill_id).delete()
    except Skill.DoesNotExist:
        pass
    return redirect("escalated:admin_skills_index")


# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------


@login_required
def capacity_index(request):
    check = _require_admin(request)
    if check:
        return check
    capacities = AgentCapacity.objects.select_related("user").order_by("user_id")
    return render(request, "Escalated/Admin/Capacity/Index", props={"capacities": AgentCapacitySerializer.serialize_list(capacities)})


@login_required
def capacity_update(request, capacity_id):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))
    try:
        capacity = AgentCapacity.objects.get(pk=capacity_id)
    except AgentCapacity.DoesNotExist:
        return HttpResponseNotFound(_("Capacity not found"))
    max_concurrent = request.POST.get("max_concurrent")
    if max_concurrent:
        capacity.max_concurrent = int(max_concurrent)
        capacity.save(update_fields=["max_concurrent", "updated_at"])
    return redirect("escalated:admin_capacity_index")


# ---------------------------------------------------------------------------
# Webhooks CRUD
# ---------------------------------------------------------------------------


@login_required
def webhooks_index(request):
    check = _require_admin(request)
    if check:
        return check
    webhooks = Webhook.objects.annotate(deliveries_count=Count("deliveries")).order_by("-created_at")
    return render(request, "Escalated/Admin/Webhooks/Index", props={
        "webhooks": WebhookSerializer.serialize_list(webhooks),
        "available_events": WebhookSerializer.AVAILABLE_EVENTS,
    })


@login_required
def webhooks_create(request):
    check = _require_admin(request)
    if check:
        return check
    if request.method == "POST":
        url = request.POST.get("url", "").strip()
        if not url:
            return render(request, "Escalated/Admin/Webhooks/Form", props={
                "errors": {"url": _("URL is required.")},
                "available_events": WebhookSerializer.AVAILABLE_EVENTS,
            })
        try:
            events = json.loads(request.POST.get("events", "[]"))
        except (json.JSONDecodeError, TypeError):
            events = []
        Webhook.objects.create(
            url=url,
            events=events,
            secret=request.POST.get("secret", "") or None,
            active=request.POST.get("active", "true") == "true",
        )
        return redirect("escalated:admin_webhooks_index")
    return render(request, "Escalated/Admin/Webhooks/Form", props={"available_events": WebhookSerializer.AVAILABLE_EVENTS})


@login_required
def webhooks_edit(request, webhook_id):
    check = _require_admin(request)
    if check:
        return check
    try:
        webhook = Webhook.objects.get(pk=webhook_id)
    except Webhook.DoesNotExist:
        return HttpResponseNotFound(_("Webhook not found"))
    if request.method == "POST":
        webhook.url = request.POST.get("url", webhook.url)
        try:
            webhook.events = json.loads(request.POST.get("events", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass
        secret = request.POST.get("secret")
        if secret is not None:
            webhook.secret = secret or None
        webhook.active = request.POST.get("active", "true") == "true"
        webhook.save()
        return redirect("escalated:admin_webhooks_index")
    return render(request, "Escalated/Admin/Webhooks/Form", props={
        "webhook": WebhookSerializer.serialize(webhook),
        "available_events": WebhookSerializer.AVAILABLE_EVENTS,
    })


@login_required
def webhooks_delete(request, webhook_id):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))
    try:
        Webhook.objects.get(pk=webhook_id).delete()
    except Webhook.DoesNotExist:
        pass
    return redirect("escalated:admin_webhooks_index")


@login_required
def webhooks_deliveries(request, webhook_id):
    check = _require_admin(request)
    if check:
        return check
    try:
        webhook = Webhook.objects.get(pk=webhook_id)
    except Webhook.DoesNotExist:
        return HttpResponseNotFound(_("Webhook not found"))
    deliveries = webhook.deliveries.order_by("-created_at")
    paginator = Paginator(deliveries, 25)
    page = paginator.get_page(request.GET.get("page", 1))
    return render(request, "Escalated/Admin/Webhooks/Deliveries", props={
        "webhook": WebhookSerializer.serialize(webhook),
        "deliveries": WebhookDeliverySerializer.serialize_list(page.object_list),
        "pagination": {
            "current_page": page.number,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
        },
    })


@login_required
def webhooks_retry(request, delivery_id):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        delivery = WebhookDelivery.objects.get(pk=delivery_id)
    except WebhookDelivery.DoesNotExist:
        return JsonResponse({"error": "Delivery not found"}, status=404)
    from escalated.services.webhook_dispatcher import WebhookDispatcher
    dispatcher = WebhookDispatcher()
    dispatcher.retry_delivery(delivery)
    return JsonResponse({"success": True})


# ---------------------------------------------------------------------------
# Automations CRUD
# ---------------------------------------------------------------------------


@login_required
def automations_index(request):
    check = _require_admin(request)
    if check:
        return check
    automations = Automation.objects.order_by("position")
    return render(request, "Escalated/Admin/Automations/Index", props={"automations": AutomationSerializer.serialize_list(automations)})


@login_required
def automations_create(request):
    check = _require_admin(request)
    if check:
        return check
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            return render(request, "Escalated/Admin/Automations/Form", props={"errors": {"name": _("Name is required.")}})
        try:
            conditions = json.loads(request.POST.get("conditions", "[]"))
        except (json.JSONDecodeError, TypeError):
            conditions = []
        try:
            actions = json.loads(request.POST.get("actions", "[]"))
        except (json.JSONDecodeError, TypeError):
            actions = []
        max_pos = Automation.objects.aggregate(max_pos=Max("position"))["max_pos"] or 0
        Automation.objects.create(
            name=name,
            conditions=conditions,
            actions=actions,
            active=request.POST.get("active", "true") == "true",
            position=max_pos + 1,
        )
        return redirect("escalated:admin_automations_index")
    return render(request, "Escalated/Admin/Automations/Form", props={})


@login_required
def automations_edit(request, automation_id):
    check = _require_admin(request)
    if check:
        return check
    try:
        automation = Automation.objects.get(pk=automation_id)
    except Automation.DoesNotExist:
        return HttpResponseNotFound(_("Automation not found"))
    if request.method == "POST":
        automation.name = request.POST.get("name", automation.name)
        try:
            automation.conditions = json.loads(request.POST.get("conditions", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            automation.actions = json.loads(request.POST.get("actions", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass
        automation.active = request.POST.get("active", "true") == "true"
        automation.save()
        return redirect("escalated:admin_automations_index")
    return render(request, "Escalated/Admin/Automations/Form", props={"automation": AutomationSerializer.serialize(automation)})


@login_required
def automations_delete(request, automation_id):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))
    try:
        Automation.objects.get(pk=automation_id).delete()
    except Automation.DoesNotExist:
        pass
    return redirect("escalated:admin_automations_index")


# ---------------------------------------------------------------------------
# Settings - CSAT, SSO, Two-Factor
# ---------------------------------------------------------------------------


@login_required
def settings_csat(request):
    check = _require_admin(request)
    if check:
        return check
    from escalated.models import EscalatedSetting
    defaults = {
        "csat_question_text": "How would you rate your support experience?",
        "csat_scale": "1-5",
        "csat_delivery_trigger": "on_resolve",
        "csat_delay_hours": "0",
    }
    if request.method == "POST":
        for key in defaults:
            EscalatedSetting.objects.update_or_create(key=key, defaults={"value": request.POST.get(key, defaults[key])})
        return redirect("escalated:admin_settings")
    config = {}
    for key, default in defaults.items():
        try:
            config[key] = EscalatedSetting.objects.get(key=key).value
        except EscalatedSetting.DoesNotExist:
            config[key] = default
    return render(request, "Escalated/Admin/Settings/Csat", props={"config": config})


@login_required
def settings_sso(request):
    check = _require_admin(request)
    if check:
        return check
    from escalated.services.sso_service import SsoService
    sso = SsoService()
    if request.method == "POST":
        sso.save_config(request.POST.dict())
        return redirect("escalated:admin_settings")
    return render(request, "Escalated/Admin/Settings/Sso", props={"config": sso.get_config()})


@login_required
def settings_two_factor(request):
    check = _require_admin(request)
    if check:
        return check
    two_factor = TwoFactor.objects.filter(user=request.user).first()
    return render(request, "Escalated/Admin/Settings/TwoFactor", props={
        "enabled": two_factor.is_confirmed() if two_factor else False,
        "pending": two_factor is not None and not two_factor.is_confirmed() if two_factor else False,
    })


@login_required
def two_factor_setup(request):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))
    from escalated.services.two_factor_service import TwoFactorService
    service = TwoFactorService()
    TwoFactor.objects.filter(user=request.user, confirmed_at__isnull=True).delete()
    secret = service.generate_secret()
    recovery_codes = service.generate_recovery_codes()
    TwoFactor.objects.create(user=request.user, secret=secret, recovery_codes=recovery_codes)
    qr_uri = service.generate_qr_uri(secret, request.user.email)
    return JsonResponse({"qr_uri": qr_uri, "recovery_codes": recovery_codes})


@login_required
def two_factor_confirm(request):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    code = body.get("code", "").strip()
    if not code or len(code) != 6:
        return JsonResponse({"error": "Code must be 6 digits"}, status=400)
    two_factor = TwoFactor.objects.filter(user=request.user, confirmed_at__isnull=True).first()
    if not two_factor:
        return JsonResponse({"error": "No pending 2FA setup"}, status=400)
    from escalated.services.two_factor_service import TwoFactorService
    service = TwoFactorService()
    if not service.verify(two_factor.secret, code):
        return JsonResponse({"error": "Invalid code"}, status=400)
    from django.utils import timezone as tz
    two_factor.confirmed_at = tz.now()
    two_factor.save(update_fields=["confirmed_at", "updated_at"])
    return JsonResponse({"success": True})


@login_required
def two_factor_disable(request):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))
    TwoFactor.objects.filter(user=request.user).delete()
    return JsonResponse({"success": True})


# ---------------------------------------------------------------------------
# Custom Objects CRUD
# ---------------------------------------------------------------------------


@login_required
def custom_objects_index(request):
    check = _require_admin(request)
    if check:
        return check
    objects = CustomObject.objects.annotate(records_count=Count("records")).order_by("name")
    return render(request, "Escalated/Admin/CustomObjects/Index", props={"custom_objects": CustomObjectSerializer.serialize_list(objects)})


@login_required
def custom_objects_create(request):
    check = _require_admin(request)
    if check:
        return check
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            return render(request, "Escalated/Admin/CustomObjects/Form", props={"errors": {"name": _("Name is required.")}})
        slug_val = slugify(request.POST.get("slug", "") or name)
        try:
            fields_schema = json.loads(request.POST.get("fields_schema", "[]"))
        except (json.JSONDecodeError, TypeError):
            fields_schema = []
        CustomObject.objects.create(name=name, slug=slug_val, fields_schema=fields_schema)
        return redirect("escalated:admin_custom_objects_index")
    return render(request, "Escalated/Admin/CustomObjects/Form", props={})


@login_required
def custom_objects_edit(request, object_id):
    check = _require_admin(request)
    if check:
        return check
    try:
        obj = CustomObject.objects.get(pk=object_id)
    except CustomObject.DoesNotExist:
        return HttpResponseNotFound(_("Custom object not found"))
    if request.method == "POST":
        obj.name = request.POST.get("name", obj.name)
        obj.slug = slugify(request.POST.get("slug", "") or obj.name)
        try:
            obj.fields_schema = json.loads(request.POST.get("fields_schema", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass
        obj.save()
        return redirect("escalated:admin_custom_objects_index")
    return render(request, "Escalated/Admin/CustomObjects/Form", props={"custom_object": CustomObjectSerializer.serialize(obj)})


@login_required
def custom_objects_delete(request, object_id):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))
    try:
        CustomObject.objects.get(pk=object_id).delete()
    except CustomObject.DoesNotExist:
        pass
    return redirect("escalated:admin_custom_objects_index")


@login_required
def custom_object_records(request, object_id):
    check = _require_admin(request)
    if check:
        return check
    try:
        obj = CustomObject.objects.get(pk=object_id)
    except CustomObject.DoesNotExist:
        return HttpResponseNotFound(_("Custom object not found"))
    records = obj.records.order_by("-created_at")
    paginator = Paginator(records, 25)
    page = paginator.get_page(request.GET.get("page", 1))
    return render(request, "Escalated/Admin/CustomObjects/Records", props={
        "custom_object": CustomObjectSerializer.serialize(obj),
        "records": CustomObjectRecordSerializer.serialize_list(page.object_list),
        "pagination": {
            "current_page": page.number,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
        },
    })


@login_required
def custom_object_records_store(request, object_id):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        obj = CustomObject.objects.get(pk=object_id)
    except CustomObject.DoesNotExist:
        return JsonResponse({"error": "Custom object not found"}, status=404)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    record = CustomObjectRecord.objects.create(object=obj, data=body.get("data", {}))
    return JsonResponse({"record": CustomObjectRecordSerializer.serialize(record)})


@login_required
def custom_object_records_update(request, object_id, record_id):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        record = CustomObjectRecord.objects.get(pk=record_id, object_id=object_id)
    except CustomObjectRecord.DoesNotExist:
        return JsonResponse({"error": "Record not found"}, status=404)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    record.data = body.get("data", record.data)
    record.save()
    return JsonResponse({"record": CustomObjectRecordSerializer.serialize(record)})


@login_required
def custom_object_records_delete(request, object_id, record_id):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        record = CustomObjectRecord.objects.get(pk=record_id, object_id=object_id)
        record.delete()
    except CustomObjectRecord.DoesNotExist:
        return JsonResponse({"error": "Record not found"}, status=404)
    return JsonResponse({"success": True})


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@login_required
def reports_dashboard(request):
    check = _require_admin(request)
    if check:
        return check
    from escalated.services.reporting_service import ReportingService
    from datetime import timedelta
    from django.utils import timezone as tz
    service = ReportingService()
    end = tz.now()
    start = end - timedelta(days=30)
    return render(request, "Escalated/Admin/Reports/Dashboard", props={
        "ticket_volume": service.get_ticket_volume_by_date(start, end),
        "by_status": service.get_tickets_by_status(),
        "by_priority": service.get_tickets_by_priority(),
        "avg_response_hours": service.get_average_response_time(start, end),
        "avg_resolution_hours": service.get_average_resolution_time(start, end),
        "agent_performance": service.get_agent_performance(start, end),
    })
