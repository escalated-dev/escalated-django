"""Contract for host-app models attachable as ticket subjects."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TicketSubjectProtocol(Protocol):
    """Presentation contract for entities a ticket is *about*."""

    def ticket_subject_title(self) -> str: ...

    def ticket_subject_subtitle(self) -> str | None: ...

    def ticket_subject_url(self) -> str | None: ...

    def ticket_subject_color(self) -> str | None: ...

    def ticket_subject_icon(self) -> str | None: ...


class TicketSubjectMixin:
    """
    Default presentation for ticket subjects.

    Override any method on the host model; title falls back to ``name``,
    ``title``, or ``label`` attributes.
    """

    def ticket_subject_title(self) -> str:
        for attribute in ("name", "title", "label"):
            value = getattr(self, attribute, None)
            if isinstance(value, str) and value:
                return value
        return str(self.pk)

    def ticket_subject_subtitle(self) -> str | None:
        return None

    def ticket_subject_url(self) -> str | None:
        return None

    def ticket_subject_color(self) -> str | None:
        return None

    def ticket_subject_icon(self) -> str | None:
        return None
