import pytest
from django.db import IntegrityError

from escalated.models import (
    Article,
    ArticleCategory,
    CustomField,
    CustomFieldValue,
    SideConversation,
    SideConversationReply,
    Ticket,
    TicketLink,
)
from tests.factories import (
    ArticleCategoryFactory,
    ArticleFactory,
    CustomFieldFactory,
    CustomFieldValueFactory,
    SideConversationFactory,
    SideConversationReplyFactory,
    TicketFactory,
    TicketLinkFactory,
)

# ---------------------------------------------------------------------------
# Custom Fields
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCustomFieldModel:
    def test_auto_generates_slug(self):
        field = CustomFieldFactory(name="My Custom Field", slug="")
        assert field.slug == "my_custom_field"

    def test_field_type_choices(self):
        for ft in ["text", "textarea", "select", "multi_select", "checkbox", "date", "number"]:
            f = CustomFieldFactory(type=ft)
            assert f.type == ft

    def test_context_choices(self):
        for ctx in ["ticket", "user", "organization"]:
            f = CustomFieldFactory(context=ctx)
            assert f.context == ctx

    def test_str_returns_name(self):
        f = CustomFieldFactory(name="Priority Level")
        assert str(f) == "Priority Level"

    def test_ordering_by_position(self):
        f2 = CustomFieldFactory(position=2, slug="field-pos2")
        f1 = CustomFieldFactory(position=1, slug="field-pos1")
        f3 = CustomFieldFactory(position=3, slug="field-pos3")

        fields = list(CustomField.objects.all())
        assert fields[0] == f1
        assert fields[1] == f2
        assert fields[2] == f3

    def test_json_options(self):
        f = CustomFieldFactory(
            type="select",
            options=["Option A", "Option B", "Option C"],
        )
        f.refresh_from_db()
        assert f.options == ["Option A", "Option B", "Option C"]

    def test_active_default(self):
        f = CustomFieldFactory()
        assert f.active is True

    def test_required_default(self):
        f = CustomFieldFactory()
        assert f.required is False


@pytest.mark.django_db
class TestCustomFieldValueModel:
    def test_str_representation(self):
        field = CustomFieldFactory(name="Region")
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(Ticket)
        val = CustomFieldValueFactory(
            custom_field=field,
            entity_content_type=ct,
            entity_object_id=1,
            value="North America",
        )
        assert "Region" in str(val)
        assert "North America" in str(val)

    def test_cascade_delete_on_field(self):
        field = CustomFieldFactory()
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(Ticket)
        CustomFieldValueFactory(
            custom_field=field,
            entity_content_type=ct,
            entity_object_id=1,
        )
        field_pk = field.pk
        field.delete()
        assert not CustomFieldValue.objects.filter(custom_field_id=field_pk).exists()


# ---------------------------------------------------------------------------
# Ticket Links
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTicketLinkModel:
    def test_str_representation(self):
        link = TicketLinkFactory(link_type="related")
        assert "related" in str(link)

    def test_link_type_choices(self):
        for lt in ["problem_incident", "parent_child", "related"]:
            link = TicketLinkFactory(link_type=lt)
            assert link.link_type == lt

    def test_unique_together(self):
        t1 = TicketFactory()
        t2 = TicketFactory()
        TicketLinkFactory(parent_ticket=t1, child_ticket=t2, link_type="related")

        with pytest.raises(IntegrityError):
            TicketLinkFactory(parent_ticket=t1, child_ticket=t2, link_type="related")

    def test_cascade_delete_parent(self):
        link = TicketLinkFactory()
        parent_pk = link.parent_ticket.pk
        link.parent_ticket.delete()
        assert not TicketLink.objects.filter(parent_ticket_id=parent_pk).exists()

    def test_cascade_delete_child(self):
        link = TicketLinkFactory()
        child_pk = link.child_ticket.pk
        link.child_ticket.delete()
        assert not TicketLink.objects.filter(child_ticket_id=child_pk).exists()

    def test_links_as_parent_relation(self):
        t1 = TicketFactory()
        t2 = TicketFactory()
        link = TicketLinkFactory(parent_ticket=t1, child_ticket=t2)
        assert link in t1.links_as_parent.all()

    def test_links_as_child_relation(self):
        t1 = TicketFactory()
        t2 = TicketFactory()
        link = TicketLinkFactory(parent_ticket=t1, child_ticket=t2)
        assert link in t2.links_as_child.all()


# ---------------------------------------------------------------------------
# Side Conversations
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSideConversationModel:
    def test_str_representation(self):
        sc = SideConversationFactory(subject="Billing question")
        assert "Billing question" in str(sc)

    def test_default_status_is_open(self):
        sc = SideConversationFactory()
        assert sc.status == "open"

    def test_open_scope(self):
        sc_open = SideConversationFactory(status="open")
        sc_closed = SideConversationFactory(status="closed")

        open_convos = list(SideConversation.objects.open())
        assert sc_open in open_convos
        assert sc_closed not in open_convos

    def test_cascade_delete_with_ticket(self):
        sc = SideConversationFactory()
        ticket_pk = sc.ticket.pk
        sc.ticket.delete()
        assert not SideConversation.objects.filter(ticket_id=ticket_pk).exists()

    def test_replies_relationship(self):
        sc = SideConversationFactory()
        r1 = SideConversationReplyFactory(side_conversation=sc)
        r2 = SideConversationReplyFactory(side_conversation=sc)

        assert sc.replies.count() == 2
        assert r1 in sc.replies.all()
        assert r2 in sc.replies.all()


