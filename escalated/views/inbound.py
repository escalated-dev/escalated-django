import logging

from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from escalated.conf import get_setting
from escalated.mail.adapters import get_adapter
from escalated.services.inbound_email_service import InboundEmailService

logger = logging.getLogger("escalated")


@csrf_exempt
@require_POST
def inbound_webhook(request, adapter_name):
    """
    Receive inbound email webhooks from external services (Mailgun,
    Postmark, SES, etc.).

    This endpoint is intentionally NOT behind authentication since
    external email services POST to it directly.

    URL pattern: /support/inbound/<adapter_name>/

    Args:
        request: Django HttpRequest
        adapter_name: Name of the adapter (e.g. 'mailgun', 'postmark', 'ses')

    Returns:
        200 OK on success, 400/403 on error.
    """
    # Check if inbound email processing is enabled
    if not get_setting("INBOUND_EMAIL_ENABLED"):
        logger.warning(
            f"Inbound email webhook called but feature is disabled "
            f"(adapter={adapter_name})"
        )
        return HttpResponseBadRequest(_("Inbound email processing is disabled."))

    # Resolve the adapter
    try:
        adapter = get_adapter(adapter_name)
    except ValueError as exc:
        logger.error(f"Unknown inbound email adapter: {adapter_name}")
        return HttpResponseBadRequest(str(exc))

    # Verify the request authenticity
    if not adapter.verify_request(request):
        logger.warning(
            f"Inbound email webhook verification failed "
            f"(adapter={adapter_name}, ip={request.META.get('REMOTE_ADDR')})"
        )
        return HttpResponseForbidden(_("Request verification failed."))

    # Parse the request into an InboundMessage
    try:
        message = adapter.parse_request(request)
    except ValueError as exc:
        # Special case: SNS subscription confirmation is handled inside parse
        if "SubscriptionConfirmation" in str(exc):
            return HttpResponse("OK", status=200)
        logger.error(
            f"Failed to parse inbound email webhook "
            f"(adapter={adapter_name}): {exc}"
        )
        return HttpResponseBadRequest(f"Failed to parse request: {exc}")

    # Process the inbound email
    inbound = InboundEmailService.process(message, adapter_name=adapter_name)

    # Return appropriate response
    if inbound.status == "processed":
        return HttpResponse("OK", status=200)
    elif inbound.status == "failed":
        # Still return 200 to prevent the sender from retrying
        # (the error is logged and stored in the InboundEmail record)
        logger.error(
            f"Inbound email processing failed but returning 200 to "
            f"prevent retry: {inbound.error_message}"
        )
        return HttpResponse("Accepted", status=200)
    else:
        return HttpResponse("Accepted", status=200)
