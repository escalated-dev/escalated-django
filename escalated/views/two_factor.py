"""
Two-factor authentication screens (ADR 2026-10-29-configurable-access-features),
404 while ESCALATED["ACCESS"]["two_factor"] is off.

Enrolment (Admin/Settings/TwoFactor) is about the signed-in user's own
account, so every staff user reaches it, not only admins. The challenge
(Auth/TwoFactorChallenge) sits between the host's login and the admin and
agent areas; the staff guard in escalated.access sends people to it.
"""

import json
import logging

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from escalated.access import feature_required, mark_two_factor_passed, take_intended_url, two_factor_passed
from escalated.models import TwoFactor
from escalated.permissions import is_admin, is_agent
from escalated.rendering import render_page
from escalated.services.two_factor_service import TwoFactorService

logger = logging.getLogger("escalated")

FLASH_SESSION_KEY = "escalated_two_factor_flash"
ERRORS_SESSION_KEY = "escalated_two_factor_errors"
VERIFY_LIMIT = 5
VERIFY_WINDOW = 60


def _staff(request):
    user = request.user
    return user.is_authenticated and (is_agent(user) or is_admin(user))


def _data(request):
    if "json" in request.META.get("CONTENT_TYPE", ""):
        try:
            body = json.loads(request.body or b"{}")
            return body if isinstance(body, dict) else {}
        except ValueError:
            return {}
    return request.POST.dict()


def _wants_json(request):
    return request.headers.get("X-Inertia") is None and "json" in request.headers.get("Accept", "")


def _back(request, *, flash=None, errors=None):
    if flash:
        request.session[FLASH_SESSION_KEY] = {**request.session.get(FLASH_SESSION_KEY, {}), **flash}
    if errors:
        request.session[ERRORS_SESSION_KEY] = errors
    response = redirect(reverse("escalated:admin_settings_two_factor"))
    response.status_code = 303
    return response


# ---- Enrolment ---------------------------------------------------------------


@feature_required("two_factor")
@login_required
def settings_two_factor(request):
    if not _staff(request):
        return HttpResponseForbidden("Agent access required.")
    two_factor = TwoFactor.objects.filter(user=request.user).first()
    props = {
        "enabled": bool(two_factor and two_factor.is_confirmed()),
        "pending": bool(two_factor and not two_factor.is_confirmed()),
        "required": TwoFactorService.required(),
        "flash": request.session.pop(FLASH_SESSION_KEY, {}),
        "errors": request.session.pop(ERRORS_SESSION_KEY, {}),
    }
    return render_page(request, "Escalated/Admin/Settings/TwoFactor", props=props)


@feature_required("two_factor")
@login_required
def two_factor_setup(request):
    if not _staff(request):
        return HttpResponseForbidden("Agent access required.")
    if request.method != "POST":
        return HttpResponse(status=405)
    if TwoFactorService.confirmed_for(request.user):
        return _back(request, flash={"error": "Two-factor authentication is already enabled. Disable it first."})

    service = TwoFactorService()
    TwoFactor.objects.filter(user=request.user, confirmed_at__isnull=True).delete()
    secret = service.generate_secret()
    recovery_codes = service.generate_recovery_codes()
    TwoFactor.objects.create(user=request.user, secret=secret, recovery_codes=recovery_codes)
    data = {"qr_uri": service.generate_qr_uri(secret, request.user.email), "recovery_codes": recovery_codes}
    if _wants_json(request):
        return JsonResponse(data)
    return _back(request, flash={"two_factor_setup": data})


@feature_required("two_factor")
@login_required
def two_factor_confirm(request):
    if not _staff(request):
        return HttpResponseForbidden("Agent access required.")
    if request.method != "POST":
        return HttpResponse(status=405)
    code = str(_data(request).get("code", "")).strip()
    two_factor = TwoFactor.objects.filter(user=request.user, confirmed_at__isnull=True).first()
    if len(code) != 6 or two_factor is None or not TwoFactorService().verify_and_consume(two_factor, code):
        message = "No pending two-factor setup found." if two_factor is None else "Invalid verification code."
        if _wants_json(request):
            return JsonResponse({"errors": {"code": message}}, status=422)
        return _back(request, errors={"code": message})

    two_factor.confirmed_at = timezone.now()
    two_factor.save(update_fields=["confirmed_at", "updated_at"])
    # The code just entered proves the second factor for this session.
    mark_two_factor_passed(request, request.user)
    data = {"recovery_codes": list(two_factor.recovery_codes or [])}
    if _wants_json(request):
        return JsonResponse({"enabled": True, **data})
    return _back(request, flash={"success": "Two-factor authentication enabled.", "two_factor_confirmed": data})


@feature_required("two_factor")
@login_required
def two_factor_disable(request):
    if not _staff(request):
        return HttpResponseForbidden("Agent access required.")
    if request.method != "POST":
        return HttpResponse(status=405)
    TwoFactor.objects.filter(user=request.user).delete()
    if _wants_json(request):
        return JsonResponse({"enabled": False})
    return _back(request, flash={"success": "Two-factor authentication disabled."})


# ---- Challenge -----------------------------------------------------------------


def _home(request):
    if is_agent(request.user):
        return reverse("escalated:agent_dashboard")
    return reverse("escalated:admin_reports")


def _leave(request, intended=None):
    response = redirect(intended or take_intended_url(request) or _home(request))
    if request.method != "GET":
        response.status_code = 303
    return response


def _throttled(request):
    bucket = int(timezone.now().timestamp()) // VERIFY_WINDOW
    key = f"escalated:two_factor_verify:{request.user.pk}:{bucket}"
    if cache.add(key, 1, VERIFY_WINDOW + 5):
        return False
    try:
        hits = cache.incr(key)
    except ValueError:
        cache.set(key, 1, VERIFY_WINDOW + 5)
        hits = 1
    return hits > VERIFY_LIMIT


@feature_required("two_factor")
@login_required
def challenge(request):
    if not _staff(request):
        return HttpResponseForbidden("Agent access required.")
    enrolment = TwoFactorService.confirmed_for(request.user)

    if request.method != "POST":
        if enrolment is None or two_factor_passed(request, request.user):
            return _leave(request)
        props = {
            "action": request.build_absolute_uri(reverse("escalated:two_factor_challenge")),
            "error": "",
            "errors": request.session.pop(ERRORS_SESSION_KEY, {}),
        }
        return render_page(request, "Escalated/Auth/TwoFactorChallenge", props=props)

    if _throttled(request):
        response = HttpResponse("Too many attempts. Please try again later.", status=429)
        response["Retry-After"] = str(VERIFY_WINDOW)
        return response
    if enrolment is None:
        return _leave(request)

    data = _data(request)
    recovery = str(data.get("recovery_code") or "")
    code = str(data.get("code") or "")
    service = TwoFactorService()
    if recovery.strip():
        field, passed = "recovery_code", len(recovery) <= 64 and service.use_recovery_code(enrolment, recovery)
    else:
        field, passed = "code", len(code) <= 16 and service.verify_and_consume(enrolment, code)

    if not passed:
        logger.info("Escalated: two-factor challenge failed for user %s", request.user.pk)
        message = "That recovery code is not valid." if field == "recovery_code" else "That code is not valid."
        if _wants_json(request):
            return JsonResponse({"message": message, "errors": {field: message}}, status=422)
        request.session[ERRORS_SESSION_KEY] = {field: message}
        response = redirect(reverse("escalated:two_factor_challenge"))
        response.status_code = 303
        return response

    intended = take_intended_url(request)
    request.session.cycle_key()
    mark_two_factor_passed(request, request.user)
    return _leave(request, intended)
