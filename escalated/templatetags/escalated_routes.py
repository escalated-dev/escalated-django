"""``{% load escalated_routes %}{% escalated_route_helper %}`` in the host's Inertia layout."""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from escalated.route_list import ROUTE_HELPER

register = template.Library()


@register.simple_tag
def escalated_route_helper(nonce=None):
    """
    A ``<script>`` installing ``window.route()`` for the shared pages, reading
    the ``ziggy`` prop Escalated shares. Does nothing if the host already has a
    ``route()`` (e.g. ziggy-js); ``window.Ziggy`` wins over the prop.
    """
    if nonce:
        return format_html('<script nonce="{}">{}</script>', nonce, mark_safe(ROUTE_HELPER))
    return mark_safe(f"<script>{ROUTE_HELPER}</script>")
