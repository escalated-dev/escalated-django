"""
Abstract base class for import adapters.

Plugin authors must subclass ``ImportAdapter`` and register their instance
via the ``import.adapters`` filter hook::

    from escalated.hooks import add_filter
    from escalated.contracts.import_adapter import ImportAdapter
    from escalated.support.extract_result import ExtractResult

    class ZendeskAdapter(ImportAdapter):
        def name(self) -> str:
            return "zendesk"

        def display_name(self) -> str:
            return "Zendesk"

        # ... implement remaining abstract methods ...

    add_filter("import.adapters", lambda adapters: adapters + [ZendeskAdapter()])
"""

from abc import ABC, abstractmethod
from typing import Optional

from escalated.support.extract_result import ExtractResult


class ImportAdapter(ABC):
    """Interface every platform-specific import adapter must implement."""

    @abstractmethod
    def name(self) -> str:
        """Unique machine slug, e.g. ``"zendesk"``."""

    @abstractmethod
    def display_name(self) -> str:
        """Human-readable label, e.g. ``"Zendesk"``."""

    @abstractmethod
    def credential_fields(self) -> list[dict]:
        """
        Describe the credentials this adapter needs.

        Each element is a dict with keys:
        ``name``, ``label``, ``type`` (``"text"``, ``"password"``, ``"url"``),
        ``help`` (optional).
        """

    @abstractmethod
    def test_connection(self, credentials: dict) -> bool:
        """Validate credentials by making a test API call."""

    @abstractmethod
    def entity_types(self) -> list[str]:
        """
        Ordered list of importable entity types.

        The order matters: entities that reference others (e.g. tickets
        referencing contacts) must come *after* their dependencies.
        Example: ``["agents", "tags", "contacts", "tickets", "replies"]``
        """

    @abstractmethod
    def default_field_mappings(self, entity_type: str) -> dict:
        """Default source-to-Escalated field mappings for *entity_type*."""

    @abstractmethod
    def available_source_fields(self, entity_type: str, credentials: dict) -> list[str]:
        """
        Fetch the list of field names available in the source for *entity_type*.

        Used to populate the mapping UI.  May make a live API call.
        """

    @abstractmethod
    def extract(self, entity_type: str, credentials: dict, cursor: Optional[str]) -> ExtractResult:
        """
        Fetch one page of records for *entity_type*.

        Args:
            entity_type: One of the values returned by :meth:`entity_types`.
            credentials: The decrypted credentials dict from the ImportJob.
            cursor:      Pagination cursor from the previous call, or
                         ``None`` for the first page.

        Returns:
            An :class:`~escalated.support.extract_result.ExtractResult`.
            Return ``cursor=None`` to signal exhaustion.
        """

    # ------------------------------------------------------------------
    # Optional hook — adapters that need to cross-reference already-
    # imported IDs (e.g. to link replies to tickets) can store the
    # active job ID here.
    # ------------------------------------------------------------------

    def set_job_id(self, job_id: str) -> None:
        """Store the active ImportJob UUID for cross-referencing.  Optional."""
        self._job_id: Optional[str] = job_id

    def get_job_id(self) -> Optional[str]:
        """Return the stored job UUID, or ``None`` if not set."""
        return getattr(self, "_job_id", None)
