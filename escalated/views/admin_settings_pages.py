"""Admin Settings sub-pages: CSAT, public tickets, data retention, database, email.

Each matches the props, fields and validation escalated-laravel gives the shared
``Escalated/Admin/Settings/*`` pages. Values live in the ``EscalatedSetting``
key/value store as text.

A save redirects back to its page. What it has to say survives the redirect in
the session and is shown once: ``flash`` (``success`` or ``error``) and, for a
rejected save, ``errors`` keyed by field (``addresses.0.email`` for list items,
as the page reads them).
"""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect

from escalated.conf import get_setting
from escalated.models import EscalatedSetting
from escalated.rendering import render_page
from escalated.request_data import is_json, request_data
from escalated.services import connection_inspector, data_retention
from escalated.views.admin import _require_admin

FLASH_SESSION_KEY = "escalated_settings_page_flash"
ERRORS_SESSION_KEY = "escalated_settings_page_errors"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fields(request):
    """The posted fields as Python values (JSON keeps lists and numbers)."""
    data = request_data(request)
    if is_json(request):
        return data.raw
    return {key: data.get(key) for key in data}


def _show(request, component, props):
    """Render a page with the flash and errors a previous save left behind."""
    session = request.session
    return render_page(
        request,
        component,
        props={
            **props,
            "flash": session.pop(FLASH_SESSION_KEY, {}),
            "errors": session.pop(ERRORS_SESSION_KEY, {}),
        },
    )


def _back(request, route, *, success=None, error=None, errors=None):
    if errors:
        request.session[ERRORS_SESSION_KEY] = errors
    elif success or error:
        request.session[FLASH_SESSION_KEY] = {"success": success} if success else {"error": error}
    return redirect(f"escalated:{route}")


