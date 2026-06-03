"""Admin newsletter template HTTP views."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from escalated.models import NewsletterTemplate
from escalated.rendering import render_page
from escalated.views.newsletter_utils import (
    _method_is,
    _parse_body,
    _user_id,
    abort_422,
    discover_newsletter_themes,
    guard_manage,
    newsletters_enabled_view,
    serialize_template,
)


@login_required
@newsletters_enabled_view
def index(request):
    if request.method == "POST":
        return store(request)
    if denied := guard_manage(request):
        return denied
    templates = [serialize_template(t) for t in NewsletterTemplate.objects.order_by("-created_at")]
    return render_page(request, "Escalated/Admin/Newsletters/Templates/Index", {"templates": templates})


@login_required
@newsletters_enabled_view
def create(request):
    if denied := guard_manage(request):
        return denied
    return render_page(
        request,
        "Escalated/Admin/Newsletters/Templates/Create",
        {"themes": discover_newsletter_themes()},
    )


def store(request):
    if denied := guard_manage(request):
        return denied
    data = _parse_body(request)
    name = (data.get("name") or "").strip()
    theme = (data.get("theme") or "").strip()
    body = data.get("body_markdown")
    if not name or not theme or not body:
        return render_page(
            request,
            "Escalated/Admin/Newsletters/Templates/Create",
            {"themes": discover_newsletter_themes(), "errors": {"name": "Required fields missing."}},
        )
    schema = data.get("merge_fields_schema")
    if isinstance(schema, str) and schema:
        try:
            schema = json.loads(schema)
        except json.JSONDecodeError:
            schema = None
    NewsletterTemplate.objects.create(
        name=name[:255],
        theme=theme[:64],
        subject_template=data.get("subject_template"),
        body_markdown=body,
        merge_fields_schema=schema,
        created_by=_user_id(request),
    )
    return redirect("/admin/newsletters/templates")


@login_required
@newsletters_enabled_view
def show(request, template_id: int):
    if _method_is(request, "PUT", "PATCH"):
        return update(request, template_id)
    if _method_is(request, "DELETE"):
        return destroy(request, template_id)
    if denied := guard_manage(request):
        return denied
    tpl = get_object_or_404(NewsletterTemplate, pk=template_id)
    return render_page(
        request,
        "Escalated/Admin/Newsletters/Templates/Show",
        {"template": serialize_template(tpl), "themes": discover_newsletter_themes(), "isNew": False},
    )


def update(request, template_id: int):
    if denied := guard_manage(request):
        return denied
    tpl = get_object_or_404(NewsletterTemplate, pk=template_id)
    data = _parse_body(request)
    tpl.name = (data.get("name") or tpl.name)[:255]
    tpl.theme = (data.get("theme") or tpl.theme)[:64]
    tpl.subject_template = data.get("subject_template", tpl.subject_template)
    tpl.body_markdown = data.get("body_markdown") or tpl.body_markdown
    if "merge_fields_schema" in data:
        schema = data.get("merge_fields_schema")
        if isinstance(schema, str) and schema:
            try:
                schema = json.loads(schema)
            except json.JSONDecodeError:
                schema = None
        tpl.merge_fields_schema = schema
    tpl.save()
    return redirect(f"/admin/newsletters/templates/{tpl.id}")


def destroy(request, template_id: int):
    if denied := guard_manage(request):
        return denied
    tpl = get_object_or_404(NewsletterTemplate, pk=template_id)
    tpl.delete()
    return redirect("/admin/newsletters/templates")
