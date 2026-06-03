"""Shared helpers for newsletter HTTP views."""

from __future__ import annotations

import csv
import io
import json
import re
import secrets
from datetime import datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from escalated.models import (
    Contact,
    EscalatedSetting,
    Newsletter,
    NewsletterDelivery,
    NewsletterList,
    NewsletterListMember,
    NewsletterTemplate,
)
from escalated.newsletter_conf import discover_newsletter_themes, newsletter_config, newsletters_enabled
from escalated.newsletter_permissions import require_newsletter_permission
from escalated.permissions import is_admin
from escalated.rendering import render_page


def newsletters_enabled_view(view_func):
    """404 when newsletters feature flag is off."""

    def wrapper(request, *args, **kwargs):
        if not newsletters_enabled():
            return HttpResponse(status=404)
        return view_func(request, *args, **kwargs)

    return wrapper


def _require_admin(request):
    if not request.user.is_authenticated:
        from django.shortcuts import redirect as dj_redirect

        return dj_redirect("login")
    if not is_admin(request.user):
        return HttpResponseForbidden("Admin access required.")
    return None


def guard_manage(request):
    check = _require_admin(request)
    if check:
        return check
    return require_newsletter_permission(request, "newsletters.manage")


def guard_send(request):
    denied = guard_manage(request)
    if denied:
        return denied
    return require_newsletter_permission(request, "newsletters.send")


def _user_id(request) -> str:
    return str(request.user.pk)


def _parse_body(request) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return {}
    return request.POST.dict() if request.method == "POST" else request.GET.dict()


def _method_is(request, *methods: str) -> bool:
    if request.method in methods:
        return True
    if request.method == "POST":
        spoofed = request.POST.get("_method", request.headers.get("X-HTTP-Method-Override", "")).upper()
        return spoofed in methods
    return False


def abort_422(message: str) -> HttpResponse:
    return HttpResponse(message, status=422, content_type="text/plain")


def mail_configured() -> bool:
    backend = getattr(settings, "EMAIL_BACKEND", "")
    if not backend:
        return False
    return "dummy" not in backend.lower()


# ---------------------------------------------------------------------------
# Serializers (minimal dicts for Inertia)
# ---------------------------------------------------------------------------


def serialize_list_short(lst: NewsletterList, member_count: int | None = None, opted_out_count: int = 0) -> dict:
    data = {
        "id": lst.id,
        "name": lst.name,
        "description": lst.description,
        "kind": lst.kind,
        "filter_json": lst.filter_json,
        "created_by": lst.created_by,
        "created_at": lst.created_at.isoformat() if lst.created_at else None,
        "updated_at": lst.updated_at.isoformat() if lst.updated_at else None,
    }
    if member_count is not None:
        data["member_count"] = member_count
    if opted_out_count:
        data["opted_out_count"] = opted_out_count
    return data


def serialize_newsletter(nl: Newsletter, target_list: NewsletterList | None = None) -> dict:
    data = {
        "id": nl.id,
        "subject": nl.subject,
        "from_email": nl.from_email,
        "from_name": nl.from_name,
        "reply_to": nl.reply_to,
        "target_list_id": nl.target_list_id,
        "template_id": nl.template_id,
        "theme": nl.theme,
        "body_markdown": nl.body_markdown,
        "status": nl.status,
        "scheduled_at": nl.scheduled_at.isoformat() if nl.scheduled_at else None,
        "sent_at": nl.sent_at.isoformat() if nl.sent_at else None,
        "created_by": nl.created_by,
        "sent_by": nl.sent_by,
        "summary_total": nl.summary_total,
        "summary_sent": nl.summary_sent,
        "summary_opened": nl.summary_opened,
        "summary_clicked": nl.summary_clicked,
        "summary_bounced": nl.summary_bounced,
        "summary_complained": nl.summary_complained,
        "created_at": nl.created_at.isoformat() if nl.created_at else None,
        "updated_at": nl.updated_at.isoformat() if nl.updated_at else None,
    }
    if target_list is not None:
        data["target_list"] = serialize_list_short(target_list)
    return data


def serialize_template(tpl: NewsletterTemplate) -> dict:
    return {
        "id": tpl.id,
        "name": tpl.name,
        "theme": tpl.theme,
        "subject_template": tpl.subject_template,
        "body_markdown": tpl.body_markdown,
        "merge_fields_schema": tpl.merge_fields_schema,
        "created_by": tpl.created_by,
        "created_at": tpl.created_at.isoformat() if tpl.created_at else None,
        "updated_at": tpl.updated_at.isoformat() if tpl.updated_at else None,
    }


