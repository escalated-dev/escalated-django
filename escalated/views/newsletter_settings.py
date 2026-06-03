"""Admin newsletter settings HTTP views."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from escalated.models import EscalatedSetting
from escalated.newsletter_conf import discover_newsletter_themes, newsletter_config
from escalated.rendering import render_page
from escalated.views.newsletter_utils import (
    _method_is,
    _parse_body,
    guard_manage,
    newsletters_enabled_view,
)

SETTING_KEYS = {
    "default_from": "string",
    "default_reply_to": "string",
    "default_theme": "string",
    "rate_limit_per_minute": "number",
    "batch_size": "number",
    "tracking_enabled": "boolean",
}


def _settings_payload() -> dict:
    settings = {}
    for key in SETTING_KEYS:
        stored = EscalatedSetting.get(f"newsletter.{key}")
        if stored is not None:
            if key == "tracking_enabled":
                settings[key] = stored in ("1", "true", "True", "yes")
            elif key in ("rate_limit_per_minute", "batch_size"):
                settings[key] = int(stored)
            else:
                settings[key] = stored
        else:
            default = newsletter_config(key)
            if key == "tracking_enabled" and default is None:
                default = True
            settings[key] = default
    return settings


@login_required
@newsletters_enabled_view
def show(request):
    if _method_is(request, "PUT", "PATCH"):
        return update(request)
    if denied := guard_manage(request):
        return denied
    return render_page(
        request,
        "Escalated/Admin/Newsletters/Settings",
        {"settings": _settings_payload(), "themes": ["default", "branded"]},
    )


def update(request):
    if denied := guard_manage(request):
        return denied
    data = _parse_body(request)
    theme = (data.get("default_theme") or "").strip()
    if not theme:
        return render_page(
            request,
            "Escalated/Admin/Newsletters/Settings",
            {"settings": _settings_payload(), "themes": discover_newsletter_themes(), "errors": {"default_theme": "Required."}},
        )
    try:
        rate = int(data.get("rate_limit_per_minute"))
        batch = int(data.get("batch_size"))
        assert 1 <= rate <= 10000
        assert 1 <= batch <= 1000
    except (TypeError, ValueError, AssertionError):
        return render_page(
            request,
            "Escalated/Admin/Newsletters/Settings",
            {"settings": _settings_payload(), "themes": discover_newsletter_themes(), "errors": {"rate_limit_per_minute": "Invalid."}},
        )

    tracking = data.get("tracking_enabled")
    if tracking in (True, False, "true", "false", "1", "0", 1, 0):
        tracking_bool = str(tracking).lower() in ("true", "1", "yes")
    else:
        tracking_bool = bool(tracking)

    values = {
        "default_from": data.get("default_from") or "",
        "default_reply_to": data.get("default_reply_to") or "",
        "default_theme": theme[:64],
        "rate_limit_per_minute": rate,
        "batch_size": batch,
        "tracking_enabled": tracking_bool,
    }
    for key, val in values.items():
        stored = str(int(val)) if key == "tracking_enabled" else str(val if val is not None else "")
        EscalatedSetting.set(f"newsletter.{key}", stored)

    return redirect("/admin/newsletters/settings")
