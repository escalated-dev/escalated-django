"""Attach/detach ticket subject endpoints (agent, admin, REST API)."""

import json

from django.core.exceptions import ValidationError
from django.http import HttpResponseNotFound, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from escalated.models import Ticket, TicketSubject
from escalated.ticket_subjects import resolve_allowed_model_class


def _parse_subject_payload(request) -> dict:
    if request.content_type and "json" in request.content_type:
        return json.loads(request.body or "{}")
    return {
        "type": request.POST.get("type"),
        "id": request.POST.get("id"),
        "role": request.POST.get("role"),
    }


def attach_ticket_subject(request, ticket: Ticket) -> JsonResponse:
    """POST body: type (required), id (required), role (optional)."""
    try:
        payload = _parse_subject_payload(request)
    except json.JSONDecodeError:
        return JsonResponse({"errors": {"_error": "Invalid JSON."}}, status=422)

    type_key = payload.get("type")
    subject_id = payload.get("id")
    if not type_key or subject_id is None or subject_id == "":
        return JsonResponse(
            {"errors": {"type": "Required.", "id": "Required."}},
            status=422,
        )

    try:
        model_class = resolve_allowed_model_class(str(type_key))
    except ValidationError as exc:
        return JsonResponse({"errors": exc.message_dict}, status=422)

    subject = model_class.objects.filter(pk=subject_id).first()
    if subject is None:
        return JsonResponse({"errors": {"id": "No matching subject was found."}}, status=422)

    role = payload.get("role")
    if role is not None:
        role = str(role)

    link = ticket.attach_subject(subject, role=role or None)
    return JsonResponse({"id": link.pk, "message": "Subject attached."})


def detach_ticket_subject(request, ticket: Ticket, subject_link_id: int) -> JsonResponse:
    link = TicketSubject.objects.filter(pk=subject_link_id, ticket=ticket).first()
    if link is None:
        return HttpResponseNotFound()

    link.delete()
    return JsonResponse({"message": "Subject detached."})


@csrf_exempt
@require_http_methods(["POST"])
def api_ticket_subjects_store(request, ticket: Ticket):
    return attach_ticket_subject(request, ticket)


@csrf_exempt
@require_http_methods(["DELETE"])
def api_ticket_subjects_destroy(request, ticket: Ticket, subject_id: int):
    return detach_ticket_subject(request, ticket, subject_id)
