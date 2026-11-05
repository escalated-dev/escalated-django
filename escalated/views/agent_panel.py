"""
The agent panel's own data routes (ADR 2026-11-05-agent-panel-data): the
agent's status, knowledge-base search, the notifications feed and per-agent
read markers. Each acts for the signed-in agent only. JSON clients get JSON;
an Inertia visit to a mutating route goes back.
"""

import html
import math
import re

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.translation import gettext as _

from escalated.kb_guards import kb_enabled
from escalated.models import AgentNotification, Article, Ticket
from escalated.permissions import can_view_ticket
from escalated.request_data import request_data
from escalated.services import agent_panel
from escalated.views.agent import _require_agent

KB_DEFAULT_LIMIT = 10
KB_MAX_LIMIT = 20


def _invalid(field, message):
    return JsonResponse({"message": message, "errors": {field: [message]}}, status=422)


def _back(request):
    if request.headers.get("X-Inertia"):
        return redirect(request.META.get("HTTP_REFERER") or reverse("escalated:agent_ticket_list"))
    return None


def _whole(value):
    if value in (None, ""):
        return None
    return int(value) if re.fullmatch(r"\d+", str(value)) else -1


@login_required
def status(request):
    """PUT/POST: any agent, light agents included, sets their own status."""
    check = _require_agent(request)
    if check:
        return check
    if request.method not in ("PUT", "POST", "PATCH"):
        return HttpResponseNotAllowed(["PUT", "POST"])

    value = request_data(request).get("status")
    if value not in agent_panel.AGENT_STATUSES:
        message = _("The selected status is invalid.")
        if request.headers.get("X-Inertia"):
            return redirect(request.META.get("HTTP_REFERER") or reverse("escalated:agent_ticket_list"))
        return _invalid("status", message)

    agent_panel.set_agent_status(request.user, value)
    return _back(request) or JsonResponse({"agent_status": value})


@login_required
def kb_search(request):
    """GET ?q=: published articles, title matches first, then the most recently updated."""
    check = _require_agent(request)
    if check:
        return check
    if not kb_enabled():
        return HttpResponseNotFound()

    q = (request.GET.get("q") or "").strip()
    if not 2 <= len(q) <= 200:
        return _invalid("q", _("The q field must be between 2 and 200 characters."))
    limit = _whole(request.GET.get("limit"))
    if limit is not None and not 1 <= limit <= KB_MAX_LIMIT:
        return _invalid("limit", _("The limit field must be between 1 and %(max)s.") % {"max": KB_MAX_LIMIT})

    from django.db.models import Case, IntegerField, Value, When

    # icontains escapes % and _ and ignores case on every database.
    articles = (
        Article.objects.published()
        .search(q)
        .select_related("category")
        .annotate(
            title_match=Case(When(title__icontains=q, then=Value(0)), default=Value(1), output_field=IntegerField())
        )
        .order_by("title_match", "-updated_at", "-id")[: limit or KB_DEFAULT_LIMIT]
    )
    return JsonResponse({"data": [_article(request, article) for article in articles]})


def _article(request, article):
    text = re.sub(r"\s+", " ", html.unescape(strip_tags(article.body or ""))).strip()
    return {
        "id": article.pk,
        "title": article.title,
        "excerpt": text if len(text) <= 160 else text[:160].rstrip() + "...",
        "url": agent_panel.kb_url(request, article),
        "category": {"id": article.category.pk, "name": article.category.name} if article.category else None,
        "updated_at": article.updated_at.isoformat() if article.updated_at else None,
    }


def _ticket(request, ticket_id):
    ticket = Ticket.objects.filter(pk=ticket_id).first()
    if ticket is None or not can_view_ticket(request.user, ticket):
        return None
    return ticket


@login_required
def ticket_read(request, ticket_id):
    return _mark(request, ticket_id, unread=False)


@login_required
def ticket_unread(request, ticket_id):
    return _mark(request, ticket_id, unread=True)


def _mark(request, ticket_id, unread):
    check = _require_agent(request)
    if check:
        return check
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    ticket = _ticket(request, ticket_id)
    if ticket is None:
        return HttpResponseNotFound(_("Ticket not found"))
    (agent_panel.mark_unread if unread else agent_panel.mark_read)(request.user, ticket)
    return _back(request) or JsonResponse({"is_unread": unread})


def _feed_check(request):
    check = _require_agent(request)
    if check:
        return check
    if not agent_panel.notifications_available():
        return HttpResponseNotFound()
    return None


@login_required
def notification_index(request):
    check = _feed_check(request)
    if check:
        return check

    page = _whole(request.GET.get("page"))
    per_page = _whole(request.GET.get("per_page"))
    if page is not None and page < 1:
        return _invalid("page", _("The page field must be at least 1."))
    if per_page is not None and not 1 <= per_page <= agent_panel.NOTIFICATIONS_MAX_PER_PAGE:
        return _invalid(
            "per_page",
            _("The per page field must be between 1 and %(max)s.") % {"max": agent_panel.NOTIFICATIONS_MAX_PER_PAGE},
        )
    page = page or 1
    per_page = per_page or agent_panel.NOTIFICATIONS_PER_PAGE

    rows = AgentNotification.objects.filter(user_id=request.user.pk)
    if str(request.GET.get("unread", "")).lower() in ("1", "true"):
        rows = rows.filter(read_at__isnull=True)
    total = rows.count()
    window = rows.order_by("-created_at", "-pk")[(page - 1) * per_page : page * per_page]

    return JsonResponse(
        {
            "data": agent_panel.present(window, request.user),
            "meta": {
                "current_page": page,
                "last_page": max(1, math.ceil(total / per_page)),
                "per_page": per_page,
                "total": total,
            },
            "unread_count": agent_panel.unread_count(request.user),
        }
    )


@login_required
def notification_read(request, notification_id):
    check = _feed_check(request)
    if check:
        return check
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    row = AgentNotification.objects.filter(pk=notification_id, user_id=request.user.pk).first()
    if row is None:
        return HttpResponseNotFound()
    if row.read_at is None:
        from django.utils import timezone

        row.read_at = timezone.now()
        row.save(update_fields=["read_at"])
    return JsonResponse({"unread_count": agent_panel.unread_count(request.user)})


@login_required
def notification_read_all(request):
    check = _feed_check(request)
    if check:
        return check
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    from django.utils import timezone

    AgentNotification.objects.filter(user_id=request.user.pk, read_at__isnull=True).update(read_at=timezone.now())
    return JsonResponse({"unread_count": 0})
