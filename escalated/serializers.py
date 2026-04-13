"""
Dict-based serializers for converting Django model instances to plain dicts
suitable for Inertia.js props. No DRF dependency required.
"""


def _format_dt(dt):
    """Format a datetime for JSON output, or return None."""
    if dt is None:
        return None
    return dt.isoformat()


def _user_dict(user):
    """Serialize a user to a minimal dict."""
    if user is None:
        return None
    return {
        "id": user.pk,
        "name": getattr(user, "get_full_name", lambda: str(user))(),
        "email": getattr(user, "email", ""),
    }


class TicketSerializer:
    @staticmethod
    def serialize(ticket, include_replies=False, include_activities=False):
        data = {
            "id": ticket.pk,
            "reference": ticket.reference,
            "subject": ticket.subject,
            "description": ticket.description,
            "status": ticket.status,
            "status_display": ticket.get_status_display(),
            "priority": ticket.priority,
            "priority_display": ticket.get_priority_display(),
            "channel": ticket.channel,
            "assigned_to": _user_dict(ticket.assigned_to),
            "department": (DepartmentSerializer.serialize(ticket.department) if ticket.department else None),
            "sla_policy": (SlaPolicySerializer.serialize_brief(ticket.sla_policy) if ticket.sla_policy else None),
            "tags": [TagSerializer.serialize(tag) for tag in ticket.tags.all()],
            "is_open": ticket.is_open,
            "first_response_at": _format_dt(ticket.first_response_at),
            "first_response_due_at": _format_dt(ticket.first_response_due_at),
            "resolution_due_at": _format_dt(ticket.resolution_due_at),
            "sla_first_response_breached": ticket.sla_first_response_breached,
            "sla_resolution_breached": ticket.sla_resolution_breached,
            "resolved_at": _format_dt(ticket.resolved_at),
            "closed_at": _format_dt(ticket.closed_at),
            "metadata": ticket.metadata,
            "created_at": _format_dt(ticket.created_at),
            "updated_at": _format_dt(ticket.updated_at),
        }

        # Ticket-level attachments
        data["attachments"] = [
            AttachmentSerializer.serialize(a) for a in ticket.attachments.all()
        ]

        # Guest ticket fields
        data["is_guest"] = ticket.is_guest
        data["guest_name"] = ticket.guest_name
        data["guest_email"] = ticket.guest_email
        data["requester_name"] = ticket.requester_name
        data["requester_email"] = ticket.requester_email

        # Include requester info
        try:
            requester = ticket.requester
            data["requester"] = _user_dict(requester) if requester else None
        except Exception:
            data["requester"] = None

        if include_replies:
            data["replies"] = [ReplySerializer.serialize(reply) for reply in ticket.replies.filter(is_deleted=False)]

        if include_activities:
            data["activities"] = [ActivitySerializer.serialize(activity) for activity in ticket.activities.all()[:50]]

        return data

    @staticmethod
    def serialize_list(tickets):
        return [TicketSerializer.serialize(t) for t in tickets]


class ReplySerializer:
    @staticmethod
    def serialize(reply):
        return {
            "id": reply.pk,
            "ticket_id": reply.ticket_id,
            "author": _user_dict(reply.author),
            "body": reply.body,
            "is_internal_note": reply.is_internal_note,
            "is_pinned": reply.is_pinned,
            "type": reply.type,
            "type_display": reply.get_type_display(),
            "metadata": reply.metadata,
            "attachments": [AttachmentSerializer.serialize(a) for a in reply.attachments.all()],
            "created_at": _format_dt(reply.created_at),
            "updated_at": _format_dt(reply.updated_at),
        }

    @staticmethod
    def serialize_list(replies):
        return [ReplySerializer.serialize(r) for r in replies]


class TagSerializer:
    @staticmethod
    def serialize(tag):
        return {
            "id": tag.pk,
            "name": tag.name,
            "slug": tag.slug,
            "color": tag.color,
        }

    @staticmethod
    def serialize_list(tags):
        return [TagSerializer.serialize(t) for t in tags]


class DepartmentSerializer:
    @staticmethod
    def serialize(department):
        return {
            "id": department.pk,
            "name": department.name,
            "slug": department.slug,
            "description": department.description,
            "is_active": department.is_active,
            "agent_count": department.agents.count(),
            "created_at": _format_dt(department.created_at),
            "updated_at": _format_dt(department.updated_at),
        }

    @staticmethod
    def serialize_list(departments):
        return [DepartmentSerializer.serialize(d) for d in departments]


