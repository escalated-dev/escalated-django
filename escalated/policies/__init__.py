"""
Policy-based authorization for Escalated views.

Policies wrap the low-level permission functions from escalated.permissions
into a structured, decorator-friendly pattern matching Laravel's policy classes.
"""

import functools

from django.http import JsonResponse


class PolicyDenied(Exception):
    pass


def check_policy(policy_class, action, obj_arg=None, lookup_model=None, lookup_field="pk"):
    """
    View decorator that resolves an object and checks a policy method.

    Usage:
        @check_policy(TicketPolicy, 'update', obj_arg='reference',
                       lookup_model=Ticket, lookup_field='reference')
        def ticket_update(request, reference):
            ticket = request.policy_object
            ...

    If obj_arg is None, calls the policy method with just (user,).
    Otherwise resolves the object and calls with (user, obj).
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            obj = None
            if obj_arg and lookup_model:
                lookup_value = kwargs.get(obj_arg)
                if lookup_value is None and args:
                    lookup_value = args[0]
                try:
                    obj = lookup_model.objects.get(**{lookup_field: lookup_value})
                except lookup_model.DoesNotExist:
                    return JsonResponse({"message": "Not found."}, status=404)

            method = getattr(policy_class, action)
            allowed = method(request.user, obj) if obj is not None else method(request.user)
            if not allowed:
                return JsonResponse({"message": "Forbidden."}, status=403)

            if obj is not None:
                request.policy_object = obj
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
