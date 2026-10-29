import json
import re as re_module

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import HttpResponseForbidden, HttpResponseNotAllowed, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _

from escalated.event_names import canonical_events
from escalated.kb_guards import require_kb_enabled
from escalated.models import (
    AgentCapacity,
    AgentSkill,
    Article,
    ArticleCategory,
    AuditLog,
    Automation,
    BusinessSchedule,
    CannedResponse,
    CustomField,
    CustomObject,
    CustomObjectRecord,
    Department,
    EscalatedSetting,
    EscalationRule,
    Holiday,
    Macro,
    Permission,
    Reply,
    Role,
    SatisfactionRating,
    SideConversation,
    SideConversationReply,
    Skill,
    SlaPolicy,
    Tag,
    Ticket,
    TicketLink,
    TicketStatus,
    TwoFactor,
    Webhook,
    WebhookDelivery,
)
from escalated.permissions import is_admin, is_agent
from escalated.rendering import paginated, render_page
from escalated.request_data import is_json, request_data
from escalated.serializers import (
    ActivitySerializer,
    AgentCapacitySerializer,
    ArticleCategorySerializer,
    ArticleSerializer,
    AttachmentSerializer,
    AuditLogSerializer,
    AutomationSerializer,
    BusinessScheduleSerializer,
    CannedResponseSerializer,
    CustomFieldSerializer,
    CustomObjectRecordSerializer,
    CustomObjectSerializer,
    DepartmentSerializer,
    EscalatedSettingSerializer,
    EscalationRuleSerializer,
    MacroSerializer,
    PermissionSerializer,
    ReplySerializer,
    RoleSerializer,
    SatisfactionRatingSerializer,
    SideConversationReplySerializer,
    SideConversationSerializer,
    SkillSerializer,
    SlaPolicySerializer,
    TagSerializer,
    TicketLinkSerializer,
    TicketSerializer,
    TicketStatusSerializer,
    WebhookDeliverySerializer,
    WebhookSerializer,
    ticket_detail,
)
from escalated.services.ticket_service import TicketService
from escalated.support import secret_mask
from escalated.user_keys import user_pk
from escalated.widget_embed import WidgetOrigins

User = get_user_model()


def _require_admin(request):
    """Return an error response if user is not admin, else None."""
    if not request.user.is_authenticated:
        return redirect("login")
    if not is_admin(request.user):
        return HttpResponseForbidden(_("Admin access required."))
    return None


# Inbound email secrets the Settings page edits; it sees them only as a mask.
_SENSITIVE_SETTING_KEYS = {
    "mailgun_signing_key",
    "postmark_inbound_token",
    "imap_password",
}

# SSO secrets the SSO page edits; it sees them only as a mask.
_SSO_SECRET_KEYS = ("sso_jwt_secret", "sso_oauth_client_secret")


# ---------------------------------------------------------------------------
# Reports / Analytics
# ---------------------------------------------------------------------------


@login_required
def reports(request):
    """Admin reports overview (``Admin/Reports``), with Laravel's props."""
    check = _require_admin(request)
    if check:
        return check

    from escalated.services import report_pages
    from escalated.views.advanced_reports import _days

    return render_page(request, "Escalated/Admin/Reports", props=report_pages.overview(_days(request)))


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

    tickets = Ticket.objects.select_related("assigned_to", "department").prefetch_related("tags")
    from escalated.ticket_access import filter_accounts

    tickets = filter_accounts(tickets, request.GET)

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
        "created_at",
        "-created_at",
        "priority",
        "-priority",
        "updated_at",
        "-updated_at",
    ]
    if sort in allowed_sorts:
        tickets = tickets.order_by(sort)

    paginator = Paginator(tickets, 25)
    page = paginator.get_page(request.GET.get("page", 1))

    return render_page(
        request,
        "Escalated/Admin/Tickets/Index",
        props={
            "tickets": paginated(request, page, TicketSerializer.serialize_list(page.object_list)),
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
            "departments": DepartmentSerializer.serialize_list(Department.objects.filter(is_active=True)),
            "tags": TagSerializer.serialize_list(Tag.objects.all()),
            "agents": _get_agents(),
        },
    )


@login_required
def tickets_show(request, ticket_id):
    """Show a ticket with all details for admin."""
    check = _require_admin(request)
    if check:
        return check

    try:
        ticket = (
            Ticket.objects.select_related("assigned_to", "department", "sla_policy")
            .prefetch_related(
                "tags",
                "replies__author",
                "replies__attachments",
                "activities",
                "attachments",
            )
            .get(pk=ticket_id)
        )
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    replies = ticket.replies.filter(is_deleted=False).select_related("author")
    activities = ticket.activities.all()[:50]

    canned_responses = CannedResponse.objects.filter(Q(is_shared=True) | Q(created_by=request.user))

    # Macros available to this user (shared + own)
    macros = Macro.objects.filter(Q(is_shared=True) | Q(created_by=request.user)).order_by("order")

    # Pinned notes
    pinned_notes = ticket.replies.filter(is_deleted=False, is_internal_note=True, is_pinned=True).select_related(
        "author"
    )

    # Satisfaction rating
    try:
        satisfaction_rating = ticket.satisfaction_rating
        satisfaction_data = SatisfactionRatingSerializer.serialize(satisfaction_rating)
    except SatisfactionRating.DoesNotExist:
        satisfaction_data = None

    return render_page(
        request,
        "Escalated/Admin/Tickets/Show",
        props={
            "ticket": ticket_detail(ticket, pinned_notes, satisfaction_data),
            "replies": ReplySerializer.serialize_list(replies),
            "activities": [ActivitySerializer.serialize(a) for a in activities],
            "attachments": AttachmentSerializer.serialize_list(ticket.attachments.all()),
            "agents": _get_agents(),
            "departments": DepartmentSerializer.serialize_list(Department.objects.filter(is_active=True)),
            "tags": TagSerializer.serialize_list(Tag.objects.all()),
            # The page declares cannedResponses; canned_responses is kept for host overrides.
            "cannedResponses": CannedResponseSerializer.serialize_list(canned_responses),
            "canned_responses": CannedResponseSerializer.serialize_list(canned_responses),
            "macros": MacroSerializer.serialize_list(macros),
            "statuses": [{"value": s.value, "label": s.label} for s in Ticket.Status],
            "priorities": [{"value": p.value, "label": p.label} for p in Ticket.Priority],
            "is_following": ticket.is_followed_by(request.user.pk),
            "followers_count": ticket.followers_count,
            "pinned_notes": ReplySerializer.serialize_list(pinned_notes),
            "satisfaction_rating": satisfaction_data,
        },
    )


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

    body = request_data(request).get("body", "").strip()
    if not body:
        return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)

    service = TicketService()
    reply = service.reply(ticket, request.user, {"body": body})

    files = request.FILES.getlist("attachments")
    if files:
        from escalated.conf import get_setting
        from escalated.services.attachment_service import AttachmentService

        for f in files[: get_setting("MAX_ATTACHMENTS")]:
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

    body = request_data(request).get("body", "").strip()
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

    agent_id = request_data(request).get("agent_id")
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

    new_status = request_data(request).get("status")
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

    new_priority = request_data(request).get("priority")
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

    add_tags = request_data(request).getlist("add_tags")
    if add_tags:
        service.add_tags(ticket, request.user, [int(t) for t in add_tags])

    remove_tags = request_data(request).getlist("remove_tags")
    if remove_tags:
        service.remove_tags(ticket, request.user, [int(t) for t in remove_tags])

    return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)


@login_required
def tickets_subjects_store(request, ticket_id):
    """Attach a host-app subject to a ticket (admin)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    from escalated.views.ticket_subjects import attach_ticket_subject

    return attach_ticket_subject(request, ticket)


@login_required
def tickets_subjects_destroy(request, ticket_id, subject_id):
    """Detach a ticket subject link (admin)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "DELETE":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    from escalated.views.ticket_subjects import detach_ticket_subject

    return detach_ticket_subject(request, ticket, subject_id)


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

    department_id = request_data(request).get("department_id")
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

    return render_page(
        request,
        "Escalated/Admin/Departments/Index",
        props={
            "departments": DepartmentSerializer.serialize_list(departments),
        },
    )


