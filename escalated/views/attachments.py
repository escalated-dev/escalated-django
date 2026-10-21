"""The access-checked attachment download (see escalated/attachment_access.py)."""

import os
import re

from django.http import FileResponse, HttpResponseForbidden, HttpResponseNotAllowed, HttpResponseNotFound, JsonResponse
from django.utils.translation import gettext as _

from escalated import attachment_access

# Types a browser renders without running script. Anything else is sent as
# application/octet-stream; every response is a download either way.
SAFE_CONTENT_TYPES = {
    "application/pdf",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
}

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def safe_filename(name):
    name = os.path.basename(str(name or "").replace("\\", "/"))
    name = _CONTROL_CHARACTERS.sub("", name).replace('"', "").strip()
    return name or "attachment"


def _bearer_user(request):
    """The user an Escalated API token authenticates, or a response refusing it."""
    from django.utils import timezone

    from escalated.models import ApiToken

    plain_text = request.META.get("HTTP_AUTHORIZATION", "")[7:]
    api_token = ApiToken.find_by_plain_text(plain_text) if plain_text else None
    if api_token is None or api_token.is_expired:
        return None, JsonResponse({"message": "Invalid token."}, status=401)
    user = api_token.tokenable
    if user is None:
        return None, JsonResponse({"message": "Token owner not found."}, status=401)
    api_token.last_used_at = timezone.now()
    api_token.save(update_fields=["last_used_at", "updated_at"])
    return user, None


def attachment_download(request, attachment_id):
    from escalated.models import Attachment

    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])

    payload = attachment_access.read_token(request.GET.get("token"), attachment_id)
    if payload is None:
        return HttpResponseForbidden(_("This download link is invalid or has expired."))

    # API clients send their Escalated bearer token; a token that is supplied
    # but invalid never falls back to the session.
    user = getattr(request, "user", None)
    if request.META.get("HTTP_AUTHORIZATION", "").startswith("Bearer "):
        user, refused = _bearer_user(request)
        if refused is not None:
            return refused

    attachment = Attachment.objects.filter(pk=attachment_id).first()
    if attachment is None or attachment_access.ticket_of(attachment) is None:
        return HttpResponseNotFound(_("Attachment not found."))
    if not attachment_access.allows(user, attachment, payload):
        return HttpResponseForbidden(_("You cannot download this attachment."))
    if not attachment.file:
        return HttpResponseNotFound(_("Attachment not found."))
    try:
        handle = attachment.file.open("rb")
    except (FileNotFoundError, OSError):
        return HttpResponseNotFound(_("Attachment not found."))

    mime_type = (attachment.mime_type or "").split(";")[0].strip().lower()
    content_type = mime_type if mime_type in SAFE_CONTENT_TYPES else "application/octet-stream"
    response = FileResponse(
        handle,
        as_attachment=True,
        filename=safe_filename(attachment.original_filename),
        content_type=content_type,
    )
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response
