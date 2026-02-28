from django.db import transaction


class TicketMergeService:
    """Service for merging one ticket into another."""

    def merge(self, source, target, merged_by_user_id=None):
        """
        Merge source ticket into target ticket.

        Moves all replies from source to target, adds system notes on both
        tickets, closes the source, and sets its merged_into reference.

        Args:
            source: The ticket being merged (will be closed).
            target: The ticket that absorbs the source.
            merged_by_user_id: Optional ID of the user performing the merge.
        """
        with transaction.atomic():
            from escalated.models import Reply, Ticket

            # Move all replies from source to target
            Reply.objects.filter(ticket=source).update(ticket=target)

            # System note on target
            Reply.objects.create(
                ticket=target,
                body=f"Ticket {source.reference} was merged into this ticket.",
                is_internal_note=True,
                is_pinned=False,
                metadata={
                    "system_note": True,
                    "merge_source": source.reference,
                    "merged_by": merged_by_user_id,
                },
            )

            # System note on source
            Reply.objects.create(
                ticket=source,
                body=f"This ticket was merged into {target.reference}.",
                is_internal_note=True,
                is_pinned=False,
                metadata={
                    "system_note": True,
                    "merge_target": target.reference,
                    "merged_by": merged_by_user_id,
                },
            )

            # Close source and set merged_into
            source.status = Ticket.Status.CLOSED
            source.merged_into = target
            source.save()
