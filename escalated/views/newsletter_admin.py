"""Admin newsletter campaign HTTP views."""

from __future__ import annotations

import secrets

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from escalated.models import Contact, Newsletter, NewsletterDelivery, NewsletterList, NewsletterTemplate
from escalated.rendering import render_page
from escalated.services.newsletter.planner import NewsletterPlanner
from escalated.services.newsletter.renderer import NewsletterRenderer
from escalated.views.newsletter_utils import (
    _method_is,
    _parse_body,
    _user_id,
    abort_422,
    compose_props,
    guard_manage,
    guard_send,
    mail_configured,
    newsletters_enabled_view,
    serialize_delivery,
    serialize_newsletter,
    validate_campaign_form,
)


@login_required
@newsletters_enabled_view
def index(request):
    if request.method == "POST":
        return store(request)
    if denied := guard_manage(request):
        return denied
    tab = request.GET.get("tab", "drafts")
    if tab == "scheduled":
        statuses = ["scheduled", "sending", "paused"]
    elif tab == "sent":
        statuses = ["sent", "failed"]
    else:
        statuses = ["draft"]

    qs = Newsletter.objects.filter(status__in=statuses).order_by("-created_at")
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page", 1))
    newsletters = []
    list_ids = {n.target_list_id for n in page.object_list}
    lists_by_id = {lst.id: lst for lst in NewsletterList.objects.filter(id__in=list_ids)}
    for nl in page.object_list:
        newsletters.append(serialize_newsletter(nl, lists_by_id.get(nl.target_list_id)))

    return render_page(
        request,
        "Escalated/Admin/Newsletters/Index",
        {
            "newsletters": {
                "data": newsletters,
                "current_page": page.number,
                "last_page": paginator.num_pages,
                "per_page": 50,
                "total": paginator.count,
            },
            "tab": tab,
        },
    )


@login_required
@newsletters_enabled_view
def create(request):
    if denied := guard_manage(request):
        return denied
    return render_page(request, "Escalated/Admin/Newsletters/Compose", compose_props())


def store(request):
    if denied := guard_manage(request):
        return denied
    data = _parse_body(request)
    try:
        validated = validate_campaign_form(data)
    except ValidationError as e:
        return render_page(
            request,
            "Escalated/Admin/Newsletters/Compose",
            {**compose_props(), "errors": e.message_dict},
        )

    if validated["status"] in ("scheduled", "sending"):
        if denied := guard_send(request):
            return denied
        if not mail_configured():
            return render_page(
                request,
                "Escalated/Admin/Newsletters/Compose",
                {**compose_props(), "errors": {"from_email": "Outbound mail is not configured."}},
            )

    nl = Newsletter.objects.create(created_by=_user_id(request), **validated)
    if validated["status"] == "sending":
        NewsletterPlanner().plan(nl)
    return redirect(f"/admin/newsletters/{nl.id}")


@login_required
@newsletters_enabled_view
@require_http_methods(["POST"])
def preview(request):
    if denied := guard_manage(request):
        return denied
    data = _parse_body(request)
    from_email = data.get("from_email") or "preview@example.test"
    nl = Newsletter(
        id=0,
        subject=data.get("subject") or "",
        from_email=from_email,
        from_name=None,
        reply_to=None,
        target_list_id=int(data["target_list_id"]) if data.get("target_list_id") else 0,
        template_id=None,
        theme=data.get("theme") or "default",
        body_markdown=data.get("body_markdown"),
        status="draft",
    )
    contact = Contact(id=0, email="preview@example.test", name="Preview User", metadata={})
    delivery = NewsletterDelivery(tracking_token="preview", newsletter=nl, contact=contact, email_at_send=contact.email)
    html = NewsletterRenderer().render(delivery)
    return JsonResponse({"html": html})


