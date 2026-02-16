"""
Dict-based serializers for the REST API, producing JSON-compatible output that
matches the Laravel API response format.
"""

from escalated.serializers import _format_dt, _user_dict


class ApiTicketCollectionSerializer:
    """Slim ticket serializer for list endpoints."""

    @staticmethod
    def serialize(ticket):
        assignee = ticket.assigned_to
        department = ticket.department

        return {
            "id": ticket.pk,
            "reference": ticket.reference,
            "subject": ticket.subject,
            "status": ticket.status,
            "status_label": ticket.get_status_display(),
            "priority": ticket.priority,
            "priority_label": ticket.get_priority_display(),
            "requester": {
                "name": ticket.requester_name,
                "email": ticket.requester_email,
            },
            "assignee": (
                {
                    "id": assignee.pk,
                    "name": getattr(assignee, "get_full_name", lambda: str(assignee))(),
                }
                if assignee
                else None
            ),
            "department": (
                {"id": department.pk, "name": department.name}
                if department
                else None
            ),
            "sla_breached": (
                ticket.sla_first_response_breached
                or ticket.sla_resolution_breached
            ),
            "created_at": _format_dt(ticket.created_at),
            "updated_at": _format_dt(ticket.updated_at),
        }

    @staticmethod
    def serialize_list(tickets):
        return [ApiTicketCollectionSerializer.serialize(t) for t in tickets]


class ApiTicketDetailSerializer:
    """Full ticket serializer for detail endpoints."""

    @staticmethod
    def serialize(ticket, include_replies=True, include_activities=True):
        assignee = ticket.assigned_to
        department = ticket.department

        data = {
            "id": ticket.pk,
            "reference": ticket.reference,
            "subject": ticket.subject,
            "description": ticket.description,
            "status": ticket.status,
            "status_label": ticket.get_status_display(),
            "priority": ticket.priority,
            "priority_label": ticket.get_priority_display(),
            "channel": ticket.channel,
            "metadata": ticket.metadata,
            "requester": {
                "name": ticket.requester_name,
                "email": ticket.requester_email,
            },
            "assignee": (
                {
                    "id": assignee.pk,
                    "name": getattr(assignee, "get_full_name", lambda: str(assignee))(),
                    "email": getattr(assignee, "email", ""),
                }
                if assignee
                else None
            ),
            "department": (
                {"id": department.pk, "name": department.name}
                if department
                else None
            ),
            "tags": [
                {"id": tag.pk, "name": tag.name, "color": tag.color}
                for tag in ticket.tags.all()
            ],
            "sla": {
                "first_response_due_at": _format_dt(ticket.first_response_due_at),
                "first_response_at": _format_dt(ticket.first_response_at),
                "first_response_breached": ticket.sla_first_response_breached,
                "resolution_due_at": _format_dt(ticket.resolution_due_at),
                "resolution_breached": ticket.sla_resolution_breached,
            },
            "resolved_at": _format_dt(ticket.resolved_at),
            "closed_at": _format_dt(ticket.closed_at),
            "created_at": _format_dt(ticket.created_at),
            "updated_at": _format_dt(ticket.updated_at),
        }

        if include_replies:
            data["replies"] = [
                ApiReplySerializer.serialize(reply)
                for reply in ticket.replies.filter(is_deleted=False)
            ]

        if include_activities:
            data["activities"] = [
                ApiActivitySerializer.serialize(activity)
                for activity in ticket.activities.all()[:20]
            ]

        return data


class ApiReplySerializer:
    """Reply serializer for API output."""

    @staticmethod
    def serialize(reply):
        author = reply.author
        data = {
            "id": reply.pk,
            "body": reply.body,
            "is_internal_note": reply.is_internal_note,
            "is_pinned": reply.is_pinned,
            "author": (
                {
                    "id": author.pk,
                    "name": getattr(author, "get_full_name", lambda: str(author))(),
                    "email": getattr(author, "email", None),
                }
                if author
                else None
            ),
            "attachments": [
                ApiAttachmentSerializer.serialize(a)
                for a in reply.attachments.all()
            ],
            "created_at": _format_dt(reply.created_at),
        }
        return data


class ApiActivitySerializer:
    """Activity serializer for API output."""

    @staticmethod
    def serialize(activity):
        data = {
            "id": activity.pk,
            "type": activity.type,
            "description": activity.get_type_display(),
            "properties": activity.properties,
            "created_at": _format_dt(activity.created_at),
        }
        try:
            causer = activity.causer
            data["causer"] = (
                {"id": causer.pk, "name": getattr(causer, "get_full_name", lambda: str(causer))()}
                if causer
                else None
            )
        except Exception:
            data["causer"] = None
        return data


class ApiAttachmentSerializer:
    """Attachment serializer for API output."""

    @staticmethod
    def serialize(attachment):
        return {
            "id": attachment.pk,
            "filename": attachment.original_filename,
            "mime_type": attachment.mime_type,
            "size": attachment.size,
            "url": attachment.file.url if attachment.file else None,
        }


class ApiAgentSerializer:
    """Agent (user) serializer for API output."""

    @staticmethod
    def serialize(user):
        return {
            "id": user.pk,
            "name": getattr(user, "get_full_name", lambda: str(user))(),
            "email": getattr(user, "email", ""),
        }

    @staticmethod
    def serialize_list(users):
        return [ApiAgentSerializer.serialize(u) for u in users]


class ApiDepartmentSerializer:
    """Department serializer for API output."""

    @staticmethod
    def serialize(department):
        return {
            "id": department.pk,
            "name": department.name,
            "description": department.description,
            "is_active": department.is_active,
        }

    @staticmethod
    def serialize_list(departments):
        return [ApiDepartmentSerializer.serialize(d) for d in departments]


class ApiTagSerializer:
    """Tag serializer for API output."""

    @staticmethod
    def serialize(tag):
        return {
            "id": tag.pk,
            "name": tag.name,
            "color": tag.color,
        }

    @staticmethod
    def serialize_list(tags):
        return [ApiTagSerializer.serialize(t) for t in tags]


class ApiCannedResponseSerializer:
    """Canned response serializer for API output."""

    @staticmethod
    def serialize(response):
        return {
            "id": response.pk,
            "title": response.title,
            "body": response.body,
        }

    @staticmethod
    def serialize_list(responses):
        return [ApiCannedResponseSerializer.serialize(r) for r in responses]


class ApiMacroSerializer:
    """Macro serializer for API output."""

    @staticmethod
    def serialize(macro):
        return {
            "id": macro.pk,
            "name": macro.name,
            "actions": macro.actions,
            "order": macro.order,
        }

    @staticmethod
    def serialize_list(macros):
        return [ApiMacroSerializer.serialize(m) for m in macros]


class ApiTokenSerializer:
    """API token serializer for admin views."""

    @staticmethod
    def serialize(token):
        tokenable = token.tokenable
        return {
            "id": token.pk,
            "name": token.name,
            "user_name": (
                getattr(tokenable, "get_full_name", lambda: str(tokenable))()
                if tokenable
                else None
            ),
            "user_email": getattr(tokenable, "email", None) if tokenable else None,
            "abilities": token.abilities,
            "last_used_at": _format_dt(token.last_used_at),
            "last_used_ip": token.last_used_ip,
            "expires_at": _format_dt(token.expires_at),
            "is_expired": token.is_expired,
            "created_at": _format_dt(token.created_at),
        }

    @staticmethod
    def serialize_list(tokens):
        return [ApiTokenSerializer.serialize(t) for t in tokens]
