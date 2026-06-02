"""Bounce / complaint suppression store backed by EscalatedSetting JSON."""

from __future__ import annotations

import json
from collections.abc import Iterable

from escalated.models import EscalatedSetting


class BounceSuppressionStore:
    KEY = "newsletter.suppressed_emails"

    def mark_bounced(self, email: str) -> None:
        self._mark(email)

    def mark_complained(self, email: str) -> None:
        self._mark(email)

    def is_bounced(self, email: str) -> bool:
        return email.lower() in self._load()

    def filter_sendable(self, emails: Iterable[str]) -> list[str]:
        suppressed = set(self._load())
        return [e for e in emails if e.lower() not in suppressed]

    def _mark(self, email: str) -> None:
        lower = email.lower()
        current = self._load()
        if lower in current:
            return
        current.append(lower)
        # EscalatedSetting has only key/value columns (no type/group).
        EscalatedSetting.objects.update_or_create(
            key=self.KEY,
            defaults={"value": json.dumps(current)},
        )

    def _load(self) -> list[str]:
        row = EscalatedSetting.objects.filter(key=self.KEY).first()
        if not row or not row.value:
            return []
        try:
            parsed = json.loads(row.value)
        except (ValueError, TypeError):
            return []
        if not isinstance(parsed, list):
            return []
        return [str(e).lower() for e in parsed]