@login_required
def departments_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        name = request_data(request).get("name", "").strip()
        slug = slugify(request_data(request).get("slug", "") or name)
        description = request_data(request).get("description", "")
        is_active = request_data(request).get("is_active", "true") == "true"

        if not name:
            return render_page(
                request,
                "Escalated/Admin/Departments/Form",
                props={
                    "errors": {"name": _("Name is required.")},
                },
            )

        Department.objects.create(name=name, slug=slug, description=description, is_active=is_active)
        return redirect("escalated:admin_departments_index")

    return render_page(request, "Escalated/Admin/Departments/Form", props={})


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
        department.name = request_data(request).get("name", department.name)
        department.slug = slugify(request_data(request).get("slug", "") or department.name)
        department.description = request_data(request).get("description", department.description)
        department.is_active = request_data(request).get("is_active", "true") == "true"
        department.save()

        # Update agents
        agent_ids = request_data(request).getlist("agent_ids")
        if agent_ids is not None:
            department.agents.set(agent_ids)

        return redirect("escalated:admin_departments_index")

    from django.contrib.auth import get_user_model

    User = get_user_model()

    return render_page(
        request,
        "Escalated/Admin/Departments/Form",
        props={
            "department": DepartmentSerializer.serialize(department),
            "all_agents": [
                {"id": u.pk, "name": u.get_full_name() or u.username, "email": u.email}
                for u in User.objects.filter(is_active=True)
            ],
            "current_agent_ids": list(department.agents.values_list("pk", flat=True)),
        },
    )


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
    return render_page(
        request,
        "Escalated/Admin/SlaPolicies/Index",
        props={
            "policies": SlaPolicySerializer.serialize_list(policies),
        },
    )


