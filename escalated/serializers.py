"""
Dict-based serializers for converting Django model instances to plain dicts
suitable for Inertia.js props. No DRF dependency required.
"""

from django.utils.formats import date_format


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
            "department": (
                DepartmentSerializer.serialize(ticket.department)
                if ticket.department
                else None
            ),
            "sla_policy": (
                SlaPolicySerializer.serialize_brief(ticket.sla_policy)
                if ticket.sla_policy
                else None
            ),
            "tags": [
                TagSerializer.serialize(tag) for tag in ticket.tags.all()
            ],
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
            data["replies"] = [
                ReplySerializer.serialize(reply)
                for reply in ticket.replies.filter(is_deleted=False)
            ]

        if include_activities:
            data["activities"] = [
                ActivitySerializer.serialize(activity)
                for activity in ticket.activities.all()[:50]
            ]

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
            "attachments": [
                AttachmentSerializer.serialize(a)
                for a in reply.attachments.all()
            ],
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
