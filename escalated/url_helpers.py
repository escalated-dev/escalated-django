"""URL pieces that let the shared frontend's links land on the right views."""

from functools import wraps

from django.urls import register_converter
from django.urls.converters import get_converters


class TicketConverter:
    """
    A ticket in a URL, by reference (as the shared pages link it) or by id.

    The pages call ``route('escalated.agent.tickets.show', ticket.reference)``,
    as escalated-laravel resolves tickets by reference. Views keep receiving the
    ticket's primary key, so ``/tickets/ESC-A1B2C3/`` and ``/tickets/42/`` reach
    the same view with the same argument. An unknown reference does not match,
    which Django answers with a 404.
    """

    regex = r"[0-9]+|[A-Za-z0-9][A-Za-z0-9_-]*"

    def to_python(self, value):
        if value.isdigit():
            return int(value)
        from escalated.models import Ticket

        pk = Ticket.unrestricted.filter(reference=value).values_list("pk", flat=True).first()
        if pk is None:
            raise ValueError(f"no ticket with reference {value!r}")
        return pk

    def to_url(self, value):
        return str(value)


# Registered here, not in escalated.urls: that module is re-imported when the
# URLconf is reloaded, and Django 5.1+ refuses a second registration.
if "esc_ticket" not in get_converters():
    register_converter(TicketConverter, "esc_ticket")


def accept_verbs(view, *verbs):
    """
    Let a view written for form POSTs take the verbs the shared pages send.

    The pages update with ``form.put(...)`` and delete with ``router.delete(...)``,
    as Laravel's resource routes expect. These views branch on
    ``request.method == "POST"``, so a PUT rendered the edit page and saved
    nothing, and a DELETE was refused. The listed verbs are handled as a POST.
    """

    @wraps(view)
    def accepting(request, *args, **kwargs):
        if request.method in verbs:
            request.method = "POST"
        return view(request, *args, **kwargs)

    accepting.escalated_accepts = tuple(verbs)
    return accepting


def put(view):
    return accept_verbs(view, "PUT", "PATCH")


def delete(view):
    return accept_verbs(view, "DELETE")
