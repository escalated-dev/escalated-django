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

import pytest

from tests.factories import UserFactory
from tests.route_table import route_table

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "embed" / "default-routes.json"


def test_the_url_table_is_the_one_from_before_embedding_existed():
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    actual = json.loads(json.dumps(route_table()))

    assert [row["name"] for row in actual] == [row["name"] for row in expected]
    assert actual == expected


SHARE = "escalated.middleware.EscalatedInertiaShareMiddleware"


@pytest.mark.django_db
def test_the_admin_is_served_where_it_was_with_no_embed_props_or_framing_headers(client, settings):
    settings.MIDDLEWARE = [
        "escalated.middleware.EscalatedEmbedMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
        *settings.MIDDLEWARE,
        SHARE,
    ]
    client.force_login(UserFactory(username="default-admin", is_staff=True, is_superuser=True))

    response = client.get("/support/admin/tags/", HTTP_X_INERTIA="true")

    assert response.status_code == 200
    shared = json.loads(response.content)["props"]["escalated"]
    assert "embed" not in shared
    assert "navigation" not in shared
    assert response["X-Frame-Options"] == "DENY"
    assert not response.has_header("Content-Security-Policy")
    assert client.get("/admin/support/tags/", HTTP_X_INERTIA="true").status_code == 404
