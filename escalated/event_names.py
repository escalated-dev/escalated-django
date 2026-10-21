"""
The shared event vocabulary (escalated-developer-context ADR 2026-10-21,
"One event vocabulary for webhooks and workflow triggers").

Outbound webhooks and workflow triggers use the canonical names only. Names
earlier releases stored (a webhook's ``events``, a workflow's
``trigger_event``) are read as aliases of the canonical name and are never
emitted or offered in a form.
"""

CANONICAL_EVENTS = (
    "ticket.created",
    "ticket.updated",
    "ticket.status_changed",
    "ticket.resolved",
    "ticket.closed",
    "ticket.reopened",
    "ticket.assigned",
    "ticket.unassigned",
    "ticket.escalated",
    "ticket.priority_changed",
    "ticket.department_changed",
    "ticket.tag_added",
    "ticket.tag_removed",
    "reply.created",
    "note.created",
    "sla.warning",
    "sla.breached",
    "chat.started",
    "chat.assigned",
    "chat.transferred",
    "chat.message",
    "chat.ended",
)

LEGACY_EVENT_NAMES = {
    "ticket.replied": "reply.created",
    "internal_note.added": "note.created",
    "internal_note.created": "note.created",
    "tag.added": "ticket.tag_added",
    "ticket.tagged": "ticket.tag_added",
    "tag.removed": "ticket.tag_removed",
    "ticket.untagged": "ticket.tag_removed",
    "chat.session_started": "chat.started",
    "chat.session_ended": "chat.ended",
}


def canonical_event(name):
    """The canonical name for ``name``; unknown names pass through unchanged."""
    return LEGACY_EVENT_NAMES.get(name, name)


def canonical_events(names):
    """``names`` translated to canonical names, de-duplicated, order kept."""
    result = []
    for name in names or []:
        if not isinstance(name, str):
            continue
        name = canonical_event(name)
        if name not in result:
            result.append(name)
    return result


def aliases_of(name):
    """``name`` plus every legacy name that reads as it."""
    return [name] + [legacy for legacy, canonical in LEGACY_EVENT_NAMES.items() if canonical == name]