def serialize_delivery(d: NewsletterDelivery, contact: Contact | None = None) -> dict:
    data = {
        "id": d.id,
        "newsletter_id": d.newsletter_id,
        "contact_id": d.contact_id,
        "email_at_send": d.email_at_send,
        "status": d.status,
        "tracking_token": d.tracking_token,
        "sent_at": d.sent_at.isoformat() if d.sent_at else None,
        "opened_at": d.opened_at.isoformat() if d.opened_at else None,
        "last_clicked_at": d.last_clicked_at.isoformat() if d.last_clicked_at else None,
        "clicks_count": d.clicks_count,
        "is_test": d.is_test,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
    if contact is not None:
        data["contact"] = {"id": contact.id, "name": contact.name, "email": contact.email}
    return data


def list_member_counts(list_id: int) -> tuple[int, int]:
    member_ids = NewsletterListMember.objects.filter(list_id=list_id).values_list("contact_id", flat=True)
    member_count = len(member_ids)
    opted_out = Contact.objects.filter(id__in=member_ids, marketing_opt_out_at__isnull=False).count()
    return member_count, opted_out


def lists_with_counts() -> list[dict]:
    lists = NewsletterList.objects.all().order_by("name")
    result = []
    for lst in lists:
        mc, oo = list_member_counts(lst.id)
        result.append(serialize_list_short(lst, member_count=mc, opted_out_count=oo))
    return result


def compose_props() -> dict:
    return {
        "lists": lists_with_counts(),
        "templates": [
            {"id": t.id, "name": t.name}
            for t in NewsletterTemplate.objects.all().order_by("name")
        ],
        "themes": discover_newsletter_themes(),
        "mailConfigured": mail_configured(),
        "canSend": True,
        "defaultFromEmail": newsletter_config("default_from", None),
        "defaultReplyTo": newsletter_config("default_reply_to", None),
        "defaultTheme": newsletter_config("default_theme", "default") or "default",
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _optional_str(data: dict, key: str, max_len: int | None = None):
    val = data.get(key)
    if val is None or val == "":
        return None
    val = str(val)
    if max_len and len(val) > max_len:
        raise ValidationError({key: f"Must be at most {max_len} characters."})
    return val


def _required_str(data: dict, key: str, max_len: int | None = None) -> str:
    val = data.get(key)
    if val is None or str(val).strip() == "":
        raise ValidationError({key: "This field is required."})
    val = str(val)
    if max_len and len(val) > max_len:
        raise ValidationError({key: f"Must be at most {max_len} characters."})
    return val


def validate_campaign_form(data: dict) -> dict:
    errors = {}
    try:
        subject = _required_str(data, "subject", 998)
    except ValidationError as e:
        errors.update(e.message_dict)

    for field in ("from_email",):
        raw = data.get(field)
        if not raw:
            errors[field] = "This field is required."
        else:
            try:
                validate_email(str(raw))
            except ValidationError:
                errors[field] = "Enter a valid email address."
            else:
                if len(str(raw)) > 320:
                    errors[field] = "Must be at most 320 characters."

    try:
        target_list_id = int(data.get("target_list_id") or 0)
        if not NewsletterList.objects.filter(id=target_list_id).exists():
            errors["target_list_id"] = "Selected list does not exist."
    except (TypeError, ValueError):
        errors["target_list_id"] = "This field is required."

    template_id = data.get("template_id")
    if template_id not in (None, ""):
        try:
            tid = int(template_id)
            if not NewsletterTemplate.objects.filter(id=tid).exists():
                errors["template_id"] = "Selected template does not exist."
        except (TypeError, ValueError):
            errors["template_id"] = "Invalid template."

    status = data.get("status") or "draft"
    if status not in ("draft", "scheduled", "sending"):
        errors["status"] = "Invalid status."

    scheduled_at = data.get("scheduled_at")
    parsed_scheduled = None
    if scheduled_at:
        parsed_scheduled = parse_datetime(str(scheduled_at))
        if parsed_scheduled is None:
            errors["scheduled_at"] = "Invalid date."
        elif parsed_scheduled <= timezone.now():
            errors["scheduled_at"] = "Must be a future date."

    reply_to = data.get("reply_to")
    if reply_to:
        try:
            validate_email(str(reply_to))
        except ValidationError:
            errors["reply_to"] = "Enter a valid email address."

    if errors:
        raise ValidationError(errors)

    return {
        "subject": subject,
        "from_email": str(data["from_email"]),
        "from_name": _optional_str(data, "from_name", 255),
        "reply_to": str(reply_to) if reply_to else None,
        "target_list_id": target_list_id,
        "template_id": int(template_id) if template_id not in (None, "") else None,
        "theme": _optional_str(data, "theme", 64),
        "body_markdown": data.get("body_markdown"),
        "status": status,
        "scheduled_at": parsed_scheduled,
    }


def paginate_queryset(qs, request, per_page: int, key: str = "page"):
    page_num = int(request.GET.get(key, 1) or 1)
    paginator = Paginator(qs, per_page)
    page = paginator.get_page(page_num)
    return {
        "data": list(page.object_list),
        "current_page": page.number,
        "last_page": paginator.num_pages,
        "per_page": per_page,
        "total": paginator.count,
    }


def parse_csv_import(file) -> list[str]:
    raw = file.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(raw))
    emails = []
    for row in reader:
        if not row:
            continue
        email = row[0].strip()
        if not email:
            continue
        try:
            validate_email(email)
            emails.append(email)
        except ValidationError:
            continue
    return emails


TOKEN_FROM_MESSAGE_ID = re.compile(r"n-\d+-([A-Za-z0-9]+)@")


def token_from_message_id(message_id: str) -> str:
    matched = TOKEN_FROM_MESSAGE_ID.search(message_id or "")
    if matched:
        return matched.group(1)
    local = (message_id or "").split("@")[0]
    local_match = re.match(r"^n-\d+-([A-Za-z0-9]+)$", local)
    return local_match.group(1) if local_match else ""
