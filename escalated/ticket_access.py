"""Request-local ticket access, with explicit contexts for host integrations."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import models
from django.http import JsonResponse
from django.urls import path as django_path
from django.utils.module_loading import import_string

from escalated.conf import get_setting

_actor = ContextVar("escalated_ticket_actor", default=None)


@contextmanager
def ticket_access(actor):
    """Scope queries to a user (or request); None is for trusted background work."""
    token = _actor.set(actor)
    try:
        yield
    finally:
        _actor.reset(token)


def current_actor():
    actor = _actor.get()
    return getattr(actor, "user", actor)


def account_options():
    return {"ENABLED": False, "SCOPE_AGENTS": False, "RESOLVER": None, **(get_setting("ACCOUNTS") or {})}


def validate_options():
    if get_setting("VISIBILITY") not in ("all", "department"):
        raise ImproperlyConfigured("ESCALATED VISIBILITY must be all or department.")
    options = account_options()
    if options["SCOPE_AGENTS"] and (not options["ENABLED"] or not options["RESOLVER"]):
        raise ImproperlyConfigured("Account visibility requires ENABLED and a RESOLVER.")
    if get_setting("MODE") in ("cloud", "hosted") and (
        get_setting("VISIBILITY") != "all" or options["ENABLED"] or get_setting("SLA").get("TARGETED")
    ):
        raise ImproperlyConfigured("Local ticket access and SLA targets are unavailable in cloud-only mode.")


def is_restricted(user):
    from escalated.permissions import is_admin, is_agent

    validate_options()
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and not is_admin(user)
        and (get_setting("VISIBILITY") == "department" or account_options()["SCOPE_AGENTS"])
        and is_agent(user)
    )


def resolve_account(model):
    options = account_options()
    if model is None or not options["ENABLED"]:
        return None
    resolver = options["RESOLVER"]
    if isinstance(resolver, str):
        resolver = import_string(resolver)
    if resolver is None:
        return None
    account = resolver(model)
    if account is not None and (not isinstance(account, models.Model) or account.pk is None or account._state.adding):
        raise ValidationError("The account resolver must return a persisted model or None.")
    return account


def account_identity(model):
    if model is None:
        return None
    return {"type": model._meta.concrete_model._meta.label, "id": str(model.pk)}


def normalize_account(value):
    if not isinstance(value, dict) or not isinstance(value.get("type"), str) or not value["type"]:
        raise ValidationError("An account condition requires type and id.")
    if isinstance(value.get("id"), bool) or not isinstance(value.get("id"), (str, int)) or str(value["id"]) == "":
        raise ValidationError("An account condition requires type and id.")
    return {"type": value["type"], "id": str(value["id"])}


def scope_tickets(queryset, user=None):
    from escalated.models import Department

    user = current_actor() if user is None else user
    if not is_restricted(user):
        return queryset
    if get_setting("VISIBILITY") == "department":
        # Read the package's pivot directly; never join a host user database.
        relation = Department._meta.get_field("agents")
        departments = Department.agents.through.objects.filter(
            **{relation.m2m_reverse_field_name() + "_id": user.pk}
        ).values(relation.m2m_field_name() + "_id")
        queryset = queryset.filter(department_id__in=departments)
    if account_options()["SCOPE_AGENTS"]:
        account = account_identity(resolve_account(user))
        if account is None:
            return queryset.none()
        queryset = queryset.filter(account_type=account["type"], account_id=account["id"])
    return queryset


def allows_ticket(user, ticket):
    if not is_restricted(user):
        return True
    from escalated.models import Ticket

    return scope_tickets(Ticket.unrestricted.all(), user).filter(pk=ticket.pk).exists()


def can_access_channel(user, channel):
    """Authorize subscriptions; restricted agents cannot join shared channels."""
    from escalated.models import Ticket
    from escalated.permissions import can_view_ticket, is_admin, is_agent

    if channel.startswith("ticket."):
        identifier = channel.removeprefix("ticket.")
        if not identifier.isdigit():
            return False
        ticket = Ticket.unrestricted.filter(pk=identifier).first()
        return ticket is not None and can_view_ticket(user, ticket)
    return (is_admin(user) or is_agent(user)) and not is_restricted(user)


def can_access_chat(user, session_id, guest_session=None):
    """Recheck membership for each WebSocket delivery when restrictions are enabled."""
    from escalated.chat_tokens import find_session
    from escalated.models import ChatSession
    from escalated.permissions import can_view_ticket

    if get_setting("VISIBILITY") == "all" and not account_options()["SCOPE_AGENTS"]:
        return True
    with ticket_access(None):
        session = ChatSession.objects.select_related("ticket").filter(pk=session_id).first()
    if session is None:
        return False
    if user and getattr(user, "is_authenticated", False):
        return can_view_ticket(user, session.ticket)
    if not guest_session:
        return False
    with ticket_access(None):
        return find_session(str(guest_session), ChatSession.objects.filter(pk=session.pk)) is not None


class TicketChildManager(models.Manager):
    def get_queryset(self):
        return scope_ticket_children(super().get_queryset())


def scope_ticket_children(queryset, *fields):
    if not is_restricted(current_actor()):
        return queryset
    from escalated.models import Ticket

    for field in fields or ("ticket_id",):
        queryset = queryset.filter(**{field + "__in": Ticket.objects.values("pk")})
    return queryset


class TicketLinkManager(models.Manager):
    def get_queryset(self):
        return scope_ticket_children(super().get_queryset(), "parent_ticket_id", "child_ticket_id")


def filter_accounts(queryset, params):
    if not account_options()["ENABLED"] or not ({"account_type", "account_id"} & params.keys()):
        return queryset
    identity = normalize_account({"type": params.get("account_type"), "id": params.get("account_id")})
    return queryset.filter(account_type=identity["type"], account_id=identity["id"])


def serialize_account(ticket):
    if not account_options()["ENABLED"]:
        return {}
    return {"account_type": ticket.account_type, "account_id": ticket.account_id}


def eligible_agents(agents, ticket):
    if get_setting("VISIBILITY") == "all" and not account_options()["SCOPE_AGENTS"]:
        return agents
    return agents.filter(pk__in=[agent.pk for agent in agents if allows_ticket(agent, ticket)])


def sla_targets(params):
    from escalated.models import Department, Ticket

    targets = {}
    if "department_id" in params:
        value = params.get("department_id") or None
        try:
            value = int(value) if value is not None else None
        except (ValueError, TypeError) as error:
            raise ValidationError("Invalid SLA department.") from error
        if value is not None and not Department.objects.filter(pk=value).exists():
            raise ValidationError("Invalid SLA department.")
        targets["department_id"] = value
    if "ticket_type" in params:
        value = params.get("ticket_type") or None
        if value is not None and value not in Ticket.TicketType.values:
            raise ValidationError("Invalid SLA ticket type.")
        targets["ticket_type"] = value
    return targets


def ticket_access_view(view):
    @wraps(view)
    def scoped(request, *args, **kwargs):
        with ticket_access(request):
            validate_options()
            try:
                response = view(request, *args, **kwargs)
            except ValidationError as error:
                return JsonResponse({"errors": error.messages}, status=422)
            if getattr(response, "streaming", False):
                content = response.streaming_content

                def stream():
                    with ticket_access(request):
                        yield from content

                response.streaming_content = stream()
            return response

    return scoped


def path(route, view, kwargs=None, name=None):
    """Package routes establish access context without host middleware changes."""
    return django_path(route, ticket_access_view(view) if callable(view) else view, kwargs, name)


class TicketAccessMiddleware:
    """Optional host middleware: install after AuthenticationMiddleware."""

    def __init__(self, get_response):
        self.get_response = ticket_access_view(get_response)

    def __call__(self, request):
        return self.get_response(request)
