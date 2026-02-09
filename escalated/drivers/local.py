import logging
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from escalated.models import (
    Ticket,
    Reply,
    Tag,
    TicketActivity,
)
from escalated.signals import (
    ticket_created,
    ticket_updated,
    ticket_status_changed,
    ticket_assigned,
    ticket_unassigned,
    ticket_priority_changed,
    ticket_escalated,
    ticket_resolved,
    ticket_closed,
    ticket_reopened,
    reply_created,
    internal_note_added,
    tag_added,
    tag_removed,
    department_changed,
)

logger = logging.getLogger("escalated")


class LocalDriver:
    """
    Full local database implementation. All operations write to Django ORM models
    and fire appropriate Django signals.
    """

    def create_ticket(self, user, data):
        """Create a new ticket in the local database."""
        with transaction.atomic():
            ct = ContentType.objects.get_for_model(user)
            ticket = Ticket(
                requester_content_type=ct,
                requester_object_id=user.pk,
                subject=data["subject"],
                description=data["description"],
                priority=data.get("priority", Ticket.Priority.MEDIUM),
                channel=data.get("channel", "web"),
                department_id=data.get("department_id"),
                metadata=data.get("metadata"),
            )
            ticket.save()

            # Attach tags if provided
            tag_ids = data.get("tag_ids", [])
            if tag_ids:
                ticket.tags.set(tag_ids)

            self._log_activity(
                ticket,
                TicketActivity.ActivityType.CREATED,
                user,
                {"subject": ticket.subject, "priority": ticket.priority},
            )

        ticket_created.send(sender=Ticket, ticket=ticket, user=user)
        return ticket

    def update_ticket(self, ticket, user, data):
        """Update ticket fields."""
        changes = {}
        updatable_fields = ["subject", "description", "metadata"]

        for field in updatable_fields:
            if field in data and getattr(ticket, field) != data[field]:
                changes[field] = {
                    "old": getattr(ticket, field),
                    "new": data[field],
                }
                setattr(ticket, field, data[field])

        if changes:
            ticket.save()
            ticket_updated.send(
                sender=Ticket, ticket=ticket, user=user, changes=changes
            )

        return ticket

    def transition_status(self, ticket, user, new_status):
        """Transition a ticket to a new status."""
        old_status = ticket.status

        if old_status == new_status:
            return ticket

        ticket.status = new_status

        # Set lifecycle timestamps
        now = timezone.now()
        if new_status == Ticket.Status.RESOLVED:
            ticket.resolved_at = now
        elif new_status == Ticket.Status.CLOSED:
            ticket.closed_at = now
        elif new_status == Ticket.Status.REOPENED:
            ticket.resolved_at = None
            ticket.closed_at = None

        ticket.save()

        self._log_activity(
            ticket,
            TicketActivity.ActivityType.STATUS_CHANGED,
            user,
            {"old_status": old_status, "new_status": new_status},
        )

        ticket_status_changed.send(
            sender=Ticket,
            ticket=ticket,
            user=user,
            old_status=old_status,
            new_status=new_status,
        )

        # Fire specific signals
        if new_status == Ticket.Status.RESOLVED:
            ticket_resolved.send(sender=Ticket, ticket=ticket, user=user)
        elif new_status == Ticket.Status.CLOSED:
            ticket_closed.send(sender=Ticket, ticket=ticket, user=user)
        elif new_status == Ticket.Status.REOPENED:
            ticket_reopened.send(sender=Ticket, ticket=ticket, user=user)
        elif new_status == Ticket.Status.ESCALATED:
            ticket_escalated.send(
                sender=Ticket, ticket=ticket, user=user, reason="Manual escalation"
            )

        return ticket

    def assign_ticket(self, ticket, user, agent):
        """Assign a ticket to an agent."""
        previous_agent = ticket.assigned_to
        ticket.assigned_to = agent

        if ticket.status == Ticket.Status.OPEN:
            ticket.status = Ticket.Status.IN_PROGRESS

        ticket.save()

        self._log_activity(
            ticket,
            TicketActivity.ActivityType.ASSIGNED,
            user,
            {
                "agent_id": agent.pk,
                "agent_name": getattr(agent, "get_full_name", lambda: str(agent))(),
            },
        )

        ticket_assigned.send(
            sender=Ticket, ticket=ticket, user=user, agent=agent
        )

        return ticket

    def unassign_ticket(self, ticket, user):
        """Remove agent assignment from a ticket."""
        previous_agent = ticket.assigned_to
        ticket.assigned_to = None
        ticket.save()

        self._log_activity(
            ticket,
            TicketActivity.ActivityType.UNASSIGNED,
            user,
            {
                "previous_agent_id": previous_agent.pk if previous_agent else None,
            },
        )

        ticket_unassigned.send(
            sender=Ticket,
            ticket=ticket,
            user=user,
            previous_agent=previous_agent,
        )

        return ticket

    def add_reply(self, ticket, user, data):
        """Add a reply or internal note to a ticket."""
        is_internal = data.get("is_internal_note", False)
        reply_type = Reply.Type.NOTE if is_internal else Reply.Type.REPLY

        reply = Reply.objects.create(
            ticket=ticket,
            author=user,
            body=data["body"],
            is_internal_note=is_internal,
            type=reply_type,
            metadata=data.get("metadata"),
        )

        # Update ticket status based on who is replying
        if not is_internal and user is not None:
            ct = ContentType.objects.get_for_model(user)
            is_requester = (
                ticket.requester_content_type == ct
                and ticket.requester_object_id == user.pk
            )

            if is_requester:
                if ticket.status == Ticket.Status.WAITING_ON_CUSTOMER:
                    self.transition_status(
                        ticket, user, Ticket.Status.WAITING_ON_AGENT
                    )
            else:
                if ticket.status in [
                    Ticket.Status.OPEN,
                    Ticket.Status.WAITING_ON_AGENT,
                    Ticket.Status.REOPENED,
                ]:
                    self.transition_status(
                        ticket, user, Ticket.Status.WAITING_ON_CUSTOMER
                    )
        elif not is_internal and user is None:
            # Guest reply — treat like a customer reply
            if ticket.status == Ticket.Status.WAITING_ON_CUSTOMER:
                self.transition_status(ticket, None, Ticket.Status.OPEN)

        # Fire signals
        if is_internal:
            internal_note_added.send(
                sender=Reply, reply=reply, ticket=ticket, user=user
            )
        else:
            reply_created.send(
                sender=Reply, reply=reply, ticket=ticket, user=user
            )

        return reply

    def get_ticket(self, ticket_id):
        """Retrieve a single ticket by ID."""
        return (
            Ticket.objects.select_related(
                "assigned_to", "department", "sla_policy"
            )
            .prefetch_related("tags", "replies", "activities")
            .get(pk=ticket_id)
        )

    def list_tickets(self, filters=None):
        """List tickets with optional filters."""
        qs = Ticket.objects.select_related(
            "assigned_to", "department", "sla_policy"
        ).prefetch_related("tags")

        if filters:
            if "status" in filters:
                qs = qs.filter(status=filters["status"])
            if "priority" in filters:
                qs = qs.filter(priority=filters["priority"])
            if "assigned_to" in filters:
                qs = qs.filter(assigned_to_id=filters["assigned_to"])
            if "department" in filters:
                qs = qs.filter(department_id=filters["department"])
            if "search" in filters:
                qs = qs.search(filters["search"])
            if "requester_id" in filters and "requester_type" in filters:
                qs = qs.filter(
                    requester_content_type_id=filters["requester_type"],
                    requester_object_id=filters["requester_id"],
                )
            if "tag" in filters:
                qs = qs.filter(tags__slug=filters["tag"])

        return qs

    def add_tags(self, ticket, user, tag_ids):
        """Add tags to a ticket."""
        tags = Tag.objects.filter(pk__in=tag_ids)
        for tag in tags:
            ticket.tags.add(tag)
            self._log_activity(
                ticket,
                TicketActivity.ActivityType.TAG_ADDED,
                user,
                {"tag_id": tag.pk, "tag_name": tag.name},
            )
            tag_added.send(sender=Tag, tag=tag, ticket=ticket, user=user)

    def remove_tags(self, ticket, user, tag_ids):
        """Remove tags from a ticket."""
        tags = Tag.objects.filter(pk__in=tag_ids)
        for tag in tags:
            ticket.tags.remove(tag)
            self._log_activity(
                ticket,
                TicketActivity.ActivityType.TAG_REMOVED,
                user,
                {"tag_id": tag.pk, "tag_name": tag.name},
            )
            tag_removed.send(sender=Tag, tag=tag, ticket=ticket, user=user)

    def change_department(self, ticket, user, department):
        """Change the department of a ticket."""
        old_department = ticket.department
        ticket.department = department
        ticket.save()

        self._log_activity(
            ticket,
            TicketActivity.ActivityType.DEPARTMENT_CHANGED,
            user,
            {
                "old_department_id": old_department.pk if old_department else None,
                "old_department_name": str(old_department) if old_department else None,
                "new_department_id": department.pk,
                "new_department_name": str(department),
            },
        )

        department_changed.send(
            sender=Ticket,
            ticket=ticket,
            user=user,
            old_department=old_department,
            new_department=department,
        )

        return ticket

    def change_priority(self, ticket, user, new_priority):
        """Change the priority of a ticket."""
        old_priority = ticket.priority

        if old_priority == new_priority:
            return ticket

        ticket.priority = new_priority
        ticket.save()

        self._log_activity(
            ticket,
            TicketActivity.ActivityType.PRIORITY_CHANGED,
            user,
            {"old_priority": old_priority, "new_priority": new_priority},
        )

        ticket_priority_changed.send(
            sender=Ticket,
            ticket=ticket,
            user=user,
            old_priority=old_priority,
            new_priority=new_priority,
        )

        return ticket

    # ----- internal helpers -----

    def _log_activity(self, ticket, activity_type, user=None, properties=None):
        """Create an activity log entry."""
        activity_kwargs = {
            "ticket": ticket,
            "type": activity_type,
            "properties": properties or {},
        }
        if user:
            ct = ContentType.objects.get_for_model(user)
            activity_kwargs["causer_content_type"] = ct
            activity_kwargs["causer_object_id"] = user.pk

        TicketActivity.objects.create(**activity_kwargs)
