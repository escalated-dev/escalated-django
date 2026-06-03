"""Admin newsletter list HTTP views."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from escalated.models import Contact, NewsletterList, NewsletterListMember
from escalated.rendering import render_page
from escalated.services.newsletter.contact_segment_resolver import ContactSegmentResolver
from escalated.views.newsletter_utils import (
    guard_manage,
    _method_is,
    _parse_body,
    _user_id,
    abort_422,
    list_member_counts,
    lists_with_counts,
    newsletters_enabled_view,
    parse_csv_import,
    serialize_list_short,
)


@login_required
@newsletters_enabled_view
def index(request):
    if request.method == "POST":
        return store(request)
    if denied := guard_manage(request):
        return denied
    return render_page(request, "Escalated/Admin/Newsletters/Lists/Index", {"lists": lists_with_counts()})


@login_required
@newsletters_enabled_view
def create(request):
    if denied := guard_manage(request):
        return denied
    return render_page(request, "Escalated/Admin/Newsletters/Lists/Create", {})


def store(request):
    if denied := guard_manage(request):
        return denied
    data = _parse_body(request)
    name = (data.get("name") or "").strip()
    if not name:
        return render_page(
            request,
            "Escalated/Admin/Newsletters/Lists/Create",
            {"errors": {"name": "This field is required."}},
        )
    kind = data.get("kind")
    if kind not in ("static", "dynamic"):
        return render_page(
            request,
            "Escalated/Admin/Newsletters/Lists/Create",
            {"errors": {"kind": "Invalid kind."}},
        )
    filter_json = data.get("filter_json")
    if isinstance(filter_json, str) and filter_json:
        try:
            filter_json = json.loads(filter_json)
        except json.JSONDecodeError:
            filter_json = None

    lst = NewsletterList.objects.create(
        name=name[:255],
        description=data.get("description"),
        kind=kind,
        filter_json=filter_json,
        created_by=_user_id(request),
    )
    return redirect(f"/admin/newsletters/lists/{lst.id}")


@login_required
@newsletters_enabled_view
def show(request, list_id: int):
    if _method_is(request, "PUT", "PATCH"):
        return update(request, list_id)
    if _method_is(request, "DELETE"):
        return destroy(request, list_id)
    if denied := guard_manage(request):
        return denied
    lst = get_object_or_404(NewsletterList, pk=list_id)
    members_qs = (
        NewsletterListMember.objects.filter(list_id=lst.id)
        .order_by("-id")
    )
    paginator = Paginator(members_qs, 100)
    page = paginator.get_page(request.GET.get("page", 1))
    contact_ids = [m.contact_id for m in page.object_list]
    contacts = {c.id: c for c in Contact.objects.filter(id__in=contact_ids)}
    members = []
    for m in page.object_list:
        c = contacts.get(m.contact_id)
        members.append(
            {
                "id": m.id,
                "list_id": m.list_id,
                "contact_id": m.contact_id,
                "contact": {"id": c.id, "name": c.name, "email": c.email} if c else None,
            }
        )
    mc, oo = list_member_counts(lst.id)
    match_count = 0
    if lst.kind == "dynamic":
        match_count = ContactSegmentResolver().count_matches(lst.filter_json or {"rules": []})

    return render_page(
        request,
        "Escalated/Admin/Newsletters/Lists/Show",
        {
            "list": serialize_list_short(lst, member_count=mc, opted_out_count=oo),
            "members": {
                "data": members,
                "current_page": page.number,
                "last_page": paginator.num_pages,
                "per_page": 100,
                "total": paginator.count,
            },
            "matchCount": match_count,
        },
    )


def update(request, list_id: int):
    if denied := guard_manage(request):
        return denied
    lst = get_object_or_404(NewsletterList, pk=list_id)
    data = _parse_body(request)
    if "name" in data and data["name"] is not None:
        lst.name = str(data["name"])[:255]
    if "description" in data:
        lst.description = data.get("description")
    if "filter_json" in data:
        fj = data.get("filter_json")
        if isinstance(fj, str) and fj:
            try:
                fj = json.loads(fj)
            except json.JSONDecodeError:
                fj = None
        lst.filter_json = fj
    lst.save()
    return redirect(f"/admin/newsletters/lists/{lst.id}")


def destroy(request, list_id: int):
    if denied := guard_manage(request):
        return denied
    lst = get_object_or_404(NewsletterList, pk=list_id)
    lst.delete()
    return redirect("/admin/newsletters/lists")


@login_required
@newsletters_enabled_view
@require_http_methods(["POST"])
def add_member(request, list_id: int):
    if denied := guard_manage(request):
        return denied
    lst = get_object_or_404(NewsletterList, pk=list_id)
    if lst.kind != "static":
        return abort_422("Members can only be added to static lists")
    data = _parse_body(request)
    try:
        contact_id = int(data.get("contact_id"))
    except (TypeError, ValueError):
        return abort_422("contact_id is required")
    if not Contact.objects.filter(id=contact_id).exists():
        return abort_422("contact does not exist")
    NewsletterListMember.objects.get_or_create(
        list_id=lst.id,
        contact_id=contact_id,
        defaults={"added_by": _user_id(request)},
    )
    return redirect(f"/admin/newsletters/lists/{lst.id}")


@login_required
@newsletters_enabled_view
def remove_member(request, list_id: int, contact_id: int):
    if denied := guard_manage(request):
        return denied
    if not _method_is(request, "DELETE"):
        return HttpResponseNotAllowed(["DELETE"])
    lst = get_object_or_404(NewsletterList, pk=list_id)
    if lst.kind != "static":
        return abort_422("Members can only be removed from static lists")
    NewsletterListMember.objects.filter(list_id=lst.id, contact_id=contact_id).delete()
    return redirect(f"/admin/newsletters/lists/{lst.id}")


@login_required
@newsletters_enabled_view
@require_http_methods(["POST"])
def import_csv(request, list_id: int):
    if denied := guard_manage(request):
        return denied
    lst = get_object_or_404(NewsletterList, pk=list_id)
    if lst.kind != "static":
        return abort_422("CSV import is only supported for static lists")
    upload = request.FILES.get("file")
    if not upload:
        return abort_422("file is required")
    emails = parse_csv_import(upload)
    imported = 0
    for email in emails:
        contact, _ = Contact.objects.get_or_create(email=email)
        _, created = NewsletterListMember.objects.get_or_create(
            list_id=lst.id,
            contact_id=contact.id,
            defaults={"added_by": _user_id(request)},
        )
        if created:
            imported += 1
    request.session["status"] = f"Imported {imported} contacts"
    return redirect(f"/admin/newsletters/lists/{lst.id}")
