"""
Sign-in through the SSO provider chosen in Admin > Settings > SSO (ADR
2026-10-29-configurable-access-features). Every view answers 404 unless
SSO is switched on and the provider it serves is the chosen one. The views
are for guests: the host's own login stays as it is. Every refusal answers a
generic 403 and logs the reason.
"""

import hmac
import logging
import secrets

from django.contrib.auth import get_user_model, login
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotFound
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from escalated.access import feature_enabled, feature_required, forget_two_factor, take_intended_url
from escalated.services.sso_service import SsoService, SsoValidationError, option, truthy

logger = logging.getLogger("escalated")

OAUTH_STATE = "escalated_sso_oauth_state"
OAUTH_PKCE = "escalated_sso_oauth_pkce"
REFUSED = "Single sign-on failed. Contact your administrator."


def _refuse(error):
    logger.warning("Escalated SSO: %s", error)
    return HttpResponseForbidden(REFUSED, content_type="text/plain; charset=utf-8")


@feature_required("sso")
@require_GET
def login_view(request):
    sso = SsoService()
    provider = sso.get_provider()
    try:
        if provider == "saml":
            return redirect(sso.saml_login_url(request))
        if provider == "jwt":
            return redirect(sso.jwt_login_url(request))
        if provider == "oauth":
            started = sso.oauth_start(request)
            request.session[OAUTH_STATE] = started["state"]
            request.session[OAUTH_PKCE] = started["verifier"]
            return redirect(started["url"])
    except SsoValidationError as error:
        return _refuse(error)
    return HttpResponseNotFound()


@feature_required("sso")
@require_GET
def saml_metadata(request):
    sso = SsoService()
    if sso.get_provider() != "saml":
        return HttpResponseNotFound()
    return HttpResponse(sso.saml_metadata(request), content_type="application/samlmetadata+xml")


# The IdP posts here cross-site: the signed, single-use assertion is what
# authenticates the request, not a CSRF token.
@csrf_exempt
@feature_required("sso")
@require_POST
def saml_acs(request):
    sso = SsoService()
    if sso.get_provider() != "saml":
        return HttpResponseNotFound()
    return _sign_in(request, lambda: sso.validate_saml_response(request, request.POST.get("SAMLResponse", "")))


@feature_required("sso")
@require_GET
def oauth_callback(request):
    sso = SsoService()
    if sso.get_provider() != "oauth":
        return HttpResponseNotFound()
    state = str(request.session.pop(OAUTH_STATE, "") or "")
    verifier = str(request.session.pop(OAUTH_PKCE, "") or "")

    def identify():
        if request.GET.get("error"):
            raise SsoValidationError(f"OAuth refused: the provider returned {request.GET['error']}.")
        if not state or not hmac.compare_digest(state, request.GET.get("state", "")):
            raise SsoValidationError("OAuth refused: missing or mismatched state.")
        if not request.GET.get("code") or not verifier:
            raise SsoValidationError("OAuth refused: no authorization code or PKCE verifier.")
        return sso.oauth_identity(request, request.GET["code"], verifier)

    return _sign_in(request, identify)


@csrf_exempt
@feature_required("sso")
@require_http_methods(["GET", "POST"])
def jwt_callback(request):
    sso = SsoService()
    if sso.get_provider() != "jwt":
        return HttpResponseNotFound()
    token = request.POST.get("jwt") or request.GET.get("jwt") or ""
    return _sign_in(request, lambda: sso.validate_jwt(request, token))


def _sign_in(request, identify):
    try:
        user = _resolve(identify())
    except SsoValidationError as error:
        return _refuse(error)
    intended = take_intended_url(request)
    # login() cycles the session key; the user_logged_in signal clears the
    # two-factor mark, so SSO does not skip the challenge.
    login(request, user, backend=_backend())
    forget_two_factor(request)
    logger.info("Escalated SSO: signed in user %s through %s", user.pk, SsoService().get_provider())
    target = intended or option("redirect_to", "ESCALATED_SSO_REDIRECT_TO") or reverse("escalated:agent_dashboard")
    return redirect(target)


def _backend():
    from django.conf import settings

    backends = getattr(settings, "AUTHENTICATION_BACKENDS", None) or ["django.contrib.auth.backends.ModelBackend"]
    return backends[0]


def _resolve(identity):
    """
    The host user for the identity: matched by email (case-insensitive),
    created only with ESCALATED["SSO"]["create_users"]; the asserted role
    replaces the user's Escalated roles only with roles & permissions on and
    ESCALATED["SSO"]["sync_roles"]. SSO never makes anyone an admin or agent.
    """
    model = get_user_model()
    user = model.objects.filter(email__iexact=identity["email"]).first()
    if user is None:
        if not truthy(option("create_users", "ESCALATED_SSO_CREATE_USERS")):
            raise SsoValidationError(
                f"SSO refused: no user has the email [{identity['email']}] and creating users is off."
            )
        name = identity["name"] or identity["email"].split("@")[0]
        fields = {"email": identity["email"]}
        if model.USERNAME_FIELD != "email":
            fields[model.USERNAME_FIELD] = identity["email"]
        if hasattr(model, "first_name"):
            fields["first_name"] = name[:150]
        user = model(**fields)
        user.set_password(secrets.token_urlsafe(48))
        user.save()

    if (
        identity["role"]
        and feature_enabled("roles_permissions")
        and truthy(option("sync_roles", "ESCALATED_SSO_SYNC_ROLES"))
    ):
        from escalated.models import Role

        role = Role.objects.filter(slug=identity["role"]).first()
        if role is not None:
            for current in Role.objects.filter(users=user):
                current.users.remove(user)
            role.users.add(user)
    return user
