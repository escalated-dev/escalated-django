from django.contrib.contenttypes.models import ContentType

from escalated.models import Department


def is_agent(user):
    """
    Check if a user is a support agent. An agent is a user who belongs
    to at least one active department.
    """
    if not user or not user.is_authenticated:
        return False
    return Department.objects.filter(
        agents=user, is_active=True
    ).exists()


def is_admin(user):
    """
    Check if a user has admin-level support privileges.
    Admins are Django staff users or superusers.
    """
    if not user or not user.is_authenticated:
        return False
    return user.is_staff or user.is_superuser


def can_view_ticket(user, ticket):
    """
    Check if a user can view a ticket. Users can view if they are:
    - The requester
    - The assigned agent
    - An agent in the ticket's department
    - A support admin
    """
    if not user or not user.is_authenticated:
        return False

    if is_admin(user):
        return True

    # Check if user is the requester
    ct = ContentType.objects.get_for_model(user)
    if (
        ticket.requester_content_type == ct
        and ticket.requester_object_id == user.pk
    ):
        return True

    # Check if user is the assigned agent
    if ticket.assigned_to == user:
        return True

    # Check if user is an agent in the ticket's department
    if ticket.department and ticket.department.agents.filter(pk=user.pk).exists():
        return True

    # Check if user is an agent in any department (can see all tickets)
    if is_agent(user):
        return True

    return False


def can_update_ticket(user, ticket):
    """
    Check if a user can update a ticket. Only agents, assigned users,
    and admins can update.
    """
    if not user or not user.is_authenticated:
        return False

    if is_admin(user):
        return True

    if ticket.assigned_to == user:
        return True

    if is_agent(user):
        return True

    return False


def can_reply_ticket(user, ticket):
    """
    Check if a user can reply to a ticket. The requester, assigned agent,
    department agents, and admins can reply.
    """
    if not user or not user.is_authenticated:
        return False

    if is_admin(user):
        return True

    # Requester can reply
    ct = ContentType.objects.get_for_model(user)
    if (
        ticket.requester_content_type == ct
        and ticket.requester_object_id == user.pk
    ):
        return True

    if is_agent(user):
        return True

    return False


def can_add_note(user, ticket):
    """
    Check if a user can add an internal note. Only agents and admins.
    """
    if not user or not user.is_authenticated:
        return False

    return is_admin(user) or is_agent(user)


def can_close_ticket(user, ticket):
    """
    Check if a user can close a ticket. Agents and admins always can.
    Customers can close only if ALLOW_CUSTOMER_CLOSE is True.
    """
    if not user or not user.is_authenticated:
        return False

    if is_admin(user) or is_agent(user):
        return True

    from escalated.conf import get_setting

    if get_setting("ALLOW_CUSTOMER_CLOSE"):
        ct = ContentType.objects.get_for_model(user)
        if (
            ticket.requester_content_type == ct
            and ticket.requester_object_id == user.pk
        ):
            return True

    return False
