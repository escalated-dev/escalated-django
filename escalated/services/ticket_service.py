from escalated.drivers import get_driver
from escalated.conf import get_setting


class TicketService:
    """
    High-level service for ticket operations. Delegates to the configured
    driver (local, synced, or cloud).
    """

    def __init__(self):
        self.driver = get_driver()

    def create(self, user, data):
        """
        Create a new ticket.

        Args:
            user: The requesting user
            data: dict with subject, description, priority, channel,
                  department_id, tag_ids, metadata
        Returns:
            Ticket instance (local/synced) or dict (cloud)
        """
        if "priority" not in data:
            data["priority"] = get_setting("DEFAULT_PRIORITY")

        return self.driver.create_ticket(user, data)

    def update(self, ticket, user, data):
        """Update ticket fields (subject, description, metadata)."""
        return self.driver.update_ticket(ticket, user, data)

    def change_status(self, ticket, user, new_status):
        """Transition ticket to a new status."""
        return self.driver.transition_status(ticket, user, new_status)

    def assign(self, ticket, user, agent):
        """Assign ticket to an agent."""
        return self.driver.assign_ticket(ticket, user, agent)

    def unassign(self, ticket, user):
        """Remove agent assignment."""
        return self.driver.unassign_ticket(ticket, user)

    def reply(self, ticket, user, data):
        """Add a reply to a ticket."""
        return self.driver.add_reply(ticket, user, data)

    def add_note(self, ticket, user, body):
        """Add an internal note to a ticket."""
        return self.driver.add_reply(ticket, user, {
            "body": body,
            "is_internal_note": True,
        })

    def get(self, ticket_id):
        """Retrieve a ticket by ID."""
        return self.driver.get_ticket(ticket_id)

    def list(self, filters=None):
        """List tickets with optional filters."""
        return self.driver.list_tickets(filters)

    def add_tags(self, ticket, user, tag_ids):
        """Add tags to a ticket."""
        return self.driver.add_tags(ticket, user, tag_ids)

    def remove_tags(self, ticket, user, tag_ids):
        """Remove tags from a ticket."""
        return self.driver.remove_tags(ticket, user, tag_ids)

    def change_department(self, ticket, user, department):
        """Move ticket to a different department."""
        return self.driver.change_department(ticket, user, department)

    def change_priority(self, ticket, user, new_priority):
        """Change ticket priority."""
        return self.driver.change_priority(ticket, user, new_priority)

    def close(self, ticket, user):
        """Close a ticket."""
        from escalated.models import Ticket
        return self.driver.transition_status(ticket, user, Ticket.Status.CLOSED)

    def resolve(self, ticket, user):
        """Resolve a ticket."""
        from escalated.models import Ticket
        return self.driver.transition_status(ticket, user, Ticket.Status.RESOLVED)

    def reopen(self, ticket, user):
        """Reopen a closed or resolved ticket."""
        from escalated.models import Ticket
        return self.driver.transition_status(ticket, user, Ticket.Status.REOPENED)

    def escalate(self, ticket, user):
        """Escalate a ticket."""
        from escalated.models import Ticket
        return self.driver.transition_status(ticket, user, Ticket.Status.ESCALATED)
