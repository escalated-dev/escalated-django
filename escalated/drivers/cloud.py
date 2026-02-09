import logging

from escalated.drivers.api_client import HostedApiClient

logger = logging.getLogger("escalated")


class CloudDriver:
    """
    Proxies all operations to the Escalated cloud API.
    No local database is used for ticket storage; the cloud is the
    source of truth.
    """

    def __init__(self):
        self.api = HostedApiClient()

    def create_ticket(self, user, data):
        payload = {
            "subject": data["subject"],
            "description": data["description"],
            "priority": data.get("priority", "medium"),
            "channel": data.get("channel", "web"),
            "department_id": data.get("department_id"),
            "tag_ids": data.get("tag_ids", []),
            "metadata": data.get("metadata"),
            "requester_id": user.pk,
            "requester_email": getattr(user, "email", None),
            "requester_name": getattr(
                user, "get_full_name", lambda: str(user)
            )(),
        }
        return self.api.create_ticket(payload)

    def update_ticket(self, ticket, user, data):
        ticket_id = ticket.pk if hasattr(ticket, "pk") else ticket
        return self.api.update_ticket(ticket_id, data)

    def transition_status(self, ticket, user, new_status):
        ticket_id = ticket.pk if hasattr(ticket, "pk") else ticket
        return self.api.transition_status(ticket_id, new_status)

    def assign_ticket(self, ticket, user, agent):
        ticket_id = ticket.pk if hasattr(ticket, "pk") else ticket
        agent_id = agent.pk if hasattr(agent, "pk") else agent
        return self.api.assign_ticket(ticket_id, agent_id)

    def unassign_ticket(self, ticket, user):
        ticket_id = ticket.pk if hasattr(ticket, "pk") else ticket
        return self.api.unassign_ticket(ticket_id)

    def add_reply(self, ticket, user, data):
        ticket_id = ticket.pk if hasattr(ticket, "pk") else ticket
        payload = {
            "body": data["body"],
            "is_internal_note": data.get("is_internal_note", False),
            "author_id": user.pk if user else None,
            "author_name": getattr(
                user, "get_full_name", lambda: str(user)
            )() if user else "Guest",
            "metadata": data.get("metadata"),
        }
        return self.api.add_reply(ticket_id, payload)

    def get_ticket(self, ticket_id):
        return self.api.get_ticket(ticket_id)

    def list_tickets(self, filters=None):
        return self.api.list_tickets(params=filters)

    def add_tags(self, ticket, user, tag_ids):
        ticket_id = ticket.pk if hasattr(ticket, "pk") else ticket
        return self.api.add_tags(ticket_id, tag_ids)

    def remove_tags(self, ticket, user, tag_ids):
        ticket_id = ticket.pk if hasattr(ticket, "pk") else ticket
        return self.api.remove_tags(ticket_id, tag_ids)

    def change_department(self, ticket, user, department):
        ticket_id = ticket.pk if hasattr(ticket, "pk") else ticket
        department_id = department.pk if hasattr(department, "pk") else department
        return self.api.change_department(ticket_id, department_id)

    def change_priority(self, ticket, user, new_priority):
        ticket_id = ticket.pk if hasattr(ticket, "pk") else ticket
        return self.api.change_priority(ticket_id, new_priority)
