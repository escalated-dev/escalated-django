"""Ticket subject allowlist resolution and serialization helpers."""

from __future__ import annotations

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models

from escalated.conf import get_setting
from escalated.contracts.ticket_subject import TicketSubjectProtocol


def get_ticket_subject_type_allowlist() -> list[str]:
    """Flatten ESCALATED['TICKET_SUBJECT_TYPES'] (list or alias dict) to lookup keys."""
    configured = get_setting("TICKET_SUBJECT_TYPES") or []
    if isinstance(configured, dict):
        keys: list[str] = []
        for key, value in configured.items():
            keys.append(str(key))
            keys.append(str(value))
        return keys
    return [str(item) for item in configured]


def model_type_key(model: models.Model) -> str:
    """Stable type identifier for a host model (Django app label + model name)."""
    meta = model._meta
    if meta.proxy:
        return meta.concrete_model._meta.label
    return meta.label


def resolve_allowed_model_class(type_key: str) -> type[models.Model]:
    """
    Resolve a request-supplied type to a model class when it is allowlisted.

    Raises ValidationError on unknown or disallowed types (422 for API views).
    """
    allowed = get_ticket_subject_type_allowlist()
    if not allowed:
        raise ValidationError({"type": "Attaching ticket subjects via the API is not configured."})

    if type_key not in allowed:
        raise ValidationError({"type": f"Subject type [{type_key}] is not an allowed ticket subject."})

    model_class = _resolve_model_class(type_key)
    if model_class is None:
        raise ValidationError({"type": f"Subject type [{type_key}] could not be resolved to a model."})

    return model_class


def _resolve_model_class(type_key: str) -> type[models.Model] | None:
    if "." in type_key:
        try:
            return apps.get_model(type_key)
        except (LookupError, ValueError):
            pass

        try:
            from django.utils.module_loading import import_string

            candidate = import_string(type_key)
            if isinstance(candidate, type) and issubclass(candidate, models.Model):
                return candidate
        except ImportError:
            pass

    for model in apps.get_models():
        if model_type_key(model) == type_key:
            return model
    return None


def assert_subject_type_allowed(model: models.Model) -> None:
    """Enforce programmatic allowlist when ESCALATED['TICKET_SUBJECT_TYPES'] is non-empty."""
    allowed = get_ticket_subject_type_allowlist()
    if not allowed:
        return

    key = model_type_key(model)
    if key not in allowed:
        raise ValueError(f"Subject type [{key}] is not an allowed ticket subject.")


def serialize_ticket_subject_link(link) -> dict:
    """Serialize a TicketSubject row for ticket JSON payloads."""
    content_object = None
    try:
        content_object = link.subject
    except Exception:
        content_object = None

    presents = isinstance(content_object, TicketSubjectProtocol) or (
        content_object is not None and callable(getattr(content_object, "ticket_subject_title", None))
    )
    try:
        content_type = link.content_type
    except Exception:
        content_type = None

    if content_object is not None and hasattr(content_object, "_meta"):
        type_key = model_type_key(content_object)
    elif content_type is not None:
        type_key = _content_type_key(content_type)
    else:
        type_key = "unknown"

    missing = content_object is None

    if presents:
        title = content_object.ticket_subject_title()
        subtitle = content_object.ticket_subject_subtitle()
        url = content_object.ticket_subject_url()
        color = content_object.ticket_subject_color()
        icon = content_object.ticket_subject_icon()
    elif content_object is not None:
        name = getattr(content_object, "name", None)
        title = name if isinstance(name, str) and name else f"{type_key} #{link.object_id}"
        subtitle = url = color = icon = None
    else:
        title = f"{type_key} #{link.object_id}"
        subtitle = url = color = icon = None

    return {
        "type": type_key,
        "id": link.object_id,
        "role": link.role,
        "title": title,
        "subtitle": subtitle,
        "url": url,
        "color": color,
        "icon": icon,
        "missing": missing,
    }


def _content_type_key(content_type: ContentType) -> str:
    model_class = content_type.model_class()
    if model_class is not None:
        return model_type_key(model_class)
    return f"{content_type.app_label}.{content_type.model}"
