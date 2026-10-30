"""
Single sign-on through the provider an admin picks in Admin > Settings > SSO
(ADR 2026-10-29-configurable-access-features). Crypto is left to maintained
libraries: signxml (XML signatures), Authlib (OAuth 2 / OIDC with PKCE) and
PyJWT.

Every validate method returns ``{"email", "name", "role"}`` or raises
SsoValidationError, whose message is for the log, never for the user.
"""

import base64
import os
import re
import secrets
import time
import uuid
import zlib
from datetime import datetime
from urllib.parse import urlencode

from django.urls import reverse

SAML_ASSERTION_NS = "urn:oasis:names:tc:SAML:2.0:assertion"
SAML_PROTOCOL_NS = "urn:oasis:names:tc:SAML:2.0:protocol"
XMLDSIG_NS = "http://www.w3.org/2000/09/xmldsig#"
BEARER = "urn:oasis:names:tc:SAML:2.0:cm:bearer"
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
TRUE_VALUES = {"1", "true", "yes", "on"}
# How long an AuthnRequest ID stays answerable, in seconds.
SAML_REQUEST_TTL = 600


class SsoValidationError(Exception):
    pass


def _q(ns, name):
    return f"{{{ns}}}{name}"


def _options():
    from django.conf import settings

    return (getattr(settings, "ESCALATED", {}) or {}).get("SSO", {}) or {}


def option(name, env):
    value = _options().get(name)
    return os.environ.get(env) if value is None else value


def truthy(value):
    return value is True or str(value or "").strip().lower() in TRUE_VALUES


