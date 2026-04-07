"""
Value object returned by ``ImportAdapter.extract()``.

Carries a page of normalized records, the next cursor (``None`` when the
source is exhausted), and an optional total-count hint for progress display.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtractResult:
    """
    Immutable result from a single ``extract()`` call on an ImportAdapter.

    Attributes:
        records:     Normalized records as plain dicts.  Each record MUST
                     include a ``source_id`` key.
        cursor:      Opaque pagination token for the *next* page.  Pass
                     ``None`` (or omit) when the source is exhausted.
        total_count: Optional total record count available from the source
                     API.  Used only for progress display — not guaranteed
                     to be accurate.
    """

    records: list = field(default_factory=list)
    cursor: str | None = None
    total_count: int | None = None

    def is_exhausted(self) -> bool:
        """Return True when there are no more pages to fetch."""
        return self.cursor is None
