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

    def update_ticket(self, ticket_id, user, data):
        return self.api.update_ticket(ticket_id, data)

    def transition_status(self, ticket_id, user, new_status):
        return self.api.transition_status(ticket_id, new_status)

    def assign_ticket(self, ticket_id, user, agent_id):
        return self.api.assign_ticket(ticket_id, agent_id)

    def unassign_ticket(self, ticket_id, user):
        return self.api.unassign_ticket(ticket_id)

    def add_reply(self, ticket_id, user, data):
        payload = {
            "body": data["body"],
            "is_internal_note": data.get("is_internal_note", False),
            "author_id": user.pk,
            "author_name": getattr(
                user, "get_full_name", lambda: str(user)
            )(),
            "metadata": data.get("metadata"),
        }
        return self.api.add_reply(ticket_id, payload)

    def get_ticket(self, ticket_id):
        return self.api.get_ticket(ticket_id)

    def list_tickets(self, filters=None):
        return self.api.list_tickets(params=filters)

    def add_tags(self, ticket_id, user, tag_ids):
        return self.api.add_tags(ticket_id, tag_ids)

    def remove_tags(self, ticket_id, user, tag_ids):
        return self.api.remove_tags(ticket_id, tag_ids)

    def change_department(self, ticket_id, user, department_id):
        return self.api.change_department(ticket_id, department_id)

    def change_priority(self, ticket_id, user, new_priority):
        return self.api.change_priority(ticket_id, new_priority)
