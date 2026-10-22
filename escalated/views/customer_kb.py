"""The customer knowledge base: Customer/KnowledgeBase/Index and Article.

escalated-laravel's ``Customer\\KnowledgeBaseController``: published articles
only, newest first, 15 a page, searchable and filterable by category; an
article page counts the view and lists up to five others in its category; and
readers can mark an article helpful or not. The knowledge base answers 404 when
it is switched off and 403 to visitors who are not signed in unless it is
public.
"""

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect
from django.utils.translation import gettext as _

from escalated import kb_guards
from escalated.models import Article, ArticleCategory
from escalated.rendering import paginated, render_page
from escalated.request_data import request_data
from escalated.serializers import ArticleCategorySerializer, ArticleSerializer

PER_PAGE = 15

TRUE = {True, 1, "1", "true", "True", "on", "yes"}
FALSE = {False, 0, "0", "false", "False", "off", "no"}


def _inaccessible(request):
    """Why this visitor cannot read the knowledge base, or ``None`` if they can."""
    if not kb_guards.kb_enabled():
        raise Http404(_("Knowledge base is not available."))
    user = getattr(request, "user", None)
    if not kb_guards.kb_public() and not (user is not None and user.is_authenticated):
        return HttpResponseForbidden(_("Authentication required to access the knowledge base."))
    return None


def _article(article):
    """An article as a reader sees it: the author is the staff's business."""
    data = ArticleSerializer.serialize(article)
    data.pop("author", None)
    return data


def index(request):
    refused = _inaccessible(request)
    if refused:
        return refused

    categories = (
        ArticleCategory.objects.roots()
        .ordered()
        .annotate(articles_count=Count("articles", filter=Q(articles__status=Article.Status.PUBLISHED)))
    )

    articles = Article.objects.published().select_related("category")
    filters = {}
    search = request.GET.get("search")
    if search:
        filters["search"] = search
        articles = articles.search(search)
    category = request.GET.get("category")
    if category:
        filters["category"] = category
        articles = articles.filter(category_id=category) if category.isdigit() else articles.none()

    page = Paginator(articles.order_by("-published_at", "-pk"), PER_PAGE).get_page(request.GET.get("page", 1))

    return render_page(
        request,
        "Escalated/Customer/KnowledgeBase/Index",
        props={
            "categories": ArticleCategorySerializer.serialize_list(categories),
            "articles": paginated(request, page, [_article(a) for a in page.object_list]),
            "filters": filters,
            "feedbackEnabled": kb_guards.kb_feedback_enabled(),
        },
    )


def _published(slug):
    article = Article.objects.published().select_related("category").filter(slug=slug).first()
    if article is None:
        raise Http404(_("Article not found."))
    return article


def show(request, slug):
    refused = _inaccessible(request)
    if refused:
        return refused

    article = _published(slug)
    article.increment_views()

    related = (
        Article.objects.published()
        .filter(category_id=article.category_id)
        .exclude(pk=article.pk)
        .order_by("-published_at", "-pk")
        .values("id", "title", "slug")[:5]
    )

    return render_page(
        request,
        "Escalated/Customer/KnowledgeBase/Article",
        props={
            "article": _article(article),
            "related": list(related),
            "feedbackEnabled": kb_guards.kb_feedback_enabled(),
        },
    )


def feedback(request, slug):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    refused = _inaccessible(request)
    if refused:
        return refused
    if not kb_guards.kb_feedback_enabled():
        raise Http404(_("Feedback is not available."))

    article = _published(slug)
    helpful = request_data(request).get("helpful")
    if helpful in TRUE:
        article.mark_helpful()
    elif helpful in FALSE:
        article.mark_not_helpful()
    else:
        message = _("The helpful field must be true or false.")
        return JsonResponse({"message": message, "errors": {"helpful": message}}, status=422)

    return redirect("escalated:customer_kb_show", slug=article.slug)