class SlaPolicySerializer:
    @staticmethod
    def serialize(policy):
        return {
            "id": policy.pk,
            "name": policy.name,
            "description": policy.description,
            "is_default": policy.is_default,
            "first_response_hours": policy.first_response_hours,
            "resolution_hours": policy.resolution_hours,
            "business_hours_only": policy.business_hours_only,
            "is_active": policy.is_active,
            "created_at": _format_dt(policy.created_at),
            "updated_at": _format_dt(policy.updated_at),
        }

    @staticmethod
    def serialize_brief(policy):
        """Minimal serialization for embedding in ticket data."""
        return {
            "id": policy.pk,
            "name": policy.name,
            "is_default": policy.is_default,
        }

    @staticmethod
    def serialize_list(policies):
        return [SlaPolicySerializer.serialize(p) for p in policies]


class EscalationRuleSerializer:
    @staticmethod
    def serialize(rule):
        return {
            "id": rule.pk,
            "name": rule.name,
            "description": rule.description,
            "trigger_type": rule.trigger_type,
            "trigger_type_display": rule.get_trigger_type_display(),
            "conditions": rule.conditions,
            "actions": rule.actions,
            "order": rule.order,
            "is_active": rule.is_active,
            "created_at": _format_dt(rule.created_at),
            "updated_at": _format_dt(rule.updated_at),
        }

    @staticmethod
    def serialize_list(rules):
        return [EscalationRuleSerializer.serialize(r) for r in rules]


class CannedResponseSerializer:
    @staticmethod
    def serialize(response):
        return {
            "id": response.pk,
            "title": response.title,
            "body": response.body,
            "category": response.category,
            "created_by": _user_dict(response.created_by),
            "is_shared": response.is_shared,
            "created_at": _format_dt(response.created_at),
            "updated_at": _format_dt(response.updated_at),
        }

    @staticmethod
    def serialize_list(responses):
        return [CannedResponseSerializer.serialize(r) for r in responses]


class ActivitySerializer:
    @staticmethod
    def serialize(activity):
        data = {
            "id": activity.pk,
            "ticket_id": activity.ticket_id,
            "type": activity.type,
            "type_display": activity.get_type_display(),
            "properties": activity.properties,
            "created_at": _format_dt(activity.created_at),
        }
        try:
            causer = activity.causer
            data["causer"] = _user_dict(causer) if causer else None
        except Exception:
            data["causer"] = None
        return data


class AttachmentSerializer:
    @staticmethod
    def serialize(attachment):
        return {
            "id": attachment.pk,
            "original_filename": attachment.original_filename,
            "mime_type": attachment.mime_type,
            "size": attachment.size,
            "size_kb": attachment.size_kb,
            "url": attachment.file.url if attachment.file else None,
            "created_at": _format_dt(attachment.created_at),
        }

    @staticmethod
    def serialize_list(attachments):
        return [AttachmentSerializer.serialize(a) for a in attachments]


class EscalatedSettingSerializer:
    @staticmethod
    def serialize(setting):
        return {
            "id": setting.pk,
            "key": setting.key,
            "value": setting.value,
            "created_at": _format_dt(setting.created_at),
            "updated_at": _format_dt(setting.updated_at),
        }

    @staticmethod
    def serialize_list(settings_qs):
        return [EscalatedSettingSerializer.serialize(s) for s in settings_qs]

    @staticmethod
    def serialize_as_dict(settings_qs):
        """Serialize settings as a key-value dict for frontend use."""
        return {s.key: s.value for s in settings_qs}


class MacroSerializer:
    @staticmethod
    def serialize(macro):
        return {
            "id": macro.pk,
            "name": macro.name,
            "description": macro.description,
            "actions": macro.actions,
            "is_shared": macro.is_shared,
            "order": macro.order,
            "created_by": _user_dict(macro.created_by),
            "created_at": _format_dt(macro.created_at),
            "updated_at": _format_dt(macro.updated_at),
        }

    @staticmethod
    def serialize_list(macros):
        return [MacroSerializer.serialize(m) for m in macros]


class SatisfactionRatingSerializer:
    @staticmethod
    def serialize(rating):
        data = {
            "id": rating.pk,
            "ticket_id": rating.ticket_id,
            "rating": rating.rating,
            "comment": rating.comment,
            "created_at": _format_dt(rating.created_at),
        }
        try:
            rater = rating.rated_by
            data["rated_by"] = _user_dict(rater) if rater else None
        except Exception:
            data["rated_by"] = None
        return data


