import logging

from django.contrib.auth import get_user_model

from escalated.models import Macro, Ticket, Tag, Department

logger = logging.getLogger("escalated")

User = get_user_model()


class MacroService:
    """
    Applies a macro (sequence of actions) to a ticket.
    """

    def __init__(self):
        from escalated.services.ticket_service import TicketService
        self.ticket_service = TicketService()

    def apply(self, macro: Macro, ticket: Ticket, user) -> Ticket:
        """
        Apply all actions in a macro sequentially to a ticket.

        Args:
            macro: The Macro instance to apply.
            ticket: The Ticket to apply actions to.
            user: The user performing the action (causer).

        Returns:
            The updated Ticket instance.
        """
        for action in macro.actions:
            action_type = action.get("type")
            value = action.get("value")

            try:
                if action_type == "set_status" or action_type == "status":
                    self.ticket_service.change_status(ticket, user, value)
                elif action_type == "set_priority" or action_type == "priority":
                    self.ticket_service.change_priority(ticket, user, value)
                elif action_type == "assign":
                    try:
                        agent = User.objects.get(pk=int(value))
                        self.ticket_service.assign(ticket, user, agent)
                    except User.DoesNotExist:
                        logger.warning(
                            f"Macro action 'assign' skipped: user {value} not found"
                        )
                elif action_type == "add_note" or action_type == "note":
                    if value:
                        self.ticket_service.add_note(ticket, user, str(value))
                elif action_type == "add_tags" or action_type == "tags":
                    tag_ids = value if isinstance(value, list) else [value]
                    self.ticket_service.add_tags(
                        ticket, user, [int(t) for t in tag_ids]
                    )
                elif action_type == "send_reply" or action_type == "reply":
                    if value:
                        self.ticket_service.reply(
                            ticket, user, {"body": str(value)}
                        )
                elif action_type == "department":
                    try:
                        dept = Department.objects.get(pk=int(value))
                        self.ticket_service.change_department(ticket, user, dept)
                    except Department.DoesNotExist:
                        logger.warning(
                            f"Macro action 'department' skipped: department {value} not found"
                        )
                else:
                    logger.warning(
                        f"Unknown macro action type: {action_type}"
                    )
            except Exception as e:
                logger.error(
                    f"Macro action '{action_type}' failed on ticket "
                    f"{ticket.reference}: {e}"
                )

            # Refresh ticket from DB after each action
            ticket.refresh_from_db()

        return ticket
