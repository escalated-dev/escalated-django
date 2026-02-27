import json

import pytest
from unittest.mock import patch, MagicMock

from django.test import RequestFactory

from escalated.models import (
    CustomField, TicketLink, SideConversation, SideConversationReply,
    Article, ArticleCategory, Ticket,
)
from escalated.views import admin
from tests.factories import (
    UserFactory, TicketFactory, CustomFieldFactory,
    SideConversationFactory, SideConversationReplyFactory,
    ArticleCategoryFactory, ArticleFactory, TicketLinkFactory,
)


@pytest.fixture
def rf():
    return RequestFactory()


def _make_admin_request(rf, method, path, data=None, user=None, content_type=None):
    if user is None:
        user = UserFactory(username="admin_p2", is_staff=True, is_superuser=True)
    if method == "GET":
        request = rf.get(path)
    elif content_type == "application/json":
        request = rf.post(
            path,
            data=json.dumps(data or {}),
            content_type="application/json",
        )
    else:
        request = rf.post(path, data=data or {})
    request.user = user
    from django.contrib.sessions.backends.db import SessionStore
    request.session = SessionStore()
    return request


# ---------------------------------------------------------------------------
# Custom Fields
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCustomFieldsAdminViews:
    @patch("escalated.views.admin.render")
    def test_index_returns_fields(self, mock_render, rf):
        CustomFieldFactory(slug="cf-test-idx")
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", "/admin/custom-fields/")
        admin.custom_fields_index(request)

        mock_render.assert_called_once()
        args = mock_render.call_args
        assert args[0][1] == "Escalated/Admin/CustomFields/Index"
        props = args[1]["props"] if "props" in args[1] else args[0][2]
        assert "custom_fields" in props

    def test_create_post_creates_field(self, rf):
        request = _make_admin_request(rf, "POST", "/admin/custom-fields/create/", data={
            "name": "Priority Level",
            "type": "select",
            "context": "ticket",
            "options": json.dumps(["Low", "Medium", "High"]),
            "position": "0",
        })

        response = admin.custom_fields_create(request)
        assert response.status_code == 302
        assert CustomField.objects.filter(name="Priority Level").exists()
        field = CustomField.objects.get(name="Priority Level")
        assert field.options == ["Low", "Medium", "High"]

    def test_edit_post_updates_field(self, rf):
        field = CustomFieldFactory(name="Old Name", slug="old-cf")
        request = _make_admin_request(rf, "POST", f"/admin/custom-fields/{field.pk}/edit/", data={
            "name": "New Name",
            "type": "textarea",
            "context": "user",
        })

        response = admin.custom_fields_edit(request, field.pk)
        assert response.status_code == 302

        field.refresh_from_db()
        assert field.name == "New Name"
        assert field.type == "textarea"
        assert field.context == "user"

    def test_delete_removes_field(self, rf):
        field = CustomFieldFactory(slug="cf-to-delete")
        request = _make_admin_request(rf, "POST", f"/admin/custom-fields/{field.pk}/delete/")

        response = admin.custom_fields_delete(request, field.pk)
        assert response.status_code == 302
        assert not CustomField.objects.filter(pk=field.pk).exists()

    def test_reorder_updates_positions(self, rf):
        f1 = CustomFieldFactory(position=0, slug="cf-reorder1")
        f2 = CustomFieldFactory(position=1, slug="cf-reorder2")

        request = _make_admin_request(
            rf, "POST", "/admin/custom-fields/reorder/",
            data={"positions": [
                {"id": f1.pk, "position": 5},
                {"id": f2.pk, "position": 3},
            ]},
            content_type="application/json",
        )

        response = admin.custom_fields_reorder(request)
        assert response.status_code == 200

        f1.refresh_from_db()
        f2.refresh_from_db()
        assert f1.position == 5
        assert f2.position == 3

    def test_non_admin_forbidden(self, rf):
        user = UserFactory(username="nonadmin_cf", is_staff=False)
        request = _make_admin_request(rf, "GET", "/admin/custom-fields/", user=user)

        response = admin.custom_fields_index(request)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Ticket Links
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTicketLinksAdminViews:
    def test_index_returns_links(self, rf):
        t1 = TicketFactory()
        t2 = TicketFactory()
        TicketLinkFactory(parent_ticket=t1, child_ticket=t2)

        request = _make_admin_request(rf, "GET", f"/admin/tickets/{t1.pk}/links/")
        response = admin.ticket_links_index(request, t1.pk)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "links" in data
        assert len(data["links"]) == 1

    def test_store_creates_link(self, rf):
        t1 = TicketFactory()
        t2 = TicketFactory()

        request = _make_admin_request(
            rf, "POST", f"/admin/tickets/{t1.pk}/links/store/",
            data={
                "target_reference": t2.reference,
                "link_type": "related",
            },
            content_type="application/json",
        )

        response = admin.ticket_links_store(request, t1.pk)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "link" in data
        assert TicketLink.objects.filter(
            parent_ticket=t1, child_ticket=t2
        ).exists()

    def test_store_prevents_self_linking(self, rf):
        t1 = TicketFactory()

        request = _make_admin_request(
            rf, "POST", f"/admin/tickets/{t1.pk}/links/store/",
            data={
                "target_reference": t1.reference,
                "link_type": "related",
            },
            content_type="application/json",
        )

        response = admin.ticket_links_store(request, t1.pk)
        assert response.status_code == 400

    def test_store_prevents_duplicates(self, rf):
        t1 = TicketFactory()
        t2 = TicketFactory()
        TicketLinkFactory(parent_ticket=t1, child_ticket=t2, link_type="related")

        request = _make_admin_request(
            rf, "POST", f"/admin/tickets/{t1.pk}/links/store/",
            data={
                "target_reference": t2.reference,
                "link_type": "related",
            },
            content_type="application/json",
        )

        response = admin.ticket_links_store(request, t1.pk)
        assert response.status_code == 400

    def test_destroy_removes_link(self, rf):
        t1 = TicketFactory()
        t2 = TicketFactory()
        link = TicketLinkFactory(parent_ticket=t1, child_ticket=t2)

        request = _make_admin_request(
            rf, "POST", f"/admin/tickets/{t1.pk}/links/{link.pk}/delete/",
        )

        response = admin.ticket_links_destroy(request, t1.pk, link.pk)
        assert response.status_code == 200
        assert not TicketLink.objects.filter(pk=link.pk).exists()