@login_required
@newsletters_enabled_view
@require_http_methods(["POST"])
def test_send(request):
    if denied := guard_send(request):
        return denied
    data = _parse_body(request)
    try:
        validated = validate_campaign_form(data)
    except ValidationError as e:
        return JsonResponse({"errors": e.message_dict}, status=422)
    if not mail_configured():
        return JsonResponse({"from_email": ["Outbound mail is not configured."]}, status=400)

    nl = Newsletter(id=0, **validated)
    contact = Contact(
        id=int(request.user.pk) if str(request.user.pk).isdigit() else 0,
        email=request.user.email or validated["from_email"],
        name=getattr(request.user, "get_full_name", lambda: "")() or "Tester",
        metadata={},
    )
    token = secrets.token_hex(20)
    delivery = NewsletterDelivery(
        tracking_token=token,
        newsletter=nl,
        contact=contact,
        email_at_send=contact.email,
        is_test=True,
    )
    html = NewsletterRenderer().render(delivery)
    from_addr = (
        f'"{validated["from_name"]}" <{validated["from_email"]}>'
        if validated.get("from_name")
        else validated["from_email"]
    )
    msg = EmailMultiAlternatives(
        subject=f"[TEST] {validated['subject']}",
        body=html,
        from_email=from_addr,
        to=[contact.email],
    )
    msg.attach_alternative(html, "text/html")
    msg.send()
    return JsonResponse({"ok": True})


@login_required
@newsletters_enabled_view
def show(request, newsletter_id: int):
    if _method_is(request, "PUT", "PATCH"):
        return update(request, newsletter_id)
    if _method_is(request, "DELETE"):
        return destroy(request, newsletter_id)
    if denied := guard_manage(request):
        return denied
    nl = get_object_or_404(Newsletter, pk=newsletter_id)
    target_list = NewsletterList.objects.filter(id=nl.target_list_id).first()
    tab = request.GET.get("tab", "overview")
    status_filter = request.GET.get("status")
    deliveries_qs = NewsletterDelivery.objects.filter(newsletter_id=nl.id, is_test=False).order_by("-id")
    if status_filter:
        deliveries_qs = deliveries_qs.filter(status=status_filter)
    paginator = Paginator(deliveries_qs, 100)
    page = paginator.get_page(request.GET.get("page", 1))
    contact_ids = {d.contact_id for d in page.object_list}
    contacts = {c.id: c for c in Contact.objects.filter(id__in=contact_ids)}
    delivery_data = [serialize_delivery(d, contacts.get(d.contact_id)) for d in page.object_list]

    return render_page(
        request,
        "Escalated/Admin/Newsletters/Show",
        {
            "newsletter": serialize_newsletter(nl, target_list),
            "deliveries": {
                "data": delivery_data,
                "current_page": page.number,
                "last_page": paginator.num_pages,
                "per_page": 100,
                "total": paginator.count,
            },
            "topClicks": [],
            "tab": tab,
        },
    )


@login_required
@newsletters_enabled_view
def edit(request, newsletter_id: int):
    if denied := guard_manage(request):
        return denied
    nl = get_object_or_404(Newsletter, pk=newsletter_id)
    if nl.status not in ("draft", "scheduled"):
        return abort_422("Only drafts and scheduled newsletters can be edited")
    return render_page(
        request,
        "Escalated/Admin/Newsletters/Edit",
        {**compose_props(), "newsletter": serialize_newsletter(nl)},
    )


def update(request, newsletter_id: int):
    if denied := guard_manage(request):
        return denied
    nl = get_object_or_404(Newsletter, pk=newsletter_id)
    data = _parse_body(request)
    try:
        validated = validate_campaign_form(data)
    except ValidationError as e:
        return render_page(
            request,
            "Escalated/Admin/Newsletters/Edit",
            {**compose_props(), "newsletter": serialize_newsletter(nl), "errors": e.message_dict},
        )
    if validated["status"] in ("scheduled", "sending"):
        if denied := guard_send(request):
            return denied
    for field, value in validated.items():
        setattr(nl, field, value)
    nl.save()
    if validated["status"] == "sending":
        NewsletterPlanner().plan(nl)
    return redirect(f"/admin/newsletters/{nl.id}")


def destroy(request, newsletter_id: int):
    if denied := guard_manage(request):
        return denied
    nl = get_object_or_404(Newsletter, pk=newsletter_id)
    if nl.status != "draft":
        return abort_422("Only drafts can be deleted")
    nl.delete()
    return redirect("/admin/newsletters")