class AuditLogSerializer:
    @staticmethod
    def serialize(log):
        return {
            "id": log.pk,
            "user": _user_dict(log.user),
            "action": log.action,
            "auditable_type": str(log.auditable_content_type),
            "auditable_id": log.auditable_object_id,
            "old_values": log.old_values,
            "new_values": log.new_values,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "created_at": _format_dt(log.created_at),
        }

    @staticmethod
    def serialize_list(logs):
        return [AuditLogSerializer.serialize(log) for log in logs]


class TicketStatusSerializer:
    @staticmethod
    def serialize(status):
        return {
            "id": status.pk,
            "label": status.label,
            "slug": status.slug,
            "category": status.category,
            "color": status.color,
            "description": status.description,
            "position": status.position,
            "is_default": status.is_default,
            "created_at": _format_dt(status.created_at),
            "updated_at": _format_dt(status.updated_at),
        }

    @staticmethod
    def serialize_list(statuses):
        return [TicketStatusSerializer.serialize(s) for s in statuses]


class HolidaySerializer:
    @staticmethod
    def serialize(holiday):
        return {
            "id": holiday.pk,
            "name": holiday.name,
            "date": str(holiday.date),
            "recurring": holiday.recurring,
        }


class BusinessScheduleSerializer:
    @staticmethod
    def serialize(schedule, include_holidays=True):
        data = {
            "id": schedule.pk,
            "name": schedule.name,
            "timezone": schedule.timezone,
            "is_default": schedule.is_default,
            "schedule": schedule.schedule,
            "created_at": _format_dt(schedule.created_at),
            "updated_at": _format_dt(schedule.updated_at),
        }
        if include_holidays:
            data["holidays"] = [HolidaySerializer.serialize(h) for h in schedule.holidays.all()]
        return data

    @staticmethod
    def serialize_list(schedules):
        return [BusinessScheduleSerializer.serialize(s) for s in schedules]


class PermissionSerializer:
    @staticmethod
    def serialize(permission):
        return {
            "id": permission.pk,
            "name": permission.name,
            "slug": permission.slug,
            "group": permission.group,
            "description": permission.description,
        }

    @staticmethod
    def serialize_list(permissions):
        return [PermissionSerializer.serialize(p) for p in permissions]

    @staticmethod
    def serialize_grouped(permissions):
        """Group permissions by their group field."""
        grouped = {}
        for p in permissions:
            group = p.group
            if group not in grouped:
                grouped[group] = []
            grouped[group].append(PermissionSerializer.serialize(p))
        return grouped


class RoleSerializer:
    @staticmethod
    def serialize(role, include_permissions=False):
        data = {
            "id": role.pk,
            "name": role.name,
            "slug": role.slug,
            "description": role.description,
            "is_system": role.is_system,
            "users_count": role.users.count()
            if hasattr(role, "_prefetched_objects_cache")
            else getattr(role, "users__count", role.users.count()),
            "created_at": _format_dt(role.created_at),
            "updated_at": _format_dt(role.updated_at),
        }
        if include_permissions:
            data["permissions"] = PermissionSerializer.serialize_list(role.permissions.all())
        return data

    @staticmethod
    def serialize_list(roles):
        return [RoleSerializer.serialize(r) for r in roles]


class CustomFieldSerializer:
    @staticmethod
    def serialize(field):
        return {
            "id": field.pk,
            "name": field.name,
            "slug": field.slug,
            "type": field.type,
            "context": field.context,
            "options": field.options,
            "required": field.required,
            "placeholder": field.placeholder,
            "description": field.description,
            "validation_rules": field.validation_rules,
            "conditions": field.conditions,
            "position": field.position,
            "active": field.active,
            "created_at": _format_dt(field.created_at),
            "updated_at": _format_dt(field.updated_at),
        }

    @staticmethod
    def serialize_list(fields):
        return [CustomFieldSerializer.serialize(f) for f in fields]


class CustomFieldValueSerializer:
    @staticmethod
    def serialize(value):
        return {
            "id": value.pk,
            "custom_field_id": value.custom_field_id,
            "entity_type": str(value.entity_content_type),
            "entity_id": value.entity_object_id,
            "value": value.value,
        }

    @staticmethod
    def serialize_list(values):
        return [CustomFieldValueSerializer.serialize(v) for v in values]


