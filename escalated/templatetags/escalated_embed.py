"""``{% load escalated_embed %}``: Escalated's admin menu in a host template."""

from django import template

from escalated.embed import admin_navigation

register = template.Library()


@register.simple_tag(takes_context=True)
def escalated_admin_navigation(context, user=None):
    """
    ``{% escalated_admin_navigation as items %}``: the admin menu for the
    request's user (or ``user``), the list shared as ``escalated.navigation``
    (ADR 2026-11-05-embeddable-admin), for a server-rendered admin layout.
    """
    request = context.get("request")
    return admin_navigation(user, request)
