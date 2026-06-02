"""Regression tests for ContactSegmentResolver dynamic-list filtering.

Covers the bugs found in the 2026-05-29 newsletter review:
- metadata filtering used `metadata__contains`, which raises NotSupportedError
  on SQLite; it now uses a JSON key transform.
- `!=` mapped to a nonexistent `__ne` lookup (FieldError); it now uses exclude().
- arbitrary `field` values are skipped instead of raising FieldError.
"""

import pytest

from escalated.models import Contact
from escalated.services.newsletter.contact_segment_resolver import ContactSegmentResolver


@pytest.mark.django_db
class TestContactSegmentResolver:
    def test_metadata_key_filter_runs_on_sqlite(self):
        Contact.objects.create(email="gold@example.com", metadata={"tier": "gold"})
        Contact.objects.create(email="silver@example.com", metadata={"tier": "silver"})
        resolver = ContactSegmentResolver()

        flt = {"rules": [{"field": "metadata.tier", "op": "=", "value": "gold"}]}
        assert resolver.count_matches(flt) == 1

    def test_not_equal_uses_exclude(self):
        Contact.objects.create(email="keep@example.com", name="Keep")
        Contact.objects.create(email="drop@example.com", name="Drop")
        resolver = ContactSegmentResolver()

        flt = {"rules": [{"field": "name", "op": "!=", "value": "Drop"}]}
        emails = set(resolver._apply_filter(flt).values_list("email", flat=True))
        assert emails == {"keep@example.com"}

    def test_unknown_field_is_skipped(self):
        Contact.objects.create(email="a@example.com")
        resolver = ContactSegmentResolver()

        flt = {"rules": [{"field": "id); DROP TABLE", "op": "=", "value": 1}]}
        # Unknown field is skipped (not a FieldError); all contacts still match.
        assert resolver.count_matches(flt) == 1
