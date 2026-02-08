import logging

from escalated.drivers.local import LocalDriver
from escalated.drivers.api_client import HostedApiClient, HostedApiError
from escalated.serializers import TicketSerializer, ReplySerializer

logger = logging.getLogger("escalated")


class SyncedDriver(LocalDriver):
    """
    Extends LocalDriver to sync operations to the Escalated cloud API.
    Local operations always succeed; cloud sync failures are logged but
    do not block the local operation.
    """

    def __init__(self):
        super().__init__()
        self.api = HostedApiClient()

    def _emit_safe(self, event_type, payload):
        """Emit an event to the cloud, swallowing errors."""
        try:
            self.api.emit(event_type, payload)
        except HostedApiError as e:
            logger.error(
                f"Failed to sync event '{event_type}' to cloud: {e}. "
                f"Local operation succeeded."
            )
        except Exception as e:
            logger.error(f"Unexpected error syncing '{event_type}': {e}")

    def create_ticket(self, user, data):
        ticket = super().create_ticket(user, data)
        self._emit_safe("ticket.created", {
            "ticket": TicketSerializer.serialize(ticket),
            "user_id": user.pk,
        })
        return ticket

    def update_ticket(self, ticket, user, data):
        ticket = super().update_ticket(ticket, user, data)
        self._emit_safe("ticket.updated", {
            "ticket": TicketSerializer.serialize(ticket),
            "user_id": user.pk,
            "changes": data,
        })
        return ticket

    def transition_status(self, ticket, user, new_status):
        old_status = ticket.status
        ticket = super().transition_status(ticket, user, new_status)
        self._emit_safe("ticket.status_changed", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "old_status": old_status,
            "new_status": new_status,
            "user_id": user.pk,
        })
        return ticket

    def assign_ticket(self, ticket, user, agent):
        ticket = super().assign_ticket(ticket, user, agent)
        self._emit_safe("ticket.assigned", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "agent_id": agent.pk,
            "user_id": user.pk,
        })
        return ticket

    def unassign_ticket(self, ticket, user):
        ticket = super().unassign_ticket(ticket, user)
        self._emit_safe("ticket.unassigned", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "user_id": user.pk,
        })
        return ticket

    def add_reply(self, ticket, user, data):
        reply = super().add_reply(ticket, user, data)
        self._emit_safe("reply.created", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "reply": ReplySerializer.serialize(reply),
            "user_id": user.pk,
        })
        return reply

    def add_tags(self, ticket, user, tag_ids):
        super().add_tags(ticket, user, tag_ids)
        self._emit_safe("ticket.tags_added", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "tag_ids": tag_ids,
            "user_id": user.pk,
        })

    def remove_tags(self, ticket, user, tag_ids):
        super().remove_tags(ticket, user, tag_ids)
        self._emit_safe("ticket.tags_removed", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "tag_ids": tag_ids,
            "user_id": user.pk,
        })

    def change_department(self, ticket, user, department):
        ticket = super().change_department(ticket, user, department)
        self._emit_safe("ticket.department_changed", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "department_id": department.pk,
            "user_id": user.pk,
        })
        return ticket

    def change_priority(self, ticket, user, new_priority):
        ticket = super().change_priority(ticket, user, new_priority)
        self._emit_safe("ticket.priority_changed", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "priority": new_priority,
            "user_id": user.pk,
        })
        return ticket
