import functools

from django.contrib.auth.views import redirect_to_login
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseForbidden
from django.utils.translation import gettext as _

from escalated.models import Department
from escalated.ticket_access import allows_ticket

# The attributes Escalated reads from the host's user to decide who is a
# support admin (the admin gate). AbstractUser has both; AbstractBaseUser has
# neither, and PermissionsMixin adds only is_superuser.
ADMIN_GATE_ATTRIBUTES = ("is_staff", "is_superuser")


class UserModelNotSupported(ImproperlyConfigured):
    """The host's user model lacks what Escalated's staff gates read."""


def user_model_problem(model):
    """Why ``model`` (a user model, or a user) cannot pass Escalated's admin gate, or ``None`` when it can."""
    if any(hasattr(model, attribute) for attribute in ADMIN_GATE_ATTRIBUTES):
        return None
    label = getattr(getattr(model, "_meta", None), "label", None)
    if not label:
        label = model.__name__ if isinstance(model, type) else type(model).__name__
    return (
        f"Escalated cannot tell whether a {label} is a support admin: the user model has neither "
        "is_staff nor is_superuser. Escalated's admin gate reads these, as "
        "django.contrib.auth.models.AbstractUser provides them. Subclass AbstractUser, or add "
        "PermissionsMixin (is_superuser) and an is_staff field or property to the model. Agents are "
        "the users in an active Department's agents. See docs/access-control.md."
    )


def is_agent(user):
    """
    Check if a user is a support agent. An agent is a user who belongs
    to at least one active department.
    """
    if not user or not user.is_authenticated:
        return False
    return Department.objects.filter(agents=user, is_active=True).exists()


def is_admin(user):
    """
    Check if a user has admin-level support privileges.
    Admins are Django staff users or superusers.
    """
    if not user or not user.is_authenticated:
        return False
    problem = user_model_problem(user)
    if problem:
        raise UserModelNotSupported(problem)
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def staff_only(view):
    """
    A customer-route guard for staff-only installs
    (``ESCALATED["CUSTOMER_ROUTE_DECORATORS"] = ["escalated.permissions.staff_only"]``):
    visitors who are not signed in go to the login page, and signed-in users
    who are neither agents nor admins get 403.
    """

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (is_agent(user) or is_admin(user)):
            return HttpResponseForbidden(_("Support staff only."))
        return view(request, *args, **kwargs)

    return wrapper


def admin_gate_replaced(request) -> bool:
    """
    Whether the host replaced Escalated's admin gate for this request: only on
    an embedded admin view, only with ``ESCALATED["EMBED"]["REPLACE_ADMIN_GATE"]``
    (ADR 2026-11-05-embeddable-admin), and only for a signed-in user. The
    host's view decorators already decided who may reach the view.
    """
    user = getattr(request, "user", None)
    if not getattr(request, "escalated_embedded", False) or not user or not user.is_authenticated:
        return False
    from escalated import embed

    return embed.enabled() and embed.replaces_admin_gate()


def passes_admin_gate(request) -> bool:
    """Escalated's admin gate for the admin views: is_admin(), unless the host replaced it."""
    return is_admin(getattr(request, "user", None)) or admin_gate_replaced(request)


def user_permissions(user):
    """Return the permission slugs granted to the user via their roles ([] if none/unauth)."""
    if not user or not user.is_authenticated:
        return []
    try:
        from escalated.models import Permission

        return list(Permission.objects.filter(roles__users=user).values_list("slug", flat=True).distinct())
    except Exception:
        return []


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

    if not allows_ticket(user, ticket):
        return False

    if is_admin(user):
        return True

    # Check if user is the requester
    ct = ContentType.objects.get_for_model(user)
    if ticket.requester_content_type == ct and str(ticket.requester_object_id) == str(user.pk):
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

    if not allows_ticket(user, ticket):
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

    if not allows_ticket(user, ticket):
        return False

    if is_admin(user):
        return True

    # Requester can reply
    ct = ContentType.objects.get_for_model(user)
    if ticket.requester_content_type == ct and str(ticket.requester_object_id) == str(user.pk):
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

    if not allows_ticket(user, ticket):
        return False

    return is_admin(user) or is_agent(user)


def can_close_ticket(user, ticket):
    """
    Check if a user can close a ticket. Agents and admins always can.
    Customers can close only if ALLOW_CUSTOMER_CLOSE is True.
    """
    if not user or not user.is_authenticated:
        return False

    if not allows_ticket(user, ticket):
        return False

    if is_admin(user) or is_agent(user):
        return True

    from escalated.conf import get_setting

    if get_setting("ALLOW_CUSTOMER_CLOSE"):
        ct = ContentType.objects.get_for_model(user)
        if ticket.requester_content_type == ct and str(ticket.requester_object_id) == str(user.pk):
            return True

    return False
