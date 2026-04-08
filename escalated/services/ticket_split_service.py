from django.db import transaction


class TicketSplitService:
    """Service for splitting a reply out of a ticket into a new ticket."""

    def split_ticket(self, source, reply, data, split_by_user_id=None):
        """
        Split a reply from the source ticket into a new ticket.

        Creates a new ticket using the reply body as description, copies
        relevant metadata from the source ticket, links the two tickets,
        and logs activity on both.

        Args:
            source: The original Ticket the reply belongs to.
            reply: The Reply to split out (its body becomes the new ticket description).
            data: dict with optional overrides — subject, priority, department_id, assigned_to_id.
            split_by_user_id: ID of the user performing the split.

        Returns:
            The newly created Ticket.
        """
        with transaction.atomic():
            from django.contrib.contenttypes.models import ContentType

            from escalated.models import Reply, Ticket, TicketActivity, TicketLink

            subject = data.get("subject") or f"Split from {source.reference}: {source.subject}"
            if len(subject) > 500:
                subject = subject[:497] + "..."

            new_ticket = Ticket(
                subject=subject,
                description=reply.body,
                priority=data.get("priority", source.priority),
                channel=source.channel,
                ticket_type=source.ticket_type,
                status=Ticket.Status.OPEN,
            )

            # Copy requester from source
            new_ticket.requester_content_type = source.requester_content_type
            new_ticket.requester_object_id = source.requester_object_id
            new_ticket.guest_name = source.guest_name
            new_ticket.guest_email = source.guest_email

            # Apply optional overrides
            if data.get("department_id"):
                new_ticket.department_id = data["department_id"]
            elif source.department_id:
                new_ticket.department_id = source.department_id

            if data.get("assigned_to_id"):
                new_ticket.assigned_to_id = data["assigned_to_id"]

            new_ticket.save()

            # Copy tags from source
            if source.tags.exists():
                new_ticket.tags.set(source.tags.all())

            # Link source and new ticket
            TicketLink.objects.create(
                parent_ticket=source,
                child_ticket=new_ticket,
                link_type=TicketLink.LinkType.RELATED,
            )

            # System note on source
            Reply.objects.create(
                ticket=source,
                body=f"Reply was split into new ticket {new_ticket.reference}.",
                is_internal_note=True,
                is_pinned=False,
                metadata={
                    "system_note": True,
                    "split_target": new_ticket.reference,
                    "split_by": split_by_user_id,
                },
            )

            # System note on new ticket
            Reply.objects.create(
                ticket=new_ticket,
                body=f"This ticket was split from {source.reference}.",
                is_internal_note=True,
                is_pinned=False,
                metadata={
                    "system_note": True,
                    "split_source": source.reference,
                    "split_by": split_by_user_id,
                },
            )

            # Activity on source
            causer_ct = None
            causer_oid = None
            if split_by_user_id:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                causer_ct = ContentType.objects.get_for_model(User)
                causer_oid = split_by_user_id

            TicketActivity.objects.create(
                ticket=source,
                causer_content_type=causer_ct,
                causer_object_id=causer_oid,
                type=TicketActivity.ActivityType.CREATED,
                properties={
                    "action": "split",
                    "new_ticket_reference": new_ticket.reference,
                },
            )

            # Activity on new ticket
            TicketActivity.objects.create(
                ticket=new_ticket,
                causer_content_type=causer_ct,
                causer_object_id=causer_oid,
                type=TicketActivity.ActivityType.CREATED,
                properties={
                    "action": "split_from",
                    "source_ticket_reference": source.reference,
                },
            )

            return new_ticket