# ---------------------------------------------------------------------------
# Ticket Merging
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTicketMergeAdminViews:
    def test_merge_search_returns_tickets(self, rf):
        t1 = TicketFactory(subject="Login issue")

        request = _make_admin_request(rf, "GET", "/admin/tickets/merge-search/")
        request = rf.get("/admin/tickets/merge-search/", {"q": "Login"})
        user = UserFactory(username="merge_admin", is_staff=True, is_superuser=True)
        request.user = user
        from django.contrib.sessions.backends.db import SessionStore
        request.session = SessionStore()

        response = admin.ticket_merge_search(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "tickets" in data
        assert len(data["tickets"]) >= 1

    def test_merge_search_empty_query(self, rf):
        request = _make_admin_request(rf, "GET", "/admin/tickets/merge-search/")

        response = admin.ticket_merge_search(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["tickets"] == []

    def test_merge_merges_tickets(self, rf):
        source = TicketFactory()
        target = TicketFactory()

        request = _make_admin_request(
            rf, "POST", f"/admin/tickets/{source.pk}/merge/",
            data={"target_reference": target.reference},
            content_type="application/json",
        )

        response = admin.ticket_merge(request, source.pk)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True

        source.refresh_from_db()
        assert source.status == Ticket.Status.CLOSED
        assert source.merged_into == target

    def test_merge_prevents_self_merge(self, rf):
        source = TicketFactory()

        request = _make_admin_request(
            rf, "POST", f"/admin/tickets/{source.pk}/merge/",
            data={"target_reference": source.reference},
            content_type="application/json",
        )

        response = admin.ticket_merge(request, source.pk)
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Side Conversations
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSideConversationsAdminViews:
    def test_index_returns_conversations(self, rf):
        ticket = TicketFactory()
        SideConversationFactory(ticket=ticket)

        request = _make_admin_request(rf, "GET", f"/admin/tickets/{ticket.pk}/side-conversations/")
        response = admin.side_conversations_index(request, ticket.pk)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "side_conversations" in data
        assert len(data["side_conversations"]) == 1

    def test_store_creates_conversation(self, rf):
        ticket = TicketFactory()

        request = _make_admin_request(
            rf, "POST", f"/admin/tickets/{ticket.pk}/side-conversations/store/",
            data={
                "subject": "Check with billing",
                "body": "Need to verify the charge",
                "channel": "internal",
            },
            content_type="application/json",
        )

        response = admin.side_conversations_store(request, ticket.pk)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "side_conversation" in data
        assert data["side_conversation"]["subject"] == "Check with billing"

        sc = SideConversation.objects.get(subject="Check with billing")
        assert sc.replies.count() == 1

    def test_store_requires_subject(self, rf):
        ticket = TicketFactory()

        request = _make_admin_request(
            rf, "POST", f"/admin/tickets/{ticket.pk}/side-conversations/store/",
            data={"body": "Missing subject"},
            content_type="application/json",
        )

        response = admin.side_conversations_store(request, ticket.pk)
        assert response.status_code == 400

    def test_reply_adds_reply(self, rf):
        ticket = TicketFactory()
        sc = SideConversationFactory(ticket=ticket)

        request = _make_admin_request(
            rf, "POST",
            f"/admin/tickets/{ticket.pk}/side-conversations/{sc.pk}/reply/",
            data={"body": "Here is my reply"},
            content_type="application/json",
        )

        response = admin.side_conversations_reply(request, ticket.pk, sc.pk)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "reply" in data
        assert data["reply"]["body"] == "Here is my reply"

    def test_reply_requires_body(self, rf):
        ticket = TicketFactory()
        sc = SideConversationFactory(ticket=ticket)

        request = _make_admin_request(
            rf, "POST",
            f"/admin/tickets/{ticket.pk}/side-conversations/{sc.pk}/reply/",
            data={"body": ""},
            content_type="application/json",
        )

        response = admin.side_conversations_reply(request, ticket.pk, sc.pk)
        assert response.status_code == 400

    def test_close_closes_conversation(self, rf):
        ticket = TicketFactory()
        sc = SideConversationFactory(ticket=ticket, status="open")

        request = _make_admin_request(
            rf, "POST",
            f"/admin/tickets/{ticket.pk}/side-conversations/{sc.pk}/close/",
        )

        response = admin.side_conversations_close(request, ticket.pk, sc.pk)
        assert response.status_code == 200

        sc.refresh_from_db()
        assert sc.status == "closed"


# ---------------------------------------------------------------------------
# Knowledge Base - Articles
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestArticlesAdminViews:
    @patch("escalated.views.admin.render")
    def test_index_returns_articles(self, mock_render, rf):
        ArticleFactory(slug="art-test-idx")
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", "/admin/kb/articles/")
        admin.articles_index(request)

        mock_render.assert_called_once()
        args = mock_render.call_args
        assert args[0][1] == "Escalated/Admin/KB/Articles/Index"
        props = args[1]["props"] if "props" in args[1] else args[0][2]
        assert "articles" in props
        assert "pagination" in props
        assert "categories" in props

    def test_create_post_creates_article(self, rf):
        cat = ArticleCategoryFactory(slug="art-create-cat")
        request = _make_admin_request(rf, "POST", "/admin/kb/articles/create/", data={
            "title": "Getting Started Guide",
            "body": "Welcome to Escalated...",
            "status": "draft",
            "category_id": str(cat.pk),
        })

        response = admin.articles_create(request)
        assert response.status_code == 302
        assert Article.objects.filter(title="Getting Started Guide").exists()

    def test_create_published_sets_published_at(self, rf):
        request = _make_admin_request(rf, "POST", "/admin/kb/articles/create/", data={
            "title": "Published Article",
            "body": "Content here",
            "status": "published",
        })

        admin.articles_create(request)
        article = Article.objects.get(title="Published Article")
        assert article.published_at is not None

    def test_edit_post_updates_article(self, rf):
        article = ArticleFactory(title="Old Title", slug="art-edit-old")
        request = _make_admin_request(rf, "POST", f"/admin/kb/articles/{article.pk}/edit/", data={
            "title": "New Title",
            "body": "Updated body",
            "status": "draft",
        })

        response = admin.articles_edit(request, article.pk)
        assert response.status_code == 302

        article.refresh_from_db()
        assert article.title == "New Title"
        assert article.body == "Updated body"

    def test_delete_removes_article(self, rf):
        article = ArticleFactory(slug="art-to-delete")
        request = _make_admin_request(rf, "POST", f"/admin/kb/articles/{article.pk}/delete/")

        response = admin.articles_delete(request, article.pk)
        assert response.status_code == 302
        assert not Article.objects.filter(pk=article.pk).exists()

    def test_non_admin_forbidden(self, rf):
        user = UserFactory(username="nonadmin_art", is_staff=False)
        request = _make_admin_request(rf, "GET", "/admin/kb/articles/", user=user)

        response = admin.articles_index(request)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Knowledge Base - Categories
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestKBCategoriesAdminViews:
    @patch("escalated.views.admin.render")
    def test_index_returns_categories(self, mock_render, rf):
        ArticleCategoryFactory(slug="kbcat-test-idx")
        mock_render.return_value = MagicMock(status_code=200)

        request = _make_admin_request(rf, "GET", "/admin/kb/categories/")
        admin.kb_categories_index(request)

        mock_render.assert_called_once()
        args = mock_render.call_args
        assert args[0][1] == "Escalated/Admin/KB/Categories/Index"
        props = args[1]["props"] if "props" in args[1] else args[0][2]
        assert "categories" in props

    def test_store_creates_category(self, rf):
        request = _make_admin_request(rf, "POST", "/admin/kb/categories/store/", data={
            "name": "Troubleshooting",
            "position": "0",
        })

        response = admin.kb_categories_store(request)
        assert response.status_code == 302
        assert ArticleCategory.objects.filter(name="Troubleshooting").exists()

    def test_store_requires_name(self, rf):
        request = _make_admin_request(rf, "POST", "/admin/kb/categories/store/", data={
            "name": "",
        })

        response = admin.kb_categories_store(request)
        assert response.status_code == 400

    def test_update_updates_category(self, rf):
        cat = ArticleCategoryFactory(name="Old Name", slug="kbcat-edit-old")
        request = _make_admin_request(rf, "POST", f"/admin/kb/categories/{cat.pk}/update/", data={
            "name": "New Name",
            "description": "Updated desc",
        })

        response = admin.kb_categories_update(request, cat.pk)
        assert response.status_code == 302

        cat.refresh_from_db()
        assert cat.name == "New Name"
        assert cat.description == "Updated desc"

    def test_delete_removes_category(self, rf):
        cat = ArticleCategoryFactory(slug="kbcat-to-delete")
        request = _make_admin_request(rf, "POST", f"/admin/kb/categories/{cat.pk}/delete/")

        response = admin.kb_categories_delete(request, cat.pk)
        assert response.status_code == 302
        assert not ArticleCategory.objects.filter(pk=cat.pk).exists()
