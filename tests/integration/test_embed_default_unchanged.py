"""
Embedding the admin in the host's own admin panel is optional and off by
default (ADR 2026-11-05-embeddable-admin). With no ``ESCALATED["EMBED"]`` the
URL table, the shared props and the response headers are what they were
before the feature existed.

tests/fixtures/embed/default-routes.json is the URL table taken from the code
before the change (see tests/route_table.py).
"""

import json
from pathlib import Path

from tests.route_table import route_table

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "embed" / "default-routes.json"


def test_the_url_table_is_the_one_from_before_embedding_existed():
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    actual = json.loads(json.dumps(route_table()))

    assert [row["name"] for row in actual] == [row["name"] for row in expected]
    assert actual == expected