@pytest.mark.django_db
class TestSideConversationReplyModel:
    def test_str_representation(self):
        sc = SideConversationFactory(subject="Hardware issue")
        reply = SideConversationReplyFactory(side_conversation=sc)
        assert "Hardware issue" in str(reply)

    def test_cascade_delete_with_conversation(self):
        sc = SideConversationFactory()
        SideConversationReplyFactory(side_conversation=sc)
        sc_pk = sc.pk
        sc.delete()
        assert not SideConversationReply.objects.filter(side_conversation_id=sc_pk).exists()


# ---------------------------------------------------------------------------
# Knowledge Base
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestArticleCategoryModel:
    def test_str_returns_name(self):
        cat = ArticleCategoryFactory(name="Getting Started")
        assert str(cat) == "Getting Started"

    def test_roots_scope(self):
        root = ArticleCategoryFactory(parent=None, slug="root-cat")
        child = ArticleCategoryFactory(parent=root, slug="child-cat")

        roots = list(ArticleCategory.objects.roots())
        assert root in roots
        assert child not in roots

    def test_ordered_scope(self):
        c2 = ArticleCategoryFactory(position=2, name="Bravo", slug="cat-bravo")
        c1 = ArticleCategoryFactory(position=1, name="Alpha", slug="cat-alpha")
        c3 = ArticleCategoryFactory(position=2, name="Alpha", slug="cat-alpha2")

        ordered = list(ArticleCategory.objects.ordered())
        assert ordered[0] == c1  # position=1
        # position=2 ties broken by name
        assert ordered[1] == c3  # Alpha
        assert ordered[2] == c2  # Bravo

    def test_children_relationship(self):
        root = ArticleCategoryFactory(slug="root-rel")
        child = ArticleCategoryFactory(parent=root, slug="child-rel")

        assert child in root.children.all()

    def test_parent_set_null_on_delete(self):
        root = ArticleCategoryFactory(slug="root-del")
        child = ArticleCategoryFactory(parent=root, slug="child-del")

        root.delete()
        child.refresh_from_db()
        assert child.parent is None


@pytest.mark.django_db
class TestArticleModel:
    def test_str_returns_title(self):
        article = ArticleFactory(title="How to Reset Password")
        assert str(article) == "How to Reset Password"

    def test_default_status_is_draft(self):
        article = ArticleFactory()
        assert article.status == "draft"

    def test_published_scope(self):
        draft = ArticleFactory(status="draft", slug="art-draft")
        published = ArticleFactory(status="published", slug="art-pub")

        pub_list = list(Article.objects.published())
        assert published in pub_list
        assert draft not in pub_list

    def test_draft_scope(self):
        draft = ArticleFactory(status="draft", slug="art-draft2")
        published = ArticleFactory(status="published", slug="art-pub2")

        draft_list = list(Article.objects.draft())
        assert draft in draft_list
        assert published not in draft_list

    def test_search_scope(self):
        a1 = ArticleFactory(title="Password Reset Guide", slug="art-search1")
        a2 = ArticleFactory(title="Billing FAQ", body="How to reset your billing", slug="art-search2")
        a3 = ArticleFactory(title="Something else", slug="art-search3")

        results = list(Article.objects.search("reset"))
        assert a1 in results
        assert a2 in results
        assert a3 not in results

    def test_increment_views(self):
        article = ArticleFactory()
        assert article.view_count == 0

        article.increment_views()
        article.refresh_from_db()
        assert article.view_count == 1

    def test_mark_helpful(self):
        article = ArticleFactory()
        article.mark_helpful()
        article.refresh_from_db()
        assert article.helpful_count == 1

    def test_mark_not_helpful(self):
        article = ArticleFactory()
        article.mark_not_helpful()
        article.refresh_from_db()
        assert article.not_helpful_count == 1

    def test_ordering_by_created_at_desc(self):
        a1 = ArticleFactory(slug="art-ord1")
        a2 = ArticleFactory(slug="art-ord2")

        articles = list(Article.objects.all())
        assert articles[0] == a2
        assert articles[1] == a1

    def test_category_set_null_on_delete(self):
        cat = ArticleCategoryFactory(slug="cat-del-art")
        article = ArticleFactory(category=cat)

        cat.delete()
        article.refresh_from_db()
        assert article.category is None


@pytest.mark.django_db
class TestTicketTypeAndMergedFields:
    def test_ticket_type_default(self):
        t = TicketFactory()
        assert t.ticket_type == "question"

    def test_ticket_type_choices(self):
        for tt in ["question", "problem", "incident", "task"]:
            t = TicketFactory(ticket_type=tt)
            assert t.ticket_type == tt

    def test_merged_into_field(self):
        source = TicketFactory()
        target = TicketFactory()
        source.merged_into = target
        source.save()
        source.refresh_from_db()
        assert source.merged_into == target

    def test_merged_into_null_by_default(self):
        t = TicketFactory()
        assert t.merged_into is None