class TicketLinkSerializer:
    @staticmethod
    def serialize(link, direction="parent"):
        ticket = link.child_ticket if direction == "parent" else link.parent_ticket
        return {
            "id": link.pk,
            "link_type": link.link_type,
            "direction": direction,
            "ticket": {
                "id": ticket.pk,
                "reference": ticket.reference,
                "subject": ticket.subject,
                "status": ticket.status,
                "type": getattr(ticket, "type", "question"),
            },
        }


class SideConversationReplySerializer:
    @staticmethod
    def serialize(reply):
        return {
            "id": reply.pk,
            "side_conversation_id": reply.side_conversation_id,
            "body": reply.body,
            "author": _user_dict(reply.author),
            "created_at": _format_dt(reply.created_at),
            "updated_at": _format_dt(reply.updated_at),
        }

    @staticmethod
    def serialize_list(replies):
        return [SideConversationReplySerializer.serialize(r) for r in replies]


class SideConversationSerializer:
    @staticmethod
    def serialize(conversation, include_replies=True):
        data = {
            "id": conversation.pk,
            "ticket_id": conversation.ticket_id,
            "subject": conversation.subject,
            "channel": conversation.channel,
            "status": conversation.status,
            "created_by": _user_dict(conversation.created_by),
            "created_at": _format_dt(conversation.created_at),
            "updated_at": _format_dt(conversation.updated_at),
        }
        if include_replies:
            replies = conversation.replies.all()
            data["replies"] = SideConversationReplySerializer.serialize_list(replies)
            data["reply_count"] = len(data["replies"])
        elif hasattr(conversation, "reply_count"):
            data["reply_count"] = conversation.reply_count
        return data

    @staticmethod
    def serialize_list(conversations):
        return [SideConversationSerializer.serialize(c) for c in conversations]


class ArticleCategorySerializer:
    @staticmethod
    def serialize(category):
        data = {
            "id": category.pk,
            "name": category.name,
            "slug": category.slug,
            "parent_id": category.parent_id,
            "position": category.position,
            "description": category.description,
            "created_at": _format_dt(category.created_at),
            "updated_at": _format_dt(category.updated_at),
        }
        if hasattr(category, "articles__count"):
            data["articles_count"] = category.articles__count
        elif hasattr(category, "articles_count"):
            data["articles_count"] = category.articles_count
        return data

    @staticmethod
    def serialize_list(categories):
        return [ArticleCategorySerializer.serialize(c) for c in categories]


class ArticleSerializer:
    @staticmethod
    def serialize(article):
        return {
            "id": article.pk,
            "category": (ArticleCategorySerializer.serialize(article.category) if article.category else None),
            "title": article.title,
            "slug": article.slug,
            "body": article.body,
            "status": article.status,
            "author": _user_dict(article.author),
            "view_count": article.view_count,
            "helpful_count": article.helpful_count,
            "not_helpful_count": article.not_helpful_count,
            "published_at": _format_dt(article.published_at),
            "created_at": _format_dt(article.created_at),
            "updated_at": _format_dt(article.updated_at),
        }

    @staticmethod
    def serialize_list(articles):
        return [ArticleSerializer.serialize(a) for a in articles]


class AgentProfileSerializer:
    @staticmethod
    def serialize(profile):
        return {
            "id": profile.pk,
            "user_id": profile.user_id,
            "user": _user_dict(profile.user) if hasattr(profile, "user") else None,
            "agent_type": profile.agent_type,
            "max_tickets": profile.max_tickets,
            "created_at": _format_dt(profile.created_at),
            "updated_at": _format_dt(profile.updated_at),
        }

    @staticmethod
    def serialize_list(profiles):
        return [AgentProfileSerializer.serialize(p) for p in profiles]


class SkillSerializer:
    @staticmethod
    def serialize(skill):
        data = {
            "id": skill.pk,
            "name": skill.name,
            "slug": skill.slug,
            "created_at": _format_dt(skill.created_at),
            "updated_at": _format_dt(skill.updated_at),
        }
        if hasattr(skill, "agents_count"):
            data["agents_count"] = skill.agents_count
        elif hasattr(skill, "agents__count"):
            data["agents_count"] = skill.agents__count
        return data

    @staticmethod
    def serialize_list(skills):
        return [SkillSerializer.serialize(s) for s in skills]