def _text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _int(value):
    """An integer from an int or a digit string, else ``None``. Booleans are not integers."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = _text(value).strip()
    if text.lstrip("-").isdigit():
        return int(text)
    return None


def _email_error(value, field_label):
    try:
        validate_email(value)
    except ValidationError:
        return f"The {field_label} must be a valid email address."
    if len(value) > 255:
        return f"The {field_label} may not be longer than 255 characters."
    return None


def _setting(key, default):
    value = EscalatedSetting.get(key)
    return default if value is None else value


# ---------------------------------------------------------------------------
# CSAT
# ---------------------------------------------------------------------------

CSAT_DEFAULTS = {
    "csat_question_text": "How would you rate your support experience?",
    "csat_scale": "1-5",
    "csat_delivery_trigger": "on_resolve",
    "csat_delay_hours": "0",
}


@login_required
def settings_csat(request):
    if check := _require_admin(request):
        return check
    if request.method == "POST":
        return _csat_update(request)
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])

    settings = {key: _setting(key, default) for key, default in CSAT_DEFAULTS.items()}
    settings["csat_delay_hours"] = _int(settings["csat_delay_hours"]) or 0
    return _show(request, "Escalated/Admin/Settings/CsatSettings", {"settings": settings})


def _csat_update(request):
    data = _fields(request)
    errors = {}

    question = data.get("csat_question_text")
    if not isinstance(question, str) or not question.strip():
        errors["csat_question_text"] = "The question text is required."
    elif len(question) > 500:
        errors["csat_question_text"] = "The question text may not be longer than 500 characters."
    if data.get("csat_scale") not in ("1-3", "1-5"):
        errors["csat_scale"] = "The scale must be 1-3 or 1-5."
    if data.get("csat_delivery_trigger") not in ("on_resolve", "delayed", "manual"):
        errors["csat_delivery_trigger"] = "The delivery trigger must be on_resolve, delayed or manual."
    hours = _int(data.get("csat_delay_hours"))
    if hours is None or not 0 <= hours <= 168:
        errors["csat_delay_hours"] = "The delay must be a whole number of hours from 0 to 168."

    if errors:
        return _back(request, "admin_settings_csat", errors=errors)

    EscalatedSetting.set("csat_question_text", question)
    EscalatedSetting.set("csat_scale", data["csat_scale"])
    EscalatedSetting.set("csat_delivery_trigger", data["csat_delivery_trigger"])
    EscalatedSetting.set("csat_delay_hours", str(hours))
    return _back(request, "admin_settings_csat", success="CSAT settings updated.")


# ---------------------------------------------------------------------------
# Public tickets (guest policy)
# ---------------------------------------------------------------------------

GUEST_POLICY_MODES = ("unassigned", "guest_user", "prompt_signup")


@login_required
def settings_public_tickets(request):
    """Guest policy for tickets from the public widget and inbound email.

    The widget reads these same keys at request time, so a change applies
    without a redeploy. The page posts; Laravel's route is a PUT; both work.
    """
    if check := _require_admin(request):
        return check
    if request.method in ("POST", "PUT"):
        return _public_tickets_update(request)
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST", "PUT"])

    return _show(
        request,
        "Escalated/Admin/Settings/PublicTickets",
        {
            "settings": {
                "guest_policy_mode": _setting("guest_policy_mode", "unassigned") or "unassigned",
                "guest_policy_user_id": _setting("guest_policy_user_id", "") or None,
                "guest_policy_signup_url_template": _setting("guest_policy_signup_url_template", ""),
            }
        },
    )


def _public_tickets_update(request):
    data = _fields(request)
    errors = {}

    mode = data.get("guest_policy_mode")
    if mode not in GUEST_POLICY_MODES:
        errors["guest_policy_mode"] = "The mode must be unassigned, guest_user or prompt_signup."

    raw_user_id = data.get("guest_policy_user_id")
    user_id = None
    if raw_user_id not in (None, ""):
        user_id = _int(raw_user_id)
        if user_id is None or user_id < 1:
            errors["guest_policy_user_id"] = "The guest user must be a user id."
    if mode == "guest_user" and user_id is None and "guest_policy_user_id" not in errors:
        errors["guest_policy_user_id"] = "A guest user is required for the guest_user mode."

    template = data.get("guest_policy_signup_url_template")
    if template is not None and not isinstance(template, str):
        errors["guest_policy_signup_url_template"] = "The signup URL template must be text."
    elif template and len(template) > 500:
        errors["guest_policy_signup_url_template"] = "The signup URL template may not be longer than 500 characters."

    if errors:
        return _back(request, "admin_settings_public_tickets", errors=errors)

    EscalatedSetting.set("guest_policy_mode", mode)
    EscalatedSetting.set("guest_policy_user_id", str(user_id) if mode == "guest_user" else "")
    EscalatedSetting.set(
        "guest_policy_signup_url_template",
        (template or "").strip() if mode == "prompt_signup" else "",
    )
    return _back(request, "admin_settings_public_tickets", success="Guest policy updated.")


# ---------------------------------------------------------------------------
# Data retention
# ---------------------------------------------------------------------------

# What Laravel's ``boolean`` rule accepts. The True/False keys also match 1/0.
_BOOLEAN_TEXT = {True: "1", False: "0", "1": "1", "0": "0", "true": "1", "false": "0"}


@login_required
def settings_data_retention(request):
    if check := _require_admin(request):
        return check
    if request.method == "POST":
        return _data_retention_update(request)
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])

    settings = {key: _setting(key, default) for key, default in data_retention.DEFAULTS.items()}
    settings["retention_user_data_gdpr"] = EscalatedSetting.get_bool("retention_user_data_gdpr", False)
    return _show(
        request,
        "Escalated/Admin/Settings/DataRetention",
        {"settings": settings, "purgePreview": data_retention.preview()},
    )


def _data_retention_update(request):
    data = _fields(request)
    errors = {}

    choices = {
        "retention_closed_tickets": data_retention.RECORD_CHOICES,
        "retention_attachments": data_retention.RECORD_CHOICES,
        "retention_audit_logs": data_retention.AUDIT_LOG_CHOICES,
    }
    for key, allowed in choices.items():
        if data.get(key) not in allowed:
            errors[key] = f"The {key.replace('_', ' ')} must be one of: {', '.join(allowed)}."
    gdpr = data.get("retention_user_data_gdpr")
    gdpr_text = _BOOLEAN_TEXT.get(gdpr) if isinstance(gdpr, (bool, int, str)) else None
    if gdpr_text is None:
        errors["retention_user_data_gdpr"] = "The GDPR setting must be true or false."

    if errors:
        return _back(request, "admin_settings_data_retention", errors=errors)

    for key in choices:
        EscalatedSetting.set(key, data[key])
    EscalatedSetting.set("retention_user_data_gdpr", gdpr_text)
    return _back(request, "admin_settings_data_retention", success="Data retention settings updated.")


# ---------------------------------------------------------------------------
# Database connection (read-only)
# ---------------------------------------------------------------------------

PINNED_MESSAGE = "The database connection is set in configuration and cannot be changed from here."


@login_required
def settings_database(request):
    """Which database Escalated uses. Set by ``ESCALATED["DATABASE"]``; shown, never switched here."""
    if check := _require_admin(request):
        return check
    if request.method == "POST":
        return _back(request, "admin_settings_database", error=PINNED_MESSAGE)
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])

    current = connection_inspector.current_connection()
    return _show(
        request,
        "Escalated/Admin/Settings/DatabaseConnection",
        {
            "connections": connection_inspector.all_connections(),
            "current": current,
            "hostDefault": connection_inspector.HOST_DEFAULT,
            "pinnedByConfig": True,
            "tablePrefix": get_setting("TABLE_PREFIX") or "",
        },
    )


@login_required
def settings_database_test(request):
    """Probe one configured connection without changing anything."""
    if check := _require_admin(request):
        return check
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    name = _fields(request).get("connection")
    if not isinstance(name, str) or not name.strip():
        return JsonResponse({"errors": {"connection": "The connection field is required."}}, status=422)
    if len(name) > 64 or not connection_inspector.configured(name):
        return JsonResponse(
            {"errors": {"connection": f"[{name[:64]}] is not configured in settings.DATABASES."}},
            status=422,
        )
    return JsonResponse(connection_inspector.describe(name))


# ---------------------------------------------------------------------------
# Email addresses
# ---------------------------------------------------------------------------

DKIM_STATUSES = ("verified", "pending", "failed", "unknown")


def _stored_addresses():
    try:
        addresses = json.loads(EscalatedSetting.get("email_addresses") or "[]")
    except (TypeError, ValueError):
        return []
    return addresses if isinstance(addresses, list) else []


@login_required
def settings_email(request):
    """Inbound/outbound addresses of the email channel. Stored only, as in Laravel."""
    if check := _require_admin(request):
        return check
    if request.method == "POST":
        return _email_update(request)
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])

    return _show(
        request,
        "Escalated/Admin/Settings/EmailSettings",
        {
            "addresses": _stored_addresses(),
            "defaultReplyAddress": _setting("default_reply_address", "") or "",
        },
    )


def _clean_address(index, item, errors):
    prefix = f"addresses.{index}"
    if not isinstance(item, dict):
        errors[prefix] = "Each address must be an object."
        return None

    email = item.get("email")
    if not isinstance(email, str) or not email.strip():
        errors[f"{prefix}.email"] = "The email field is required."
    elif message := _email_error(email.strip(), "email"):
        errors[f"{prefix}.email"] = message

    display_name = item.get("display_name")
    if display_name in ("",):
        display_name = None
    if display_name is not None and (not isinstance(display_name, str) or len(display_name) > 255):
        errors[f"{prefix}.display_name"] = "The display name must be text of at most 255 characters."

    department_id = item.get("department_id")
    if department_id in ("",):
        department_id = None
    if department_id is not None:
        department_id = _int(department_id)
        if department_id is None:
            errors[f"{prefix}.department_id"] = "The department must be an integer."

    dkim_status = item.get("dkim_status") or None
    if dkim_status is not None and dkim_status not in DKIM_STATUSES:
        errors[f"{prefix}.dkim_status"] = "The DKIM status must be verified, pending, failed or unknown."

    return {
        "email": email.strip() if isinstance(email, str) else email,
        "display_name": display_name,
        "department_id": department_id,
        "dkim_status": dkim_status or "unknown",
    }


def _email_update(request):
    data = _fields(request)
    errors = {}

    addresses = data.get("addresses")
    if isinstance(addresses, str):
        try:
            addresses = json.loads(addresses)
        except ValueError:
            addresses = None
    cleaned = []
    if not isinstance(addresses, list) or not addresses:
        errors["addresses"] = "At least one address is required."
    else:
        cleaned = [_clean_address(index, item, errors) for index, item in enumerate(addresses)]

    reply = data.get("default_reply_address")
    if reply not in (None, ""):
        if not isinstance(reply, str):
            errors["default_reply_address"] = "The default reply address must be a valid email address."
        elif message := _email_error(reply.strip(), "default reply address"):
            errors["default_reply_address"] = message

    if errors:
        return _back(request, "admin_settings_email", errors=errors)

    EscalatedSetting.set("email_addresses", json.dumps(cleaned))
    if reply not in (None, ""):
        EscalatedSetting.set("default_reply_address", reply.strip())
    return _back(request, "admin_settings_email", success="Email settings updated.")
