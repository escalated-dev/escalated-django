from escalated.permissions import (
    is_admin,
    is_agent,
    can_view_ticket,
    can_update_ticket,
    can_reply_ticket,
    can_add_note,
    can_close_ticket,
)


class TicketPolicy:
    @staticmethod
    def view(user, ticket):
        return can_view_ticket(user, ticket)

    @staticmethod
    def create(user):
        if not user or not user.is_authenticated:
            return False
        return True

    @staticmethod
    def update(user, ticket):
        return can_update_ticket(user, ticket)

    @staticmethod
    def delete(user, ticket):
        return is_admin(user)

    @staticmethod
    def reply(user, ticket):
        return can_reply_ticket(user, ticket)

    @staticmethod
    def add_note(user, ticket):
        return can_add_note(user, ticket)

    @staticmethod
    def close(user, ticket):
        return can_close_ticket(user, ticket)

    @staticmethod
    def assign(user, ticket):
        if not user or not user.is_authenticated:
            return False
        return is_admin(user) or is_agent(user)