class AgentCapacitySerializer:
    @staticmethod
    def serialize(cap):
        return {
            "id": cap.pk,
            "user_id": cap.user_id,
            "agent_name": (cap.user.get_full_name() or cap.user.username) if cap.user else "Unknown",
            "channel": cap.channel,
            "max_concurrent": cap.max_concurrent,
            "current_count": cap.current_count,
            "load_percentage": cap.load_percentage(),
        }

    @staticmethod
    def serialize_list(capacities):
        return [AgentCapacitySerializer.serialize(c) for c in capacities]


class WebhookSerializer:
    AVAILABLE_EVENTS = [
        "ticket.created",
        "ticket.updated",
        "ticket.status_changed",
        "ticket.resolved",
        "ticket.closed",
        "ticket.reopened",
        "ticket.assigned",
        "ticket.unassigned",
        "ticket.escalated",
        "ticket.priority_changed",
        "ticket.department_changed",
        "reply.created",
        "internal_note.added",
        "sla.breached",
        "sla.warning",
        "tag.added",
        "tag.removed",
    ]

    @staticmethod
    def serialize(webhook):
        data = {
            "id": webhook.pk,
            "url": webhook.url,
            "events": webhook.events,
            "secret": bool(webhook.secret),
            "active": webhook.active,
            "created_at": _format_dt(webhook.created_at),
            "updated_at": _format_dt(webhook.updated_at),
        }
        if hasattr(webhook, "deliveries_count"):
            data["deliveries_count"] = webhook.deliveries_count
        elif hasattr(webhook, "deliveries__count"):
            data["deliveries_count"] = webhook.deliveries__count
        return data

    @staticmethod
    def serialize_list(webhooks):
        return [WebhookSerializer.serialize(w) for w in webhooks]


class WebhookDeliverySerializer:
    @staticmethod
    def serialize(delivery):
        return {
            "id": delivery.pk,
            "webhook_id": delivery.webhook_id,
            "event": delivery.event,
            "payload": delivery.payload,
            "response_code": delivery.response_code,
            "response_body": delivery.response_body,
            "attempts": delivery.attempts,
            "is_success": delivery.is_success(),
            "delivered_at": _format_dt(delivery.delivered_at),
            "created_at": _format_dt(delivery.created_at),
        }

    @staticmethod
    def serialize_list(deliveries):
        return [WebhookDeliverySerializer.serialize(d) for d in deliveries]


class AutomationSerializer:
    @staticmethod
    def serialize(automation):
        conditions = automation.conditions or []
        actions = automation.actions or []
        # Extract the trigger type from the first condition if available
        trigger_type = None
        if conditions and isinstance(conditions, list) and len(conditions) > 0:
            first = conditions[0]
            if isinstance(first, dict):
                trigger_type = first.get("type") or first.get("field")
        return {
            "id": automation.pk,
            "name": automation.name,
            "conditions": conditions,
            "actions": actions,
            "active": automation.active,
            "position": automation.position,
            "trigger_type": trigger_type,
            "condition_count": len(conditions) if isinstance(conditions, list) else 0,
            "action_count": len(actions) if isinstance(actions, list) else 0,
            "last_run_at": _format_dt(automation.last_run_at),
            "created_at": _format_dt(automation.created_at),
            "updated_at": _format_dt(automation.updated_at),
        }

    @staticmethod
    def serialize_list(automations):
        return [AutomationSerializer.serialize(a) for a in automations]


class CustomObjectSerializer:
    @staticmethod
    def serialize(obj):
        data = {
            "id": obj.pk,
            "name": obj.name,
            "slug": obj.slug,
            "fields_schema": obj.fields_schema,
            "created_at": _format_dt(obj.created_at),
            "updated_at": _format_dt(obj.updated_at),
        }
        if hasattr(obj, "records_count"):
            data["records_count"] = obj.records_count
        elif hasattr(obj, "records__count"):
            data["records_count"] = obj.records__count
        return data

    @staticmethod
    def serialize_list(objects):
        return [CustomObjectSerializer.serialize(o) for o in objects]


class CustomObjectRecordSerializer:
    @staticmethod
    def serialize(record):
        return {
            "id": record.pk,
            "object_id": record.object_id,
            "data": record.data,
            "created_at": _format_dt(record.created_at),
            "updated_at": _format_dt(record.updated_at),
        }

    @staticmethod
    def serialize_list(records):
        return [CustomObjectRecordSerializer.serialize(r) for r in records]