class SsoService:
    CONFIG_KEYS = [
        "sso_provider",
        "sso_entity_id",
        "sso_url",
        "sso_login_url",
        "sso_logout_url",
        "sso_metadata_url",
        "sso_certificate",
        "sso_attr_email",
        "sso_attr_name",
        "sso_attr_role",
        "sso_jwt_secret",
        "sso_jwt_algorithm",
        "sso_oauth_authorize_url",
        "sso_oauth_token_url",
        "sso_oauth_userinfo_url",
        "sso_oauth_client_id",
        "sso_oauth_client_secret",
        "sso_oauth_scopes",
    ]
    SECRET_KEYS = ["sso_jwt_secret", "sso_oauth_client_secret"]
    DEFAULTS = {
        "sso_provider": "none",
        "sso_attr_email": "email",
        "sso_attr_name": "name",
        "sso_attr_role": "role",
        "sso_jwt_algorithm": "HS256",
        "sso_oauth_scopes": "openid profile email",
    }
    PROVIDERS = ("saml", "oauth", "jwt")
    JWT_ALGORITHMS = ["HS256", "HS384", "HS512", "RS256", "RS384", "RS512"]

    # ---- Configuration -------------------------------------------------------

    def get_config(self):
        from escalated.models import EscalatedSetting

        stored = dict(EscalatedSetting.objects.filter(key__in=self.CONFIG_KEYS).values_list("key", "value"))
        config = {key: str(stored.get(key, self.DEFAULTS.get(key, "")) or "") for key in self.CONFIG_KEYS}
        for key, default in self.DEFAULTS.items():
            if key not in stored:
                config[key] = default
        # The single URL older versions stored.
        legacy = config["sso_url"].strip()
        if legacy:
            config["sso_login_url"] = config["sso_login_url"] or legacy
            if config["sso_provider"] == "oauth" and not config["sso_oauth_authorize_url"]:
                config["sso_oauth_authorize_url"] = legacy
        return config

    def save_config(self, data):
        from escalated.models import EscalatedSetting

        for key in self.CONFIG_KEYS:
            if key in data:
                EscalatedSetting.set(key, "" if data[key] is None else str(data[key]))

    def get_provider(self):
        from escalated.models import EscalatedSetting

        value = str(EscalatedSetting.get("sso_provider", "none") or "none")
        return value if value in self.PROVIDERS else "none"

    def is_enabled(self):
        from escalated.access import feature_enabled

        return feature_enabled("sso") and self.get_provider() != "none"

    def clock_skew(self):
        try:
            value = int(option("clock_skew", "ESCALATED_SSO_CLOCK_SKEW") or 120)
        except (TypeError, ValueError):
            value = 120
        return 120 if value < 0 else min(value, 300)

    # ---- Endpoints -------------------------------------------------------------

    def url(self, request, name):
        return request.build_absolute_uri(reverse(f"escalated:{name}"))

    def sp_entity_id(self, request):
        return option("sp_entity_id", "ESCALATED_SSO_SP_ENTITY_ID") or self.url(request, "sso_saml_metadata")

    def endpoints(self, request):
        """The URLs an admin gives the identity provider."""
        return {
            "login": self.url(request, "sso_login"),
            "sp_entity_id": self.sp_entity_id(request),
            "metadata": self.url(request, "sso_saml_metadata"),
            "acs": self.url(request, "sso_saml_acs"),
            "oauth_redirect": self.url(request, "sso_oauth_callback"),
            "jwt_callback": self.url(request, "sso_jwt_callback"),
        }

    # ---- SAML ----------------------------------------------------------------------

    def _certificate(self, config):
        raw = (config.get("sso_certificate") or "").strip()
        if not raw:
            raise SsoValidationError("SAML refused: no IdP certificate is configured.")
        if "PRIVATE KEY" in raw:
            raise SsoValidationError("SAML refused: the IdP certificate must not be a private key.")
        if "-----BEGIN" in raw:
            return raw
        body = re.sub(r"\s+", "", raw)
        lines = [body[i : i + 64] for i in range(0, len(body), 64)]
        return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----\n"

    def saml_login_url(self, request):
        """
        The IdP sign-in URL for a new AuthnRequest (HTTP-Redirect binding). Its
        ID is stored server-side (the IdP's cross-site POST back carries no
        SameSite=Lax session cookie) and must come back as InResponseTo.
        """
        from xml.sax.saxutils import quoteattr

        from escalated.models import SsoMessageId

        config = self.get_config()
        self._certificate(config)
        idp_url = config["sso_login_url"].strip()
        if not idp_url:
            raise SsoValidationError("SAML refused: no IdP sign-in URL is configured.")
        request_id = "_" + uuid.uuid4().hex
        SsoMessageId.remember("saml_request", request_id, int(time.time()) + SAML_REQUEST_TTL)
        issued = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        xml = (
            f'<samlp:AuthnRequest xmlns:samlp="{SAML_PROTOCOL_NS}" xmlns:saml="{SAML_ASSERTION_NS}"'
            f' ID="{request_id}" Version="2.0" IssueInstant="{issued}" Destination={quoteattr(idp_url)}'
            ' ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"'
            f" AssertionConsumerServiceURL={quoteattr(self.url(request, 'sso_saml_acs'))}>"
            f"<saml:Issuer>{self._escape(self.sp_entity_id(request))}</saml:Issuer>"
            '<samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified" AllowCreate="true"/>'
            "</samlp:AuthnRequest>"
        )
        compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
        deflated = compressor.compress(xml.encode()) + compressor.flush()
        query = urlencode({"SAMLRequest": base64.b64encode(deflated).decode()})
        return f"{idp_url}{'&' if '?' in idp_url else '?'}{query}"

    def saml_metadata(self, request):
        from xml.sax.saxutils import quoteattr

        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"'
            f" entityID={quoteattr(self.sp_entity_id(request))}>"
            '<md:SPSSODescriptor AuthnRequestsSigned="false" WantAssertionsSigned="true"'
            f' protocolSupportEnumeration="{SAML_PROTOCOL_NS}">'
            "<md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified</md:NameIDFormat>"
            '<md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"'
            f' Location={quoteattr(self.url(request, "sso_saml_acs"))} index="1"/>'
            "</md:SPSSODescriptor></md:EntityDescriptor>"
        )

    @staticmethod
    def _escape(value):
        from xml.sax.saxutils import escape

        return escape(value)

    def validate_saml_response(self, request, saml_response):
        """
        Accepted only when the IdP certificate is configured; the single
        assertion carries a signature by it (a key in KeyInfo is never trusted,
        and the user is read from the signed XML); Issuer is sso_entity_id;
        Audience names the SP entity ID; Destination and the bearer Recipient
        are the ACS URL; the validity windows hold (clock skew); InResponseTo
        names a pending request (or IdP-initiated sign-in is on); and the
        assertion ID is new.
        """
        from lxml import etree

        from escalated.models import SsoMessageId

        config = self.get_config()
        certificate = self._certificate(config)
        entity_id = config["sso_entity_id"].strip()
        if not entity_id:
            raise SsoValidationError("SAML refused: no IdP entity ID is configured.")
        sp_entity_id = self.sp_entity_id(request)
        acs = self.url(request, "sso_saml_acs")
        skew = self.clock_skew()
        now = int(time.time())

        try:
            raw = base64.b64decode(saml_response or "", validate=False)
            parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
            root = etree.fromstring(raw, parser=parser)
        except Exception as exc:
            raise SsoValidationError("SAML refused: malformed XML.") from exc
        if root.findall(f".//{_q(SAML_ASSERTION_NS, 'EncryptedAssertion')}"):
            raise SsoValidationError("SAML refused: encrypted assertions are not supported.")
        assertions = root.findall(f".//{_q(SAML_ASSERTION_NS, 'Assertion')}")
        if root.tag == _q(SAML_ASSERTION_NS, "Assertion"):
            assertions = [root]
        if len(assertions) != 1:
            raise SsoValidationError("SAML refused: the response must carry exactly one assertion.")
        assertion = self._signed_assertion(assertions[0], certificate)

        issuer = (assertion.findtext(_q(SAML_ASSERTION_NS, "Issuer")) or "").strip()
        if issuer != entity_id:
            raise SsoValidationError(f"SAML refused: Issuer [{issuer}] is not [{entity_id}].")

        conditions = assertion.find(_q(SAML_ASSERTION_NS, "Conditions"))
        if conditions is None:
            raise SsoValidationError("SAML refused: the assertion has no Conditions.")
        conditions_until = self._window(conditions, now, skew, "assertion")
        self._audience(conditions, sp_entity_id)

        is_response = root.tag == _q(SAML_PROTOCOL_NS, "Response")
        if is_response and root.get("Destination") != acs:
            raise SsoValidationError(f"SAML refused: Destination [{root.get('Destination')}] is not [{acs}].")

        in_response_to, confirmation_until = self._bearer(assertion, acs, now, skew)
        outer = root.get("InResponseTo") if is_response else None
        if outer and outer != in_response_to:
            raise SsoValidationError("SAML refused: the Response and assertion answer different requests.")
        in_response_to = in_response_to or outer
        if in_response_to:
            if not SsoMessageId.consume("saml_request", in_response_to):
                raise SsoValidationError(f"SAML refused: InResponseTo [{in_response_to}] is not a pending request.")
        elif not truthy(option("allow_idp_initiated", "ESCALATED_SSO_ALLOW_IDP_INITIATED")):
            raise SsoValidationError(
                "SAML refused: unsolicited response (no InResponseTo) and IdP-initiated sign-in is off."
            )

        assertion_id = assertion.get("ID") or ""
        until = max(conditions_until or 0, confirmation_until) + skew
        if not assertion_id or not SsoMessageId.claim("saml_assertion", assertion_id, until):
            raise SsoValidationError(f"SAML refused: assertion [{assertion_id}] was already used.")

        attributes = {}
        for attribute in assertion.iter(_q(SAML_ASSERTION_NS, "Attribute")):
            value = attribute.find(_q(SAML_ASSERTION_NS, "AttributeValue"))
            if attribute.get("Name") and value is not None:
                attributes[attribute.get("Name")] = (value.text or "").strip()
        email = attributes.get(config["sso_attr_email"] or "email", "")
        if not email:
            name_id = (next(assertion.iter(_q(SAML_ASSERTION_NS, "NameID")), None) or etree.Element("x")).text or ""
            email = name_id.strip() if EMAIL.match(name_id.strip()) else ""
        return self._identity(
            email,
            attributes.get(config["sso_attr_name"] or "name", ""),
            attributes.get(config["sso_attr_role"] or "role", ""),
        )

    def _signed_assertion(self, assertion, certificate):
        """
        The assertion as its own signature covers it. Only a signature inside
        the assertion counts: a signed Response around an unsigned assertion
        is refused.
        """
        from lxml import etree
        from signxml import XMLVerifier

        if assertion.find(_q(XMLDSIG_NS, "Signature")) is None:
            raise SsoValidationError("SAML refused: the assertion is not signed.")
        try:
            standalone = etree.fromstring(etree.tostring(assertion))
            result = XMLVerifier().verify(
                standalone,
                x509_cert=certificate,
                expect_references=1,
                ignore_ambiguous_key_info=True,
            )
        except Exception as exc:
            raise SsoValidationError(f"SAML refused: the assertion signature does not verify ({exc}).") from exc
        signed = result.signed_xml
        if signed is None or signed.tag != _q(SAML_ASSERTION_NS, "Assertion"):
            raise SsoValidationError("SAML refused: the signature does not cover the assertion.")
        return signed

    @staticmethod
    def _time(value, attribute):
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
        except ValueError as exc:
            raise SsoValidationError(f"SAML refused: {attribute} is not a time.") from exc

    def _window(self, element, now, skew, what):
        not_before = element.get("NotBefore")
        if not_before and self._time(not_before, "NotBefore") > now + skew:
            raise SsoValidationError(f"SAML refused: the {what} is not yet valid.")
        not_on_or_after = element.get("NotOnOrAfter")
        if not not_on_or_after:
            return None
        until = self._time(not_on_or_after, "NotOnOrAfter")
        if now >= until + skew:
            raise SsoValidationError(f"SAML refused: the {what} has expired.")
        return until

    @staticmethod
    def _audience(conditions, sp_entity_id):
        restrictions = conditions.findall(_q(SAML_ASSERTION_NS, "AudienceRestriction"))
        if not restrictions:
            raise SsoValidationError("SAML refused: the assertion names no Audience.")
        for restriction in restrictions:
            audiences = [(a.text or "").strip() for a in restriction.findall(_q(SAML_ASSERTION_NS, "Audience"))]
            if sp_entity_id not in audiences:
                raise SsoValidationError(f"SAML refused: [{sp_entity_id}] is not an Audience of the assertion.")

    def _bearer(self, assertion, acs, now, skew):
        subject = assertion.find(_q(SAML_ASSERTION_NS, "Subject"))
        bearers = (
            [c for c in subject.findall(_q(SAML_ASSERTION_NS, "SubjectConfirmation")) if c.get("Method") == BEARER]
            if subject is not None
            else []
        )
        if not bearers:
            raise SsoValidationError("SAML refused: no bearer SubjectConfirmation.")
        first = None
        for bearer in bearers:
            try:
                data = bearer.find(_q(SAML_ASSERTION_NS, "SubjectConfirmationData"))
                if data is None:
                    raise SsoValidationError("SAML refused: no SubjectConfirmationData.")
                if data.get("Recipient") != acs:
                    raise SsoValidationError(f"SAML refused: Recipient [{data.get('Recipient')}] is not [{acs}].")
                until = self._window(data, now, skew, "subject confirmation")
                if until is None:
                    raise SsoValidationError("SAML refused: SubjectConfirmationData has no NotOnOrAfter.")
                return data.get("InResponseTo") or None, until
            except SsoValidationError as exc:
                first = first or exc
        raise first

    # ---- OAuth 2 / OIDC ---------------------------------------------------------

    def _oauth_session(self, request, config, **extra):
        from authlib.integrations.requests_client import OAuth2Session

        return OAuth2Session(
            client_id=config["sso_oauth_client_id"],
            client_secret=config["sso_oauth_client_secret"],
            scope=" ".join(s for s in re.split(r"[\s,]+", config["sso_oauth_scopes"]) if s),
            redirect_uri=self.url(request, "sso_oauth_callback"),
            code_challenge_method="S256",
            token_endpoint_auth_method="client_secret_post",
            # The token is used once, at once: a short-lived one must not read as expired.
            leeway=0,
            **extra,
        )

    def oauth_start(self, request):
        """The provider's authorization URL with a fresh state and PKCE verifier."""
        from authlib.common.security import generate_token

        config = self.get_config()
        if not (config["sso_oauth_authorize_url"] and config["sso_oauth_token_url"] and config["sso_oauth_client_id"]):
            raise SsoValidationError("OAuth refused: the provider is not fully configured.")
        verifier = generate_token(64)
        state = secrets.token_urlsafe(32)
        url, _ = self._oauth_session(request, config).create_authorization_url(
            config["sso_oauth_authorize_url"], state=state, code_verifier=verifier
        )
        return {"url": url, "state": state, "verifier": verifier}

    def oauth_identity(self, request, code, verifier):
        """Exchange the code (with the PKCE verifier) server to server, then read userinfo."""
        config = self.get_config()
        try:
            client = self._oauth_session(request, config)
            client.fetch_token(config["sso_oauth_token_url"], code=code, code_verifier=verifier)
            response = client.get(config["sso_oauth_userinfo_url"], headers={"Accept": "application/json"})
            response.raise_for_status()
            profile = response.json()
        except Exception as exc:
            raise SsoValidationError(f"OAuth refused: {exc}") from exc
        if not isinstance(profile, dict):
            profile = {}
        if profile.get("email_verified") in (False, "false", 0, "0"):
            raise SsoValidationError("OAuth refused: the provider says the email is not verified.")

        def claim(name, fallback=None):
            return str(profile.get(name) or (profile.get(fallback) if fallback else "") or "").strip()

        return self._identity(
            claim(config["sso_attr_email"] or "email", "email"),
            claim(config["sso_attr_name"] or "name", "name"),
            claim(config["sso_attr_role"] or "role"),
        )

    # ---- JWT ---------------------------------------------------------------------------

    def jwt_login_url(self, request):
        config = self.get_config()
        url = (config["sso_login_url"] or config["sso_url"]).strip()
        if not url:
            raise SsoValidationError("JWT sign-in has no login URL configured.")
        return f"{url}{'&' if '?' in url else '?'}{urlencode({'return_to': self.url(request, 'sso_jwt_callback')})}"

    def validate_jwt(self, request, token):
        """
        alg must be the configured algorithm (so none and switching are
        refused); exp is required; nbf/iat hold within the skew; aud names this
        install; jti is required and used once.
        """
        import jwt

        from escalated.models import SsoMessageId

        config = self.get_config()
        algorithm = config["sso_jwt_algorithm"] or "HS256"
        secret = config["sso_jwt_secret"]
        if algorithm not in self.JWT_ALGORITHMS:
            raise SsoValidationError(f"JWT refused: unsupported algorithm {algorithm}.")
        if not secret:
            raise SsoValidationError("JWT refused: no secret or public key is configured.")
        audience = option("jwt_audience", "ESCALATED_SSO_JWT_AUDIENCE") or request.build_absolute_uri("/")
        try:
            claims = jwt.decode(
                token or "",
                secret,
                algorithms=[algorithm],
                audience=audience,
                leeway=self.clock_skew(),
                options={"require": ["exp", "jti", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise SsoValidationError(f"JWT refused: {exc}") from exc
        jti = str(claims.get("jti") or "")
        if not jti:
            raise SsoValidationError("JWT refused: no jti claim.")
        if not SsoMessageId.claim("jwt", jti, int(claims["exp"]) + self.clock_skew()):
            raise SsoValidationError(f"JWT refused: jti [{jti}] was already used.")

        def claim(name, fallback=None):
            return str(claims.get(name) or (claims.get(fallback) if fallback else "") or "").strip()

        return self._identity(
            claim(config["sso_attr_email"] or "email", "email"),
            claim(config["sso_attr_name"] or "name", "name"),
            claim(config["sso_attr_role"] or "role"),
        )

    @staticmethod
    def _identity(email, name, role):
        if not EMAIL.match(email or ""):
            raise SsoValidationError("SSO refused: no valid email in the identity.")
        return {"email": email, "name": name or "", "role": role or ""}
