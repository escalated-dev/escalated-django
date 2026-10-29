"""Customer/KnowledgeBase/Index and Article against escalated-laravel.

Laravel's Customer\\KnowledgeBaseController serves them at /kb and /kb/<slug>,
with feedback posted to /kb/<slug>/feedback: published articles only, 404 when
the knowledge base is off, sign-in required unless it is public.
"""

import json

import pytest
from django.urls import reverse
from django.utils import timezone

from escalated.models import Article, ArticleCategory, EscalatedSetting
from tests.factories import UserFactory


def get_page(client, url, **query):
    response = client.get(url, query, HTTP_X_INERTIA="true")
    assert response.status_code == 200, f"{url} answered {response.status_code}"
    return json.loads(response.content)


@pytest.fixture
def kb(db):
    author = UserFactory(username="writer", email="writer@example.com")
    billing = ArticleCategory.objects.create(name="Billing", slug="billing", position=1, description="Money")
    ArticleCategory.objects.create(name="Child", slug="child", parent=billing)
    empty = ArticleCategory.objects.create(name="Empty", slug="empty", position=2)
    now = timezone.now()
    refunds = Article.objects.create(
        category=billing,
        title="Refunds",
        slug="refunds",
        body="How refunds work",
        status="published",
        author=author,
        published_at=now,
    )
    invoices = Article.objects.create(
        category=billing,
        title="Invoices",
        slug="invoices",
        body="Where invoices live",
        status="published",
        published_at=now - timezone.timedelta(days=1),
    )
    Article.objects.create(category=billing, title="Draft", slug="draft", body="secret", status="draft")
    return {"billing": billing, "empty": empty, "refunds": refunds, "invoices": invoices}


@pytest.mark.django_db
def test_index(client, user, kb):
    client.force_login(user)

    body = get_page(client, reverse("escalated:customer_kb_index"))
    props = body["props"]

    assert body["component"] == "Escalated/Customer/KnowledgeBase/Index"
    assert {"categories", "articles", "filters", "feedbackEnabled"} <= set(props)
    # Root categories, ordered, with their published article count.
    assert [(c["name"], c["articles_count"]) for c in props["categories"]] == [("Billing", 2), ("Empty", 0)]
    assert {"id", "name", "slug", "description", "articles_count"} <= set(props["categories"][0])

    articles = props["articles"]
    assert [a["title"] for a in articles["data"]] == ["Refunds", "Invoices"]
    assert {"data", "links", "last_page", "current_page", "total"} <= set(articles)
    row = articles["data"][0]
    assert {"id", "slug", "title", "view_count", "category"} <= set(row)
    assert row["category"]["name"] == "Billing"
    assert "author" not in row
    assert props["filters"] == {}
    assert props["feedbackEnabled"] is True


@pytest.mark.django_db
def test_index_filters(client, user, kb):
    client.force_login(user)

    props = get_page(client, reverse("escalated:customer_kb_index"), search="invoice")["props"]
    assert [a["title"] for a in props["articles"]["data"]] == ["Invoices"]
    assert props["filters"] == {"search": "invoice"}

    props = get_page(client, reverse("escalated:customer_kb_index"), category=str(kb["empty"].pk))["props"]
    assert props["articles"]["data"] == []
    assert props["filters"] == {"category": str(kb["empty"].pk)}


@pytest.mark.django_db
def test_article(client, user, kb):
    client.force_login(user)

    body = get_page(client, reverse("escalated:customer_kb_show", args=["refunds"]))
    props = body["props"]

    assert body["component"] == "Escalated/Customer/KnowledgeBase/Article"
    article = props["article"]
    for key in ("id", "slug", "title", "body", "view_count", "published_at", "category"):
        assert key in article, key
    assert article["category"]["id"] == kb["billing"].pk
    assert article["category"]["name"] == "Billing"
    assert "author" not in article
    assert props["related"] == [{"id": kb["invoices"].pk, "title": "Invoices", "slug": "invoices"}]
    assert props["feedbackEnabled"] is True

    kb["refunds"].refresh_from_db()
    assert kb["refunds"].view_count == 1


@pytest.mark.django_db
def test_drafts_and_unknown_slugs_are_not_found(client, user, kb):
    client.force_login(user)

    assert client.get(reverse("escalated:customer_kb_show", args=["draft"]), HTTP_X_INERTIA="true").status_code == 404
    assert client.get(reverse("escalated:customer_kb_show", args=["nope"]), HTTP_X_INERTIA="true").status_code == 404


@pytest.mark.django_db
def test_feedback(client, user, kb):
    client.force_login(user)
    url = reverse("escalated:customer_kb_feedback", args=["refunds"])

    response = client.post(url, data=json.dumps({"helpful": True}), content_type="application/json")
    assert response.status_code in (302, 303)
    client.post(url, {"helpful": "0"})
    assert client.post(url, {}).status_code == 422

    kb["refunds"].refresh_from_db()
    assert (kb["refunds"].helpful_count, kb["refunds"].not_helpful_count) == (1, 1)


@pytest.mark.django_db
def test_feedback_off(client, user, kb):
    EscalatedSetting.set("knowledge_base_feedback_enabled", "0")
    client.force_login(user)

    assert (
        get_page(client, reverse("escalated:customer_kb_show", args=["refunds"]))["props"]["feedbackEnabled"] is False
    )
    response = client.post(reverse("escalated:customer_kb_feedback", args=["refunds"]), {"helpful": "1"})
    assert response.status_code == 404


@pytest.mark.django_db
def test_access(client, user, kb):
    index = reverse("escalated:customer_kb_index")

    # Public by default: guests may read it.
    assert client.get(index, HTTP_X_INERTIA="true").status_code == 200

    EscalatedSetting.set("knowledge_base_public", "0")
    assert client.get(index, HTTP_X_INERTIA="true").status_code == 403

    EscalatedSetting.set("knowledge_base_enabled", "0")
    client.force_login(user)
    assert client.get(index, HTTP_X_INERTIA="true").status_code == 404