@login_required
def sla_policies_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        import json

        from escalated.ticket_access import sla_targets

        targets = sla_targets(request_data(request))

        name = request_data(request).get("name", "").strip()
        if not name:
            return render_page(
                request,
                "Escalated/Admin/SlaPolicies/Form",
                props={
                    "errors": {"name": _("Name is required.")},
                },
            )

        try:
            first_response_hours = json.loads(request_data(request).get("first_response_hours", "{}"))
        except (json.JSONDecodeError, TypeError):
            first_response_hours = {}

        try:
            resolution_hours = json.loads(request_data(request).get("resolution_hours", "{}"))
        except (json.JSONDecodeError, TypeError):
            resolution_hours = {}

        is_default = request_data(request).get("is_default", "false") == "true"

        # If setting as default, unset other defaults
        if is_default:
            SlaPolicy.objects.filter(is_default=True).update(is_default=False)

        SlaPolicy.objects.create(
            **targets,
            name=name,
            description=request_data(request).get("description", ""),
            is_default=is_default,
            first_response_hours=first_response_hours,
            resolution_hours=resolution_hours,
            business_hours_only=request_data(request).get("business_hours_only", "false") == "true",
            is_active=request_data(request).get("is_active", "true") == "true",
        )
        return redirect("escalated:admin_sla_policies_index")

    return render_page(
        request,
        "Escalated/Admin/SlaPolicies/Form",
        props={
            "priorities": [{"value": p.value, "label": p.label} for p in Ticket.Priority],
        },
    )


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

        from escalated.ticket_access import sla_targets

        targets = sla_targets(request_data(request))

        policy.name = request_data(request).get("name", policy.name)
        policy.description = request_data(request).get("description", policy.description)
        policy.business_hours_only = request_data(request).get("business_hours_only", "false") == "true"
        policy.is_active = request_data(request).get("is_active", "true") == "true"

        is_default = request_data(request).get("is_default", "false") == "true"
        if is_default and not policy.is_default:
            SlaPolicy.objects.filter(is_default=True).update(is_default=False)
        policy.is_default = is_default

        try:
            policy.first_response_hours = json.loads(request_data(request).get("first_response_hours", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            policy.resolution_hours = json.loads(request_data(request).get("resolution_hours", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass

        for field, value in targets.items():
            setattr(policy, field, value)
        policy.save()
        return redirect("escalated:admin_sla_policies_index")

    return render_page(
        request,
        "Escalated/Admin/SlaPolicies/Form",
        props={
            "policy": SlaPolicySerializer.serialize(policy),
            "priorities": [{"value": p.value, "label": p.label} for p in Ticket.Priority],
        },
    )


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
    return render_page(
        request,
        "Escalated/Admin/EscalationRules/Index",
        props={
            "rules": EscalationRuleSerializer.serialize_list(rules),
        },
    )


@login_required
def escalation_rules_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        import json

        name = request_data(request).get("name", "").strip()
        if not name:
            return render_page(
                request,
                "Escalated/Admin/EscalationRules/Form",
                props={
                    "errors": {"name": _("Name is required.")},
                    "trigger_types": [{"value": t.value, "label": t.label} for t in EscalationRule.TriggerType],
                },
            )

        try:
            conditions = json.loads(request_data(request).get("conditions", "{}"))
        except (json.JSONDecodeError, TypeError):
            conditions = {}

        try:
            actions = json.loads(request_data(request).get("actions", "{}"))
        except (json.JSONDecodeError, TypeError):
            actions = {}

        EscalationRule.objects.create(
            name=name,
            description=request_data(request).get("description", ""),
            trigger_type=request_data(request).get("trigger_type", EscalationRule.TriggerType.SLA_BREACH),
            conditions=conditions,
            actions=actions,
            order=int(request_data(request).get("order", 0)),
            is_active=request_data(request).get("is_active", "true") == "true",
        )
        return redirect("escalated:admin_escalation_rules_index")

    return render_page(
        request,
        "Escalated/Admin/EscalationRules/Form",
        props={
            "trigger_types": [{"value": t.value, "label": t.label} for t in EscalationRule.TriggerType],
        },
    )


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

        rule.name = request_data(request).get("name", rule.name)
        rule.description = request_data(request).get("description", rule.description)
        rule.trigger_type = request_data(request).get("trigger_type", rule.trigger_type)
        rule.order = int(request_data(request).get("order", rule.order))
        rule.is_active = request_data(request).get("is_active", "true") == "true"

        try:
            rule.conditions = json.loads(request_data(request).get("conditions", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            rule.actions = json.loads(request_data(request).get("actions", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass

        rule.save()
        return redirect("escalated:admin_escalation_rules_index")

    return render_page(
        request,
        "Escalated/Admin/EscalationRules/Form",
        props={
            "rule": EscalationRuleSerializer.serialize(rule),
            "trigger_types": [{"value": t.value, "label": t.label} for t in EscalationRule.TriggerType],
        },
    )


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

    return _tags_page(request)


def _tags_page(request, errors=None):
    """The tags screen, which is also the tag form.

    Tags are created and edited inline on the index, so the frontend has never
    shipped a detail component -- the separate Create and Edit page names this
    module rendered resolved to nothing and came up blank. Inertia reads `errors`
    off the page props into `form.errors`, so a rejected save comes back to the
    same form with the reason attached.
    """
    tags = Tag.objects.annotate(ticket_count=Count("tickets"))
    return render_page(
        request,
        "Escalated/Admin/Tags/Index",
        props={
            "tags": [{**TagSerializer.serialize(t), "ticket_count": t.ticket_count} for t in tags],
            "errors": errors or {},
        },
    )


@login_required
def tags_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        name = request_data(request).get("name", "").strip()
        if not name:
            return _tags_page(request, errors={"name": _("Name is required.")})

        Tag.objects.create(
            name=name,
            slug=slugify(request_data(request).get("slug", "") or name),
            color=request_data(request).get("color", "#6b7280"),
        )
        return redirect("escalated:admin_tags_index")

    return _tags_page(request)


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
        tag.name = request_data(request).get("name", tag.name)
        tag.slug = slugify(request_data(request).get("slug", "") or tag.name)
        tag.color = request_data(request).get("color", tag.color)
        tag.save()
        return redirect("escalated:admin_tags_index")

    return _tags_page(request)


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

    return _canned_responses_page(request)


def _canned_responses_page(request, errors=None):
    """The canned responses screen, which is also the form.

    Created and edited inline on the index; see _tags_page.
    """
    responses = CannedResponse.objects.select_related("created_by")
    return render_page(
        request,
        "Escalated/Admin/CannedResponses/Index",
        props={
            "responses": CannedResponseSerializer.serialize_list(responses),
            "canned_responses": CannedResponseSerializer.serialize_list(responses),
            "errors": errors or {},
        },
    )


@login_required
def canned_responses_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        title = request_data(request).get("title", "").strip()
        if not title:
            return _canned_responses_page(request, errors={"title": _("Title is required.")})

        CannedResponse.objects.create(
            title=title,
            body=request_data(request).get("body", ""),
            category=request_data(request).get("category", ""),
            created_by=request.user,
            is_shared=request_data(request).get("is_shared", "true") == "true",
        )
        return redirect("escalated:admin_canned_responses_index")

    return _canned_responses_page(request)


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
        canned.title = request_data(request).get("title", canned.title)
        canned.body = request_data(request).get("body", canned.body)
        canned.category = request_data(request).get("category", canned.category)
        canned.is_shared = request_data(request).get("is_shared", "true") == "true"
        canned.save()
        return redirect("escalated:admin_canned_responses_index")

    return _canned_responses_page(request)


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

    # The page binds switches and number inputs to these, so send real
    # booleans and integers rather than the stored "1"/"0" text.
    for key, default in _SETTINGS_BOOL_DEFAULTS.items():
        value = settings_dict.get(key)
        settings_dict[key] = default if value is None else value in ("1", "true", "True", "yes")
    for key in _SETTINGS_INT_KEYS:
        try:
            settings_dict[key] = int(settings_dict[key])
        except (KeyError, TypeError, ValueError):
            pass

    # Stored secrets reach the page only as a mask. The SSO secrets live in
    # the same table but belong to the SSO page; this page masks them too.
    for key in (*_SENSITIVE_SETTING_KEYS, *_SSO_SECRET_KEYS):
        if key in settings_dict:
            settings_dict[key] = secret_mask.mask(settings_dict[key])

    return render_page(
        request,
        "Escalated/Admin/Settings",
        props={
            "settings": settings_dict,
            "errors": request.session.pop(SETTINGS_ERRORS_SESSION_KEY, {}),
            "supported_settings": SUPPORTED_SETTINGS,
        },
    )


_SETTINGS_BOOL_DEFAULTS = {
    "guest_tickets_enabled": True,
    "allow_customer_close": True,
    "show_powered_by": True,
    "inbound_email_enabled": False,
    "knowledge_base_enabled": True,
    "knowledge_base_public": True,
    "knowledge_base_feedback_enabled": True,
    "widget_enabled": False,
    "chat_enabled": False,
}
_SETTINGS_INT_KEYS = (
    "auto_close_resolved_after_days",
    "max_attachments_per_reply",
    "max_attachment_size_kb",
    "imap_port",
)


# A rejected settings save redirects back to the settings page, which shows
# these errors once (the same flow as the workflow admin).
SETTINGS_ERRORS_SESSION_KEY = "escalated_settings_errors"


def _clean_widget_allowed_origins(raw):
    """``(value, error)`` for the posted embedding-site list: one origin per line, or an error."""
    entries = WidgetOrigins.split(raw)
    invalid = [entry for entry in entries if WidgetOrigins.normalize_pattern(entry) is None]
    if invalid:
        return None, _(
            "Each site must be an origin such as https://shop.example.com or https://*.example.com, "
            "with no path. Not valid: %(entries)s"
        ) % {"entries": ", ".join(invalid)}
    return "\n".join(entries), None


# Keys settings_update saves. Sent to the page as ``supported_settings`` so the
# shared Settings page only shows controls whose values are kept.
SUPPORTED_SETTINGS = [
    "guest_tickets_enabled",
    "allow_customer_close",
    "auto_close_resolved_after_days",
    "max_attachments_per_reply",
    "max_attachment_size_kb",
    "ticket_reference_prefix",
    "show_powered_by",
    "inbound_email_enabled",
    "inbound_email_adapter",
    "inbound_email_address",
    "mailgun_signing_key",
    "postmark_inbound_token",
    "ses_region",
    "ses_topic_arn",
    "imap_host",
    "imap_port",
    "imap_encryption",
    "imap_username",
    "imap_password",
    "imap_mailbox",
    "knowledge_base_enabled",
    "knowledge_base_public",
    "knowledge_base_feedback_enabled",
    "widget_enabled",
    "widget_color",
    "widget_position",
    "widget_greeting",
    "widget_departments",
    "widget_allowed_origins",
    "chat_enabled",
]

# Checkboxes of the original form-encoded page: an unticked box is absent from
# a form post, so absence means off. A JSON post (the shared Inertia page)
# only changes the keys it sends.
_FORM_CHECKBOX_KEYS = [
    "guest_tickets_enabled",
    "allow_customer_close",
    "inbound_email_enabled",
    "show_powered_by",
]
# Switches saved only when sent, for form and JSON posts alike.
_OPTIONAL_BOOL_KEYS = [
    "knowledge_base_enabled",
    "knowledge_base_public",
    "knowledge_base_feedback_enabled",
    "widget_enabled",
    "chat_enabled",
]
_WIDGET_COLOR_RE = re_module.compile(r"^#[0-9A-Fa-f]{6}$")
_WIDGET_DEPARTMENTS_RE = re_module.compile(r"^[0-9,\s]*$")
_WIDGET_POSITIONS = ("bottom-right", "bottom-left")


def _truthy(value):
    return str(value).strip().lower() in ("1", "true", "on", "yes")


def _clean_widget_settings(data):
    """``(values, errors)`` for the Support Widget fields present in ``data``."""
    values, errors = {}, {}

    origins = data.get("widget_allowed_origins")
    if origins is not None:
        cleaned, error = _clean_widget_allowed_origins(origins)
        if error:
            errors["widget_allowed_origins"] = error
        else:
            values["widget_allowed_origins"] = cleaned

    color = data.get("widget_color")
    if color is not None:
        color = color.strip()
        if _WIDGET_COLOR_RE.match(color):
            values["widget_color"] = color
        else:
            errors["widget_color"] = _("The widget colour must be a hex colour such as #4F46E5.")

    position = data.get("widget_position")
    if position is not None:
        if position in _WIDGET_POSITIONS:
            values["widget_position"] = position
        else:
            errors["widget_position"] = _("The widget position must be bottom-right or bottom-left.")

    greeting = data.get("widget_greeting")
    if greeting is not None:
        greeting = greeting.strip()
        if len(greeting) > 255:
            errors["widget_greeting"] = _("The widget greeting may not be longer than 255 characters.")
        else:
            values["widget_greeting"] = greeting

    departments = data.get("widget_departments")
    if departments is not None:
        if len(departments) > 1000 or not _WIDGET_DEPARTMENTS_RE.match(departments):
            errors["widget_departments"] = _("The widget departments must be department ids separated by commas.")
        else:
            values["widget_departments"] = departments.strip()

    return values, errors


@login_required
def settings_update(request):
    """Update Escalated settings from the Settings page (JSON from Inertia, or a form post)."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    data = request_data(request)
    is_json_post = is_json(request)

    # Validate before saving anything, so a rejected save changes nothing.
    widget_values, errors = _clean_widget_settings(data)
    if errors:
        request.session[SETTINGS_ERRORS_SESSION_KEY] = errors
        return redirect("escalated:admin_settings")

    for key, value in widget_values.items():
        EscalatedSetting.set(key, value)

    for key in _FORM_CHECKBOX_KEYS:
        raw = data.get(key)
        if raw is None and is_json_post:
            continue
        EscalatedSetting.set(key, "1" if raw is not None and _truthy(raw) else "0")

    for key in _OPTIONAL_BOOL_KEYS:
        raw = data.get(key)
        if raw is not None:
            EscalatedSetting.set(key, "1" if _truthy(raw) else "0")

    # Integer settings
    int_keys = [
        "auto_close_resolved_after_days",
        "max_attachments_per_reply",
        "max_attachment_size_kb",
        "imap_port",
    ]
    for key in int_keys:
        raw = data.get(key)
        if raw is not None:
            try:
                value = str(max(0, int(raw)))
                EscalatedSetting.set(key, value)
            except (ValueError, TypeError):
                pass

    # String settings
    prefix = (data.get("ticket_reference_prefix") or "").strip()
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
        raw = data.get(key)
        if raw is not None:
            stripped = raw.strip()
            # Skip saving sensitive fields that still contain masked values
            if key in _SENSITIVE_SETTING_KEYS and secret_mask.is_masked(stripped):
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
        body = request_data(request)

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
                        agent = User.objects.get(pk=user_pk(value))
                        service.assign(ticket, user, agent)
                    except (User.DoesNotExist, ValidationError):
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

    macro_id = request_data(request).get("macro_id")
    if not macro_id:
        return redirect("escalated:admin_tickets_show", ticket_id=ticket_id)

    try:
        macro = Macro.objects.filter(Q(is_shared=True) | Q(created_by=request.user)).get(pk=macro_id)
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

    return _macros_page(request)


def _macros_page(request, errors=None):
    """The macros screen, which is also the macro form.

    Created and edited inline on the index; see _tags_page.
    """
    macros = Macro.objects.select_related("created_by").order_by("order")
    return render_page(
        request,
        "Escalated/Admin/Macros/Index",
        props={
            "macros": MacroSerializer.serialize_list(macros),
            "errors": errors or {},
        },
    )


@login_required
def macros_create(request):
    """Create a new macro."""
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        name = request_data(request).get("name", "").strip()
        if not name:
            return _macros_page(request, errors={"name": _("Name is required.")})

        try:
            actions = json.loads(request_data(request).get("actions", "[]"))
        except (json.JSONDecodeError, TypeError):
            actions = []

        Macro.objects.create(
            name=name,
            description=request_data(request).get("description", ""),
            actions=actions,
            is_shared=request_data(request).get("is_shared", "true") == "true",
            order=int(request_data(request).get("order", 0)),
            created_by=request.user,
        )
        return redirect("escalated:admin_macros_index")

    return _macros_page(request)


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
        macro.name = request_data(request).get("name", macro.name)
        macro.description = request_data(request).get("description", macro.description)
        macro.is_shared = request_data(request).get("is_shared", "true") == "true"
        macro.order = int(request_data(request).get("order", macro.order))

        try:
            macro.actions = json.loads(request_data(request).get("actions", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass

        macro.save()
        return redirect("escalated:admin_macros_index")

    return _macros_page(request)


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

    return render_page(
        request,
        "Escalated/Admin/AuditLog/Index",
        props={
            "logs": paginated(request, page, AuditLogSerializer.serialize_list(page.object_list)),
            "filters": {
                "user_id": user_id,
                "action": action,
                "auditable_type": auditable_type,
                "date_from": date_from,
                "date_to": date_to,
            },
            "users": [
                {"id": u.pk, "name": u.get_full_name() or u.username} for u in User.objects.filter(is_active=True)
            ],
            "actions": ["created", "updated", "deleted"],
            "resource_types": list(AuditLog.objects.values_list("auditable_content_type__model", flat=True).distinct()),
        },
    )


# ---------------------------------------------------------------------------
# Ticket Statuses CRUD
# ---------------------------------------------------------------------------


@login_required
def statuses_index(request):
    check = _require_admin(request)
    if check:
        return check

    statuses = TicketStatus.objects.all()
    return render_page(
        request,
        "Escalated/Admin/Statuses/Index",
        props={
            "statuses": TicketStatusSerializer.serialize_list(statuses),
            "categories": ["new", "open", "pending", "on_hold", "solved"],
        },
    )


@login_required
def statuses_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        label = request_data(request).get("label", "").strip()
        if not label:
            return render_page(
                request,
                "Escalated/Admin/Statuses/Form",
                props={
                    "errors": {"label": _("Label is required.")},
                    "categories": ["new", "open", "pending", "on_hold", "solved"],
                },
            )

        category = request_data(request).get("category", "open")
        is_default = request_data(request).get("is_default", "false") == "true"

        if is_default:
            TicketStatus.objects.filter(category=category).update(is_default=False)

        TicketStatus.objects.create(
            label=label,
            category=category,
            color=request_data(request).get("color", "#6b7280"),
            description=request_data(request).get("description", ""),
            position=int(request_data(request).get("position", 0)),
            is_default=is_default,
        )
        return redirect("escalated:admin_statuses_index")

    return render_page(
        request,
        "Escalated/Admin/Statuses/Form",
        props={
            "categories": ["new", "open", "pending", "on_hold", "solved"],
        },
    )


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
        status.label = request_data(request).get("label", status.label)
        status.category = request_data(request).get("category", status.category)
        status.color = request_data(request).get("color", status.color)
        status.description = request_data(request).get("description", status.description)
        status.position = int(request_data(request).get("position", status.position))

        is_default = request_data(request).get("is_default", "false") == "true"
        if is_default and not status.is_default:
            TicketStatus.objects.filter(category=status.category).exclude(pk=status.pk).update(is_default=False)
        status.is_default = is_default

        status.save()
        return redirect("escalated:admin_statuses_index")

    return render_page(
        request,
        "Escalated/Admin/Statuses/Form",
        props={
            "status": TicketStatusSerializer.serialize(status),
            "categories": ["new", "open", "pending", "on_hold", "solved"],
        },
    )


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
    return render_page(
        request,
        "Escalated/Admin/BusinessHours/Index",
        props={
            "schedules": BusinessScheduleSerializer.serialize_list(schedules),
        },
    )


@login_required
def business_hours_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        name = request_data(request).get("name", "").strip()
        if not name:
            return render_page(
                request,
                "Escalated/Admin/BusinessHours/Form",
                props={
                    "errors": {"name": _("Name is required.")},
                },
            )

        is_default = request_data(request).get("is_default", "false") == "true"
        if is_default:
            BusinessSchedule.objects.filter(is_default=True).update(is_default=False)

        try:
            schedule_data = json.loads(request_data(request).get("schedule", "{}"))
        except (json.JSONDecodeError, TypeError):
            schedule_data = {}

        sched = BusinessSchedule.objects.create(
            name=name,
            timezone=request_data(request).get("timezone", "UTC"),
            is_default=is_default,
            schedule=schedule_data,
        )

        try:
            holidays = json.loads(request_data(request).get("holidays", "[]"))
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

    return render_page(
        request,
        "Escalated/Admin/BusinessHours/Form",
        props={
            "timezones": sorted(available_timezones()),
        },
    )


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
        sched.name = request_data(request).get("name", sched.name)
        sched.timezone = request_data(request).get("timezone", sched.timezone)

        is_default = request_data(request).get("is_default", "false") == "true"
        if is_default and not sched.is_default:
            BusinessSchedule.objects.filter(is_default=True).exclude(pk=sched.pk).update(is_default=False)
        sched.is_default = is_default

        try:
            sched.schedule = json.loads(request_data(request).get("schedule", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass

        sched.save()

        # Sync holidays
        sched.holidays.all().delete()
        try:
            holidays = json.loads(request_data(request).get("holidays", "[]"))
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

    return render_page(
        request,
        "Escalated/Admin/BusinessHours/Form",
        props={
            "schedule": BusinessScheduleSerializer.serialize(sched),
            "timezones": sorted(available_timezones()),
        },
    )


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
    return render_page(
        request,
        "Escalated/Admin/Roles/Index",
        props={
            "roles": RoleSerializer.serialize_list(roles),
        },
    )


@login_required
def roles_create(request):
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        name = request_data(request).get("name", "").strip()
        if not name:
            return render_page(
                request,
                "Escalated/Admin/Roles/Form",
                props={
                    "errors": {"name": _("Name is required.")},
                    "permissions": PermissionSerializer.serialize_grouped(Permission.objects.all()),
                },
            )

        role = Role.objects.create(
            name=name,
            description=request_data(request).get("description", ""),
        )

        permission_ids = request_data(request).getlist("permissions")
        if permission_ids:
            role.permissions.set(permission_ids)

        return redirect("escalated:admin_roles_index")

    return render_page(
        request,
        "Escalated/Admin/Roles/Form",
        props={
            "permissions": PermissionSerializer.serialize_grouped(Permission.objects.all()),
        },
    )


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
        role.name = request_data(request).get("name", role.name)
        role.description = request_data(request).get("description", role.description)
        role.save()

        permission_ids = request_data(request).getlist("permissions")
        role.permissions.set(permission_ids)

        return redirect("escalated:admin_roles_index")

    return render_page(
        request,
        "Escalated/Admin/Roles/Form",
        props={
            "role": RoleSerializer.serialize(role, include_permissions=True),
            "permissions": PermissionSerializer.serialize_grouped(Permission.objects.all()),
        },
    )


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
    return render_page(
        request,
        "Escalated/Admin/CustomFields/Index",
        props={
            "custom_fields": CustomFieldSerializer.serialize_list(fields),
        },
    )


@login_required
def custom_fields_create(request):
    """Create a new custom field."""
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        name = request_data(request).get("name", "").strip()
        if not name:
            return render_page(
                request,
                "Escalated/Admin/CustomFields/Form",
                props={
                    "errors": {"name": _("Name is required.")},
                    "contexts": [{"value": c.value, "label": c.label} for c in CustomField.Context],
                },
            )

        try:
            options = json.loads(request_data(request).get("options", "null"))
        except (json.JSONDecodeError, TypeError):
            options = None

        try:
            validation_rules = json.loads(request_data(request).get("validation_rules", "null"))
        except (json.JSONDecodeError, TypeError):
            validation_rules = None

        try:
            conditions = json.loads(request_data(request).get("conditions", "null"))
        except (json.JSONDecodeError, TypeError):
            conditions = None

        CustomField.objects.create(
            name=name,
            slug=slugify(request_data(request).get("slug", "") or name),
            type=request_data(request).get("type", CustomField.FieldType.TEXT),
            context=request_data(request).get("context", CustomField.Context.TICKET),
            options=options,
            required=request_data(request).get("required", "false") == "true",
            placeholder=request_data(request).get("placeholder", ""),
            description=request_data(request).get("description", ""),
            validation_rules=validation_rules,
            conditions=conditions,
            position=int(request_data(request).get("position", 0)),
            active=request_data(request).get("active", "true") == "true",
        )
        return redirect("escalated:admin_custom_fields_index")

    return render_page(
        request,
        "Escalated/Admin/CustomFields/Form",
        props={
            "contexts": [{"value": c.value, "label": c.label} for c in CustomField.Context],
        },
    )


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
        field.name = request_data(request).get("name", field.name)
        field.slug = slugify(request_data(request).get("slug", "") or field.name)
        field.type = request_data(request).get("type", field.type)
        field.context = request_data(request).get("context", field.context)
        field.required = request_data(request).get("required", "false") == "true"
        field.placeholder = request_data(request).get("placeholder", field.placeholder)
        field.description = request_data(request).get("description", field.description)
        field.position = int(request_data(request).get("position", field.position))
        field.active = request_data(request).get("active", "true") == "true"

        try:
            field.options = json.loads(request_data(request).get("options", "null"))
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            field.validation_rules = json.loads(request_data(request).get("validation_rules", "null"))
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            field.conditions = json.loads(request_data(request).get("conditions", "null"))
        except (json.JSONDecodeError, TypeError):
            pass

        field.save()
        return redirect("escalated:admin_custom_fields_index")

    return render_page(
        request,
        "Escalated/Admin/CustomFields/Form",
        props={
            "field": CustomFieldSerializer.serialize(field),
            "contexts": [{"value": c.value, "label": c.label} for c in CustomField.Context],
        },
    )


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
        CustomField.objects.filter(pk=item.get("id")).update(position=item.get("position", 0))

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
        links.append(TicketLinkSerializer.serialize(link, direction="parent"))
    for link in child_links:
        links.append(TicketLinkSerializer.serialize(link, direction="child"))

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
    exists = (
        TicketLink.objects.filter(parent_ticket=ticket, child_ticket=target, link_type=link_type).exists()
        or TicketLink.objects.filter(parent_ticket=target, child_ticket=ticket, link_type=link_type).exists()
    )

    if exists:
        return JsonResponse({"error": "Link already exists"}, status=400)

    link = TicketLink.objects.create(
        parent_ticket=ticket,
        child_ticket=target,
        link_type=link_type,
    )

    return JsonResponse(
        {
            "link": TicketLinkSerializer.serialize(link, direction="parent"),
        }
    )


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
        .filter(Q(reference__icontains=q) | Q(subject__icontains=q))
        .order_by("-created_at")[:10]
    )

    return JsonResponse(
        {
            "tickets": [
                {
                    "id": t.pk,
                    "reference": t.reference,
                    "subject": t.subject,
                    "status": t.status,
                }
                for t in tickets
            ]
        }
    )


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
# Saved Views
# ---------------------------------------------------------------------------


@login_required
def saved_views_index(request):
    """List saved views for the current user (own + shared)."""
    check = _require_admin(request)
    if check:
        return check

    from escalated.models import SavedView

    views = SavedView.objects.filter(Q(user=request.user) | Q(is_shared=True)).order_by("position", "name")

    return JsonResponse(
        {
            "views": [
                {
                    "id": v.pk,
                    "name": v.name,
                    "filters": v.filters,
                    "is_shared": v.is_shared,
                    "is_default": v.is_default,
                    "position": v.position,
                    "icon": v.icon,
                    "color": v.color,
                    "is_own": v.user_id == request.user.pk,
                }
                for v in views
            ]
        }
    )


@login_required
def saved_views_store(request):
    """Create a new saved view."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = body.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "name is required"}, status=400)

    from escalated.models import SavedView

    view = SavedView.objects.create(
        name=name,
        filters=body.get("filters", {}),
        user=request.user,
        is_shared=body.get("is_shared", False),
        is_default=body.get("is_default", False),
        position=body.get("position", 0),
        icon=body.get("icon", ""),
        color=body.get("color", "#6b7280"),
    )

    return JsonResponse(
        {
            "success": True,
            "view": {
                "id": view.pk,
                "name": view.name,
            },
        }
    )


@login_required
def saved_views_update(request, view_id):
    """Update an existing saved view."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    from escalated.models import SavedView

    try:
        view = SavedView.objects.get(pk=view_id)
    except SavedView.DoesNotExist:
        return HttpResponseNotFound(_("Saved view not found"))

    # Only owner or admin can update
    if view.user_id != request.user.pk and not request.user.is_superuser:
        return HttpResponseForbidden(_("Cannot update this view"))

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if "name" in body:
        view.name = body["name"]
    if "filters" in body:
        view.filters = body["filters"]
    if "is_shared" in body:
        view.is_shared = body["is_shared"]
    if "is_default" in body:
        view.is_default = body["is_default"]
    if "position" in body:
        view.position = body["position"]
    if "icon" in body:
        view.icon = body["icon"]
    if "color" in body:
        view.color = body["color"]

    view.save()

    return JsonResponse({"success": True})


@login_required
def saved_views_delete(request, view_id):
    """Delete a saved view."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    from escalated.models import SavedView

    try:
        view = SavedView.objects.get(pk=view_id)
    except SavedView.DoesNotExist:
        return HttpResponseNotFound(_("Saved view not found"))

    if view.user_id != request.user.pk and not request.user.is_superuser:
        return HttpResponseForbidden(_("Cannot delete this view"))

    view.delete()

    return JsonResponse({"success": True})


@login_required
def saved_views_reorder(request):
    """Reorder saved views."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    order = body.get("order", [])
    if not isinstance(order, list):
        return JsonResponse({"error": "order must be a list of view IDs"}, status=400)

    from escalated.models import SavedView

    for position, view_id in enumerate(order):
        SavedView.objects.filter(
            pk=view_id,
        ).filter(Q(user=request.user) | Q(is_shared=True)).update(position=position)

    return JsonResponse({"success": True})


# ---------------------------------------------------------------------------
# Ticket Snooze / Unsnooze
# ---------------------------------------------------------------------------


@login_required
def ticket_snooze(request, ticket_id):
    """Snooze a ticket until a specified datetime."""
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
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    snoozed_until = body.get("snoozed_until")
    if not snoozed_until:
        return JsonResponse({"error": "snoozed_until is required"}, status=400)

    from django.utils.dateparse import parse_datetime

    dt = parse_datetime(snoozed_until)
    if dt is None:
        return JsonResponse({"error": "Invalid datetime format"}, status=400)

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)

    ticket.snooze(until=dt, user=request.user)

    return JsonResponse({"success": True, "snoozed_until": dt.isoformat()})


@login_required
def ticket_unsnooze(request, ticket_id):
    """Unsnooze a ticket, restoring its previous status."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return HttpResponseNotFound(_("Ticket not found"))

    if not ticket.is_snoozed:
        return JsonResponse({"error": "Ticket is not snoozed"}, status=400)

    ticket.unsnooze()

    return JsonResponse({"success": True, "status": ticket.status})


# ---------------------------------------------------------------------------
# Ticket Splitting
# ---------------------------------------------------------------------------


@login_required
def ticket_split(request, ticket_id):
    """Split a reply from a ticket into a new ticket."""
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

    reply_id = body.get("reply_id")
    if not reply_id:
        return JsonResponse({"error": "reply_id is required"}, status=400)

    try:
        reply = Reply.objects.get(pk=reply_id, ticket=source)
    except Reply.DoesNotExist:
        return JsonResponse({"error": "Reply not found on this ticket"}, status=404)

    data = {
        "subject": body.get("subject"),
        "priority": body.get("priority"),
        "department_id": body.get("department_id"),
        "assigned_to_id": body.get("assigned_to_id"),
    }

    from escalated.services.ticket_split_service import TicketSplitService

    service = TicketSplitService()
    new_ticket = service.split_ticket(source, reply, data, split_by_user_id=request.user.pk)

    return JsonResponse(
        {
            "success": True,
            "new_ticket": {
                "id": new_ticket.pk,
                "reference": new_ticket.reference,
                "subject": new_ticket.subject,
            },
        }
    )


# ---------------------------------------------------------------------------
# Side Conversations
# ---------------------------------------------------------------------------


@login_required
def side_conversations_index(request, ticket_id):
    """List all side conversations for a ticket with reply counts."""
    check = _require_admin(request)
    if check:
        return check

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return JsonResponse({"error": "Ticket not found"}, status=404)

    conversations = (
        ticket.side_conversations.select_related("created_by")
        .prefetch_related("replies__author")
        .annotate(reply_count=Count("replies"))
        .order_by("-created_at")
    )

    return JsonResponse(
        {
            "side_conversations": SideConversationSerializer.serialize_list(conversations),
        }
    )


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
        SideConversation.objects.select_related("created_by")
        .prefetch_related("replies__author")
        .get(pk=conversation.pk)
    )

    return JsonResponse(
        {
            "side_conversation": SideConversationSerializer.serialize(conversation),
        }
    )


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
        conversation = SideConversation.objects.get(pk=conversation_id, ticket=ticket)
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

    return JsonResponse(
        {
            "reply": SideConversationReplySerializer.serialize(reply),
        }
    )


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
        conversation = SideConversation.objects.get(pk=conversation_id, ticket=ticket)
    except SideConversation.DoesNotExist:
        return JsonResponse({"error": "Side conversation not found"}, status=404)

    conversation.status = "closed"
    conversation.save(update_fields=["status", "updated_at"])

    return JsonResponse({"success": True})


# ---------------------------------------------------------------------------
# Knowledge Base - Articles CRUD
# ---------------------------------------------------------------------------


@require_kb_enabled
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

    return render_page(
        request,
        "Escalated/Admin/KnowledgeBase/Articles/Index",
        props={
            "articles": paginated(request, page, ArticleSerializer.serialize_list(page.object_list)),
            "filters": {
                "search": search,
                "status": status_filter,
                "category": category_filter,
            },
            "categories": ArticleCategorySerializer.serialize_list(ArticleCategory.objects.ordered()),
        },
    )


@require_kb_enabled
@login_required
def articles_create(request):
    """Create a new KB article."""
    check = _require_admin(request)
    if check:
        return check

    if request.method == "POST":
        title = request_data(request).get("title", "").strip()
        if not title:
            return render_page(
                request,
                "Escalated/Admin/KnowledgeBase/Articles/Form",
                props={
                    "errors": {"title": _("Title is required.")},
                    "categories": ArticleCategorySerializer.serialize_list(ArticleCategory.objects.ordered()),
                },
            )

        status = request_data(request).get("status", Article.Status.DRAFT)
        published_at = None
        if status == Article.Status.PUBLISHED:
            published_at = timezone.now()

        category_id = request_data(request).get("category_id")

        Article.objects.create(
            title=title,
            slug=slugify(request_data(request).get("slug", "") or title),
            body=request_data(request).get("body", ""),
            status=status,
            category_id=category_id if category_id else None,
            author=request.user,
            published_at=published_at,
        )
        return redirect("escalated:admin_articles_index")

    return render_page(
        request,
        "Escalated/Admin/KnowledgeBase/Articles/Form",
        props={
            "categories": ArticleCategorySerializer.serialize_list(ArticleCategory.objects.ordered()),
        },
    )


@require_kb_enabled
@login_required
def articles_edit(request, article_id):
    """Edit a KB article."""
    check = _require_admin(request)
    if check:
        return check

    try:
        article = Article.objects.select_related("category", "author").get(pk=article_id)
    except Article.DoesNotExist:
        return HttpResponseNotFound(_("Article not found"))

    if request.method == "POST":
        article.title = request_data(request).get("title", article.title)
        article.slug = slugify(request_data(request).get("slug", "") or article.title)
        article.body = request_data(request).get("body", article.body)

        new_status = request_data(request).get("status", article.status)
        if new_status == Article.Status.PUBLISHED and article.status != Article.Status.PUBLISHED:
            article.published_at = timezone.now()
        article.status = new_status

        category_id = request_data(request).get("category_id")
        article.category_id = category_id if category_id else None

        article.save()
        return redirect("escalated:admin_articles_index")

    return render_page(
        request,
        "Escalated/Admin/KnowledgeBase/Articles/Form",
        props={
            "article": ArticleSerializer.serialize(article),
            "categories": ArticleCategorySerializer.serialize_list(ArticleCategory.objects.ordered()),
        },
    )


@require_kb_enabled
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


@require_kb_enabled
@login_required
def kb_categories_index(request):
    """List all KB categories with article counts."""
    check = _require_admin(request)
    if check:
        return check

    categories = ArticleCategory.objects.annotate(articles_count=Count("articles")).order_by("position", "name")

    return render_page(
        request,
        "Escalated/Admin/KnowledgeBase/Categories/Index",
        props={
            "categories": ArticleCategorySerializer.serialize_list(categories),
        },
    )


@require_kb_enabled
@login_required
def kb_categories_store(request):
    """Create a new KB category."""
    check = _require_admin(request)
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden(_("Method not allowed"))

    name = request_data(request).get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Name is required"}, status=400)

    parent_id = request_data(request).get("parent_id")

    ArticleCategory.objects.create(
        name=name,
        slug=slugify(name),
        parent_id=parent_id if parent_id else None,
        position=int(request_data(request).get("position", 0)),
        description=request_data(request).get("description", ""),
    )

    return redirect("escalated:admin_kb_categories_index")


@require_kb_enabled
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

    category.name = request_data(request).get("name", category.name)
    category.slug = slugify(request_data(request).get("slug", "") or category.name)
    category.description = request_data(request).get("description", category.description)
    category.position = int(request_data(request).get("position", category.position))

    parent_id = request_data(request).get("parent_id")
    category.parent_id = parent_id if parent_id else None

    category.save()

    return redirect("escalated:admin_kb_categories_index")


@require_kb_enabled
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


def _skill_form_user_filter_q():
    """ORM Q for users with is_agent or is_admin when those fields exist on the user model."""
    field_names = {f.name for f in User._meta.get_fields()}
    parts = []
    if "is_agent" in field_names:
        parts.append(Q(is_agent=True))
    if "is_admin" in field_names:
        parts.append(Q(is_admin=True))
    if not parts:
        return None
    combined = parts[0]
    for p in parts[1:]:
        combined |= p
    return combined


def _skills_eligible_user_queryset():
    """Users shown in the skill form agent picker (is_agent or is_admin when present)."""
    qs = User.objects.filter(is_active=True)
    q_or = _skill_form_user_filter_q()
    if q_or is not None:
        qs = qs.filter(q_or)
    return qs.order_by("first_name", "last_name", "username")


def _skills_serialize_available_agents(qs):
    return [{"id": u.pk, "name": u.get_full_name() or u.username, "email": getattr(u, "email", "") or ""} for u in qs]


def _skills_form_shared_props():
    return {
        "availableAgents": _skills_serialize_available_agents(_skills_eligible_user_queryset()),
        "availableTags": TagSerializer.serialize_list(Tag.objects.order_by("name")),
        "availableDepartments": [
            {"id": d.pk, "name": d.name} for d in Department.objects.filter(is_active=True).order_by("name")
        ],
    }


def _normalize_skills_payload_dict(payload):
    name = (payload.get("name") or "").strip()
    description = payload.get("description")
    if description is not None and str(description).strip() != "":
        description = str(description).strip()
    else:
        description = None

    def collect_int_ids(key):
        out = []
        val = payload.get(key)
        if val is None:
            return out
        if isinstance(val, (list, tuple)):
            for item in val:
                try:
                    if item is None or item == "":
                        continue
                    out.append(int(item))
                except (TypeError, ValueError):
                    continue
        else:
            try:
                if val == "":
                    return out
                out.append(int(val))
            except (TypeError, ValueError):
                pass
        return list(dict.fromkeys(out))

    routing_tag_ids = collect_int_ids("routing_tag_ids")
    routing_department_ids = collect_int_ids("routing_department_ids")

    agents_out = []
    for row in payload.get("agents") or []:
        if not isinstance(row, dict):
            continue
        uid = row.get("user_id")
        if uid is None:
            continue
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            continue
        prof = row.get("proficiency", 3)
        try:
            prof = int(prof)
        except (TypeError, ValueError):
            prof = 3
        prof = max(1, min(5, prof))
        agents_out.append({"user_id": uid, "proficiency": prof})

    return {
        "name": name,
        "description": description,
        "routing_tag_ids": routing_tag_ids,
        "routing_department_ids": routing_department_ids,
        "agents": agents_out,
    }


def _skills_parse_agents_bracket_notation(data):
    agents = []
    idx = 0
    while True:
        uid = data.get(f"agents[{idx}][user_id]")
        if uid is None or str(uid).strip() == "":
            break
        prof = data.get(f"agents[{idx}][proficiency]", "3")
        try:
            agents.append({"user_id": int(uid), "proficiency": int(prof)})
        except (TypeError, ValueError):
            break
        idx += 1
    return agents


def _skills_post_to_payload_dict(data):
    """Build a normalised payload dict from a QueryDict (Inertia form posts)."""
    name = (data.get("name") or "").strip()
    description = data.get("description")
    if description is not None:
        description = str(description).strip() or None

    tag_ids = []
    for key in ("routing_tag_ids[]", "routing_tag_ids"):
        tag_ids.extend(data.getlist(key))

    dept_ids = []
    for key in ("routing_department_ids[]", "routing_department_ids"):
        dept_ids.extend(data.getlist(key))

    agents = []
    agents_raw = data.get("agents")
    if agents_raw:
        try:
            parsed = json.loads(agents_raw)
            if isinstance(parsed, list):
                agents = parsed
        except (json.JSONDecodeError, TypeError):
            pass
    if not agents:
        agents = _skills_parse_agents_bracket_notation(data)

    tag_ids_clean = []
    seen = set()
    for x in tag_ids:
        try:
            i = int(x)
            if i not in seen:
                seen.add(i)
                tag_ids_clean.append(i)
        except (TypeError, ValueError):
            continue

    dept_ids_clean = []
    seen_d = set()
    for x in dept_ids:
        try:
            i = int(x)
            if i not in seen_d:
                seen_d.add(i)
                dept_ids_clean.append(i)
        except (TypeError, ValueError):
            continue

    return _normalize_skills_payload_dict(
        {
            "name": name,
            "description": description,
            "routing_tag_ids": tag_ids_clean,
            "routing_department_ids": dept_ids_clean,
            "agents": agents,
        }
    )


def _skills_parse_request(request):
    if request.body:
        try:
            raw = json.loads(request.body)
            if isinstance(raw, dict) and raw:
                return _normalize_skills_payload_dict(raw)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            pass
    return _skills_post_to_payload_dict(request_data(request))


def _skills_apply_payload(skill, payload):
    name = payload["name"]
    if not name:
        raise ValueError("name_required")

    tag_ids = set(Tag.objects.filter(pk__in=payload["routing_tag_ids"]).values_list("pk", flat=True))
    dept_ids = set(Department.objects.filter(pk__in=payload["routing_department_ids"]).values_list("pk", flat=True))
    allowed_users = _skills_eligible_user_queryset().filter(pk__in=[a["user_id"] for a in payload["agents"]])
    valid_user_ids = set(allowed_users.values_list("pk", flat=True))

    with transaction.atomic():
        skill.name = name
        skill.description = payload.get("description")
        skill.save()
        skill.routing_tags.set(sorted(tag_ids))
        skill.routing_departments.set(sorted(dept_ids))
        AgentSkill.objects.filter(skill=skill).delete()
        bulk = []
        seen_user = set()
        for row in payload["agents"]:
            uid = row["user_id"]
            if uid not in valid_user_ids or uid in seen_user:
                continue
            seen_user.add(uid)
            bulk.append(
                AgentSkill(
                    user_id=uid,
                    skill=skill,
                    proficiency=row["proficiency"],
                )
            )
        if bulk:
            AgentSkill.objects.bulk_create(bulk)


def _skills_method_is_update(request):
    if request.method in ("PUT", "PATCH"):
        return True
    if request.method == "POST":
        spoofed = request_data(request).get("_method", "").upper()
        if spoofed in ("PUT", "PATCH", ""):
            return True
    return False


@login_required
def skills_index(request):
    check = _require_admin(request)
    if check:
        return check
    skills = Skill.objects.annotate(
        agents_count=Count("agents", distinct=True),
        routing_tags_count=Count("routing_tags", distinct=True),
        routing_departments_count=Count("routing_departments", distinct=True),
    ).order_by("name")
    return render_page(
        request,
        "Escalated/Admin/Skills/Index",
        props={"skills": SkillSerializer.serialize_index_list(skills)},
    )


@login_required
def skills_create(request):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    props = {"skill": None, **_skills_form_shared_props()}
    return render_page(request, "Escalated/Admin/Skills/Form", props=props)


@login_required
def skills_store(request):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    payload = _skills_parse_request(request)
    if not payload["name"]:
        props = {**_skills_form_shared_props(), "skill": None, "errors": {"name": _("Name is required.")}}
        return render_page(request, "Escalated/Admin/Skills/Form", props=props)
    skill = Skill()
    try:
        _skills_apply_payload(skill, payload)
    except ValueError:
        props = {**_skills_form_shared_props(), "skill": None, "errors": {"name": _("Name is required.")}}
        return render_page(request, "Escalated/Admin/Skills/Form", props=props)
    return redirect("escalated:admin_skills_index")


@login_required
def skills_edit(request, skill_id):
    check = _require_admin(request)
    if check:
        return check
    try:
        skill = Skill.objects.get(pk=skill_id)
    except Skill.DoesNotExist:
        return HttpResponseNotFound(_("Skill not found"))
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    props = {
        "skill": SkillSerializer.serialize_for_form(skill),
        **_skills_form_shared_props(),
    }
    return render_page(request, "Escalated/Admin/Skills/Form", props=props)


@login_required
def skills_update(request, skill_id):
    check = _require_admin(request)
    if check:
        return check
    if not _skills_method_is_update(request):
        return HttpResponseNotAllowed(["PUT", "PATCH", "POST"])
    try:
        skill = Skill.objects.get(pk=skill_id)
    except Skill.DoesNotExist:
        return HttpResponseNotFound(_("Skill not found"))
    payload = _skills_parse_request(request)
    if not payload["name"]:
        props = {
            "skill": SkillSerializer.serialize_for_form(skill),
            **_skills_form_shared_props(),
            "errors": {"name": _("Name is required.")},
        }
        return render_page(request, "Escalated/Admin/Skills/Form", props=props)
    try:
        _skills_apply_payload(skill, payload)
    except ValueError:
        props = {
            "skill": SkillSerializer.serialize_for_form(skill),
            **_skills_form_shared_props(),
            "errors": {"name": _("Name is required.")},
        }
        return render_page(request, "Escalated/Admin/Skills/Form", props=props)
    return redirect("escalated:admin_skills_index")


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


@login_required
def skills_destroy(request, skill_id):
    check = _require_admin(request)
    if check:
        return check
    if request.method != "DELETE":
        return HttpResponseNotAllowed(["DELETE"])
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
    return render_page(
        request,
        "Escalated/Admin/Capacity/Index",
        props={"capacities": AgentCapacitySerializer.serialize_list(capacities)},
    )


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
    max_concurrent = request_data(request).get("max_concurrent")
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
    return render_page(
        request,
        "Escalated/Admin/Webhooks/Index",
        props={
            "webhooks": WebhookSerializer.serialize_list(webhooks),
            "available_events": WebhookSerializer.AVAILABLE_EVENTS,
        },
    )


@login_required
def webhooks_create(request):
    check = _require_admin(request)
    if check:
        return check
    if request.method == "POST":
        url = request_data(request).get("url", "").strip()
        if not url:
            return render_page(
                request,
                "Escalated/Admin/Webhooks/Form",
                props={
                    "errors": {"url": _("URL is required.")},
                    "available_events": WebhookSerializer.AVAILABLE_EVENTS,
                },
            )
        try:
            events = json.loads(request_data(request).get("events", "[]"))
        except (json.JSONDecodeError, TypeError):
            events = []
        Webhook.objects.create(
            url=url,
            events=canonical_events(events),
            secret=request_data(request).get("secret", "") or None,
            active=request_data(request).get("active", "true") == "true",
        )
        return redirect("escalated:admin_webhooks_index")
    return render_page(
        request, "Escalated/Admin/Webhooks/Form", props={"available_events": WebhookSerializer.AVAILABLE_EVENTS}
    )


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
        webhook.url = request_data(request).get("url", webhook.url)
        try:
            webhook.events = canonical_events(json.loads(request_data(request).get("events", "[]")))
        except (json.JSONDecodeError, TypeError):
            pass
        # The form never receives the stored secret, so a blank or missing one
        # means "leave it as it is". ``clear_secret`` removes it.
        secret = request_data(request).get("secret")
        if _truthy(request_data(request).get("clear_secret", "")):
            webhook.secret = None
        elif secret and secret.strip():
            webhook.secret = secret
        webhook.active = request_data(request).get("active", "true") == "true"
        webhook.save()
        return redirect("escalated:admin_webhooks_index")
    return render_page(
        request,
        "Escalated/Admin/Webhooks/Form",
        props={
            "webhook": WebhookSerializer.serialize(webhook),
            "available_events": WebhookSerializer.AVAILABLE_EVENTS,
        },
    )


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
    return render_page(
        request,
        "Escalated/Admin/Webhooks/DeliveryLog",
        props={
            "webhook": WebhookSerializer.serialize(webhook),
            "deliveries": paginated(request, page, WebhookDeliverySerializer.serialize_list(page.object_list)),
        },
    )


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
    """List all automation rules with status, trigger type, and action count."""
    check = _require_admin(request)
    if check:
        return check

    automations = Automation.objects.order_by("position")

    # Filter by active status
    active_filter = request.GET.get("active")
    if active_filter is not None:
        automations = automations.filter(active=active_filter == "true")

    search = request.GET.get("search")
    if search:
        automations = automations.filter(name__icontains=search)

    paginator = Paginator(automations, 20)
    page = paginator.get_page(request.GET.get("page", 1))

    return render_page(
        request,
        "Escalated/Admin/Automations/Index",
        props={
            "automations": AutomationSerializer.serialize_list(page.object_list),
            "pagination": {
                "current_page": page.number,
                "total_pages": paginator.num_pages,
                "total_count": paginator.count,
                "has_next": page.has_next(),
                "has_previous": page.has_previous(),
            },
            "filters": {
                "active": active_filter,
                "search": search,
            },
        },
    )


@login_required
def automations_create(request):
    check = _require_admin(request)
    if check:
        return check
    if request.method == "POST":
        errors = {}
        name = request_data(request).get("name", "").strip()
        if not name:
            errors["name"] = _("Name is required.")
        try:
            conditions = json.loads(request_data(request).get("conditions", "[]"))
        except (json.JSONDecodeError, TypeError):
            conditions = []
        if not isinstance(conditions, list) or len(conditions) < 1:
            errors["conditions"] = _("At least one condition is required.")
        try:
            actions = json.loads(request_data(request).get("actions", "[]"))
        except (json.JSONDecodeError, TypeError):
            actions = []
        if not isinstance(actions, list) or len(actions) < 1:
            errors["actions"] = _("At least one action is required.")
        if errors:
            return render_page(request, "Escalated/Admin/Automations/Form", props={"errors": errors})
        max_pos = Automation.objects.aggregate(max_pos=Max("position"))["max_pos"] or 0
        Automation.objects.create(
            name=name,
            conditions=conditions,
            actions=actions,
            active=request_data(request).get("active", "true") == "true",
            position=max_pos + 1,
        )
        return redirect("escalated:admin_automations_index")
    return render_page(request, "Escalated/Admin/Automations/Form", props={})


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
        errors = {}
        name = request_data(request).get("name", "").strip()
        if not name:
            errors["name"] = _("Name is required.")
        try:
            conditions = json.loads(request_data(request).get("conditions", "[]"))
        except (json.JSONDecodeError, TypeError):
            conditions = automation.conditions
        if not isinstance(conditions, list) or len(conditions) < 1:
            errors["conditions"] = _("At least one condition is required.")
        try:
            actions = json.loads(request_data(request).get("actions", "[]"))
        except (json.JSONDecodeError, TypeError):
            actions = automation.actions
        if not isinstance(actions, list) or len(actions) < 1:
            errors["actions"] = _("At least one action is required.")
        if errors:
            return render_page(
                request,
                "Escalated/Admin/Automations/Form",
                props={"automation": AutomationSerializer.serialize(automation), "errors": errors},
            )
        automation.name = name
        automation.conditions = conditions
        automation.actions = actions
        automation.active = request_data(request).get("active", "true") == "true"
        automation.save()
        return redirect("escalated:admin_automations_index")
    return render_page(
        request, "Escalated/Admin/Automations/Form", props={"automation": AutomationSerializer.serialize(automation)}
    )


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
# Settings - SSO, Two-Factor (CSAT and the other sub-pages: admin_settings_pages.py)
# ---------------------------------------------------------------------------


@login_required
def settings_sso(request):
    check = _require_admin(request)
    if check:
        return check
    from escalated.services.sso_service import SsoService

    sso = SsoService()
    if request.method == "POST":
        data = request_data(request).dict()
        # The page posts the mask back for a secret the admin did not change.
        for key in _SSO_SECRET_KEYS:
            if secret_mask.is_masked(data.get(key)):
                data.pop(key)
        sso.save_config(data)
        return redirect("escalated:admin_settings")

    settings = sso.get_config()
    for key in _SSO_SECRET_KEYS:
        if key in settings:
            settings[key] = secret_mask.mask(settings[key])
    return render_page(request, "Escalated/Admin/Settings/SsoSettings", props={"settings": settings})


@login_required
def settings_two_factor(request):
    check = _require_admin(request)
    if check:
        return check
    two_factor = TwoFactor.objects.filter(user=request.user).first()
    return render_page(
        request,
        "Escalated/Admin/Settings/TwoFactor",
        props={
            "enabled": two_factor.is_confirmed() if two_factor else False,
            "pending": two_factor is not None and not two_factor.is_confirmed() if two_factor else False,
        },
    )


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
    return render_page(
        request,
        "Escalated/Admin/CustomObjects/Index",
        props={"custom_objects": CustomObjectSerializer.serialize_list(objects)},
    )


@login_required
def custom_objects_create(request):
    check = _require_admin(request)
    if check:
        return check
    if request.method == "POST":
        name = request_data(request).get("name", "").strip()
        if not name:
            return render_page(
                request, "Escalated/Admin/CustomObjects/Form", props={"errors": {"name": _("Name is required.")}}
            )
        slug_val = slugify(request_data(request).get("slug", "") or name)
        try:
            fields_schema = json.loads(request_data(request).get("fields_schema", "[]"))
        except (json.JSONDecodeError, TypeError):
            fields_schema = []
        CustomObject.objects.create(name=name, slug=slug_val, fields_schema=fields_schema)
        return redirect("escalated:admin_custom_objects_index")
    return render_page(request, "Escalated/Admin/CustomObjects/Form", props={})


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
        obj.name = request_data(request).get("name", obj.name)
        obj.slug = slugify(request_data(request).get("slug", "") or obj.name)
        try:
            obj.fields_schema = json.loads(request_data(request).get("fields_schema", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass
        obj.save()
        return redirect("escalated:admin_custom_objects_index")
    return render_page(
        request, "Escalated/Admin/CustomObjects/Form", props={"custom_object": CustomObjectSerializer.serialize(obj)}
    )


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
    return render_page(
        request,
        "Escalated/Admin/CustomObjects/Records",
        props={
            "custom_object": CustomObjectSerializer.serialize(obj),
            "records": CustomObjectRecordSerializer.serialize_list(page.object_list),
            "pagination": {
                "current_page": page.number,
                "total_pages": paginator.num_pages,
                "total_count": paginator.count,
                "has_next": page.has_next(),
                "has_previous": page.has_previous(),
            },
        },
    )


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

    from escalated.services import report_pages
    from escalated.views.advanced_reports import _days

    return render_page(request, "Escalated/Admin/Reports/Dashboard", props=report_pages.dashboard(_days(request)))


# ---------------------------------------------------------------------------
# Users management (admin-only)
# ---------------------------------------------------------------------------
#
# Surfaces host User rows so an admin can grant or revoke agent / admin
# access from the panel. Django has no first-class is_admin/is_agent
# columns, so we map:
#   is_admin <-> User.is_staff (the host gate the rest of the package uses)
#   is_agent <-> membership in any active Department
# Hosts that model roles differently (django-guardian, custom AUTH_USER_MODEL,
# etc.) can override these views in their own urls.py.


def _user_is_admin_flag(user) -> bool:
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def _user_is_agent_flag(user, agent_user_ids: set[int]) -> bool:
    return user.pk in agent_user_ids


def _grant_agent(user) -> None:
    """Attach the user to an active department so they count as an agent."""
    department = Department.objects.filter(is_active=True).order_by("pk").first()
    if department is None:
        department = Department.objects.create(
            name="Support",
            slug="support",
            description="Default support department.",
            is_active=True,
        )
    department.agents.add(user)


def _revoke_agent(user) -> None:
    """Remove the user from every department they belong to."""
    for department in Department.objects.filter(agents=user):
        department.agents.remove(user)


@login_required
def users_index(request):
    """List host users with their admin/agent flags for an admin to manage."""
    check = _require_admin(request)
    if check:
        return check

    search = (request.GET.get("search") or "").strip()
    qs = User.objects.all()
    if search:
        qs = qs.filter(
            Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(username__icontains=search)
        )

    # Compute is_admin / is_agent columns. Active department membership is
    # the canonical agent signal in this package (see escalated.permissions).
    qs = qs.order_by("-is_staff", "pk")
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page", 1))

    page_user_ids = [u.pk for u in page.object_list]
    agent_user_ids = set(
        User.objects.filter(escalated_departments__is_active=True, pk__in=page_user_ids)
        .values_list("pk", flat=True)
        .distinct()
    )

    # Frontend sort order: is_admin desc, is_agent desc, id asc. is_staff is
    # already DB-sorted; tiebreak by is_agent here in Python.
    rows = [
        {
            "id": u.pk,
            "name": (u.get_full_name() or u.username) if hasattr(u, "get_full_name") else (u.username or None),
            "email": u.email,
            "is_admin": _user_is_admin_flag(u),
            "is_agent": _user_is_agent_flag(u, agent_user_ids),
        }
        for u in page.object_list
    ]
    rows.sort(key=lambda r: (not r["is_admin"], not r["is_agent"], r["id"]))

    return render_page(
        request,
        "Escalated/Admin/Users/Index",
        props={
            "users": {
                "data": rows,
                "current_page": page.number,
                "last_page": paginator.num_pages,
                "per_page": paginator.per_page,
                "total": paginator.count,
                "has_next": page.has_next(),
                "has_previous": page.has_previous(),
            },
            "filters": {"search": search},
            "currentUserId": request.user.pk if request.user.is_authenticated else None,
        },
    )


@login_required
def users_role(request, user_id):
    """Toggle the admin or agent flag for a user."""
    check = _require_admin(request)
    if check:
        return check

    if request.method not in ("POST", "PATCH"):
        return HttpResponseForbidden(_("Method not allowed"))

    # Parse body — support form-encoded and JSON.
    if request.content_type and "json" in request.content_type:
        try:
            data = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, ValueError):
            data = {}
    else:
        data = request_data(request)

    role = data.get("role") if isinstance(data, dict) else data.get("role", "")
    raw_value = data.get("value") if isinstance(data, dict) else data.get("value", "")

    if role not in ("admin", "agent"):
        return JsonResponse(
            {"message": _("Validation failed."), "errors": {"role": _("Role must be admin or agent.")}},
            status=422,
        )

    if isinstance(raw_value, bool):
        value = raw_value
    elif isinstance(raw_value, str):
        value = raw_value.lower() in ("1", "true", "on", "yes")
    elif isinstance(raw_value, (int, float)):
        value = bool(raw_value)
    else:
        return JsonResponse(
            {"message": _("Validation failed."), "errors": {"value": _("Value must be boolean.")}},
            status=422,
        )

    try:
        target = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return HttpResponseNotFound(_("User not found"))

    # Safety: an admin must not be able to demote themselves and lock
    # themselves out of the admin panel they're using.
    if role == "admin" and not value and str(request.user.pk) == str(target.pk):
        return redirect("escalated:admin_users_index")

    if role == "admin":
        target.is_staff = value
        if value:
            # Admins are agents (mirrors Laravel reference).
            target.save()
            _grant_agent(target)
            return redirect("escalated:admin_users_index")
        target.save()
    else:
        # role == "agent"
        if value:
            _grant_agent(target)
        else:
            _revoke_agent(target)
            # Revoking agent from an admin would leave the admin gate on but
            # the agent gate off — confusing. Demote them fully.
            if _user_is_admin_flag(target):
                target.is_staff = False
                target.save()

    return redirect("escalated:admin_users_index")
