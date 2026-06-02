"""Newsletter feature flag and settings resolution (ESCALATED dict + DB overrides)."""

from __future__ import annotations

from django.conf import settings

from escalated.conf import get_setting
from escalated.models import EscalatedSetting


def newsletters_enabled() -> bool:
    return bool(get_setting("enable_newsletters"))


def _escalated_dict():
    return getattr(settings, "ESCALATED", {}) or {}


def newsletter_config(key: str, default=None):
    """Read `newsletter.{key}` from EscalatedSetting, else ESCALATED[`newsletter_{key}`]."""
    stored = EscalatedSetting.get(f"newsletter.{key}")
    if stored is not None:
        if key == "tracking_enabled":
            return stored in ("1", "true", "True", "yes")
        if key in ("rate_limit_per_minute", "batch_size"):
            try:
                return int(stored)
            except (TypeError, ValueError):
                pass
        return stored
    flat = f"newsletter_{key}"
    return _escalated_dict().get(flat, default)


def discover_newsletter_themes() -> list[str]:
    from pathlib import Path

    from django.apps import apps

    app_config = apps.get_app_config("escalated")
    themes_dir = Path(app_config.path) / "templates" / "escalated" / "newsletter_themes"
    if not themes_dir.is_dir():
        return ["default", "branded"]
    slugs = sorted(p.stem for p in themes_dir.glob("*.html") if p.stem)
    return slugs or ["default", "branded"]
