"""
ADR 2026-10-29-configurable-access-features: single sign-on is an
install-level switch (ESCALATED["ACCESS"]["sso"] / ESCALATED_SSO). Off, every
SSO route and the SSO settings page answer 404. On, the provider chosen in
Admin > Settings > SSO (SAML, OAuth 2 / OIDC with state and PKCE, or JWT) signs
a matched host user in.
"""

import base64
import hashlib
import hmac
import json
import time
import uuid
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.core.management import call_command
from lxml import etree
from signxml import XMLSigner

from escalated.models import EscalatedSetting, Role
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "saml"
IDP_KEY = (FIXTURES / "idp-test-key.pem").read_text()
IDP_CERT = (FIXTURES / "idp-test-cert.pem").read_text()
IDP_ENTITY = "https://idp.example.test/metadata"
ACS = "http://testserver/support/sso/saml/acs/"
SP_ENTITY = "http://testserver/support/sso/saml/metadata/"
AUD = "https://help.example.test"
SECRET = "shared-jwt-secret-of-enough-length"
REFUSED = b"Single sign-on failed. Contact your administrator."


@pytest.fixture(autouse=True)
def alice(db):
    return UserFactory(username="alice", email="Alice@Example.test")


def turn_on(settings, roles=False, **sso):
    settings.ESCALATED = {
        **settings.ESCALATED,
        "ACCESS": {"sso": True, "roles_permissions": roles},
        "SSO": {"jwt_audience": AUD, **sso},
    }


def configure(**values):
    for key, value in values.items():
        EscalatedSetting.set(key, value)


def signed_in(client):
    return client.session.get("_auth_user_id")


def refused(response):
    return response.status_code == 403 and response.content == REFUSED


# --- Switched off ---------------------------------------------------------------


def test_every_sso_route_and_the_settings_page_answer_404_while_off(client, settings):
    configure(sso_provider="jwt", sso_jwt_secret="x" * 32, sso_url="https://idp.test")
    for url in ("/support/sso/login/", "/support/sso/saml/metadata/", "/support/sso/oauth/callback/?code=c&state=s"):
        assert client.get(url).status_code == 404
    assert client.post("/support/sso/saml/acs/", {"SAMLResponse": "x"}).status_code == 404
    assert client.get("/support/sso/jwt/callback/", {"jwt": "x"}).status_code == 404
    client.force_login(UserFactory(username="boss", is_staff=True, is_superuser=True))
    assert client.get("/support/admin/settings/sso/", HTTP_X_INERTIA="true").status_code == 404


def test_cannot_be_turned_on_from_the_settings_store(client):
    configure(sso="1", **{"access.sso": "1", "ESCALATED_SSO": "1"})
    assert client.get("/support/sso/login/").status_code == 404


# --- Switched on -------------------------------------------------------------------


def test_sign_in_answers_404_while_the_provider_is_none(client, settings):
    turn_on(settings)
    assert client.get("/support/sso/login/").status_code == 404


def test_the_settings_page_masks_secrets_and_lists_the_endpoints(client, settings):
    turn_on(settings)
    configure(sso_provider="jwt", sso_jwt_secret="top-secret", sso_url="https://idp.test/login")
    client.force_login(UserFactory(username="boss", is_staff=True, is_superuser=True))
    page = client.get("/support/admin/settings/sso/", HTTP_X_INERTIA="true").json()
    assert page["component"] == "Escalated/Admin/Settings/SsoSettings"
    assert page["props"]["settings"]["sso_jwt_secret"] == "********"
    assert "top-secret" not in json.dumps(page)
    assert page["props"]["endpoints"] == {
        "login": "http://testserver/support/sso/login/",
        "sp_entity_id": SP_ENTITY,
        "metadata": SP_ENTITY,
        "acs": ACS,
        "oauth_redirect": "http://testserver/support/sso/oauth/callback/",
        "jwt_callback": "http://testserver/support/sso/jwt/callback/",
    }

    # Saving keeps a secret posted back as the mask and refuses an incomplete provider.
    post = lambda body: client.post(  # noqa: E731
        "/support/admin/settings/sso/", data=json.dumps(body), content_type="application/json"
    )
    post({**page["props"]["settings"], "sso_jwt_algorithm": "HS512"})
    assert EscalatedSetting.get("sso_jwt_secret") == "top-secret"
    assert EscalatedSetting.get("sso_jwt_algorithm") == "HS512"
    post({"sso_provider": "saml"})
    assert EscalatedSetting.get("sso_provider") == "jwt"


# --- SAML ------------------------------------------------------------------------------


def iso(offset=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")


def assertion(
    request_id,
    email="alice@example.test",
    issuer=IDP_ENTITY,
    audience=SP_ENTITY,
    recipient=ACS,
    not_on_or_after=None,
    role=None,
):
    until = not_on_or_after or iso(300)
    irt = f' InResponseTo="{request_id}"' if request_id else ""
    role_attr = (
        f'<saml:Attribute Name="role"><saml:AttributeValue>{role}</saml:AttributeValue></saml:Attribute>'
        if role
        else ""
    )
    return (
        f'<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_a{uuid.uuid4().hex}"'
        f' Version="2.0" IssueInstant="{iso()}">'
        f"<saml:Issuer>{issuer}</saml:Issuer>"
        f"<saml:Subject><saml:NameID>{email}</saml:NameID>"
        '<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">'
        f'<saml:SubjectConfirmationData Recipient="{recipient}"{irt} NotOnOrAfter="{until}"/>'
        "</saml:SubjectConfirmation></saml:Subject>"
        f'<saml:Conditions NotBefore="{iso(-60)}" NotOnOrAfter="{until}">'
        f"<saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>"
        "</saml:Conditions><saml:AttributeStatement>"
        f'<saml:Attribute Name="email"><saml:AttributeValue>{email}</saml:AttributeValue></saml:Attribute>'
        f"{role_attr}</saml:AttributeStatement></saml:Assertion>"
    )


def sign(xml, key=IDP_KEY, cert=IDP_CERT):
    signed = XMLSigner(
        signature_algorithm="rsa-sha256",
        digest_algorithm="sha256",
        c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#",
    ).sign(etree.fromstring(xml), key=key.encode(), cert=cert)
    return etree.tostring(signed).decode()


def response(inner, request_id, destination=ACS):
    irt = f' InResponseTo="{request_id}"' if request_id else ""
    return (
        f'<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" ID="_r{uuid.uuid4().hex}"'
        f' Version="2.0" IssueInstant="{iso()}" Destination="{destination}"{irt}>'
        '<samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
        f"{inner}</samlp:Response>"
    )


def other_key_and_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "other-idp")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .sign(key, hashes.SHA256())
    )
    pem_key = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return pem_key.decode(), cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture
def saml(settings):
    turn_on(settings)
    configure(
        sso_provider="saml",
        sso_entity_id=IDP_ENTITY,
        sso_login_url="https://idp.example.test/sso",
        sso_certificate=IDP_CERT,
    )


def start(client):
    res = client.get("/support/sso/login/")
    assert res.status_code == 302
    location = urlparse(res["Location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == "https://idp.example.test/sso"
    request = parse_qs(location.query)["SAMLRequest"][0]
    xml = zlib.decompress(base64.b64decode(request), -15).decode()
    assert f'AssertionConsumerServiceURL="{ACS}"' in xml
    return xml.split(' ID="', 1)[1].split('"', 1)[0]


def post_acs(client, xml):
    return client.post("/support/sso/saml/acs/", {"SAMLResponse": base64.b64encode(xml.encode()).decode()})


def test_saml_signs_in_the_matched_user(client, saml, alice):
    request_id = start(client)
    res = post_acs(client, response(sign(assertion(request_id)), request_id))
    assert res.status_code == 302
    assert res["Location"] == "/support/agent/"
    assert signed_in(client) == str(alice.pk)


def test_saml_serves_sp_metadata(client, saml):
    res = client.get("/support/sso/saml/metadata/")
    assert res.status_code == 200
    assert res["Content-Type"].startswith("application/samlmetadata+xml")
    assert f'entityID="{SP_ENTITY}"' in res.content.decode()
    assert f'Location="{ACS}"' in res.content.decode()


def _another_key(request_id):
    key, cert = other_key_and_cert()
    return response(sign(assertion(request_id), key=key, cert=cert), request_id)


REFUSALS = {
    "no certificate configured": (lambda rid: response(sign(assertion(rid)), rid), {"sso_certificate": ""}),
    "unsigned assertion": (lambda rid: response(assertion(rid), rid), None),
    "signed by another key": (_another_key, None),
    "tampered after signing": (
        lambda rid: response(sign(assertion(rid)).replace("alice@example.test", "mallory@example.test"), rid),
        None,
    ),
    "another Issuer": (lambda rid: response(sign(assertion(rid, issuer="https://evil.test")), rid), None),
    "another Audience": (lambda rid: response(sign(assertion(rid, audience="https://other-sp.test")), rid), None),
    "another Destination": (
        lambda rid: response(sign(assertion(rid)), rid, destination="https://other-sp.test/acs"),
        None,
    ),
    "another Recipient": (lambda rid: response(sign(assertion(rid, recipient="https://other-sp.test/acs")), rid), None),
    "expired": (lambda rid: response(sign(assertion(rid, not_on_or_after=iso(-900))), rid), None),
    "unknown InResponseTo": (lambda rid: response(sign(assertion("_unknown")), "_unknown"), None),
    "no InResponseTo while IdP-initiated sign-in is off": (lambda rid: response(sign(assertion(None)), None), None),
}


@pytest.mark.parametrize("why", list(REFUSALS))
def test_saml_refuses(client, saml, why):
    build, overrides = REFUSALS[why]
    request_id = start(client)
    if overrides:
        configure(**overrides)
    res = post_acs(client, build(request_id))
    assert refused(res), res.content
    assert signed_in(client) is None


def test_saml_refuses_the_same_assertion_twice(client, saml, settings, alice):
    turn_on(settings, allow_idp_initiated=True)
    xml = response(sign(assertion(None)), None)
    assert post_acs(client, xml).status_code == 302
    client.logout()
    assert refused(post_acs(client, xml))
    assert signed_in(client) is None


# --- OAuth 2 / OIDC -----------------------------------------------------------------------


@pytest.fixture
def oauth(settings):
    turn_on(settings)
    configure(
        sso_provider="oauth",
        sso_oauth_authorize_url="https://idp.test/authorize",
        sso_oauth_token_url="https://idp.test/token",
        sso_oauth_userinfo_url="https://idp.test/userinfo",
        sso_oauth_client_id="client-1",
        sso_oauth_client_secret="client-secret",
    )


class FakeIdp:
    """Stands in for the provider's token and userinfo endpoints."""

    def __init__(self, profile=None):
        self.token_body = None
        self.userinfo_auth = None
        self.profile = profile or {"email": "alice@example.test", "name": "Alice"}

    def request(self, session, method, url, data=None, headers=None, **kwargs):
        res = MagicMock()
        res.status_code = 200
        if url.endswith("/token"):
            if isinstance(data, dict):
                self.token_body = {k: [v] for k, v in data.items()}
            else:
                self.token_body = parse_qs(data.decode() if isinstance(data, bytes) else str(data))
            res.json.return_value = {"access_token": "at-123", "token_type": "Bearer", "expires_in": 3600}
        else:
            import requests

            prepared = requests.Request(method, url, headers=headers or {}).prepare()
            if kwargs.get("auth") is not None:
                prepared = kwargs["auth"](prepared)
            self.userinfo_auth = prepared.headers.get("Authorization")
            res.json.return_value = self.profile
        res.raise_for_status = lambda: None
        return res


def oauth_start(client):
    res = client.get("/support/sso/login/")
    assert res.status_code == 302
    return urlparse(res["Location"])


def test_oauth_signs_in_with_state_and_pkce(client, oauth, alice):
    idp = FakeIdp()
    authorize = oauth_start(client)
    query = parse_qs(authorize.query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["http://testserver/support/sso/oauth/callback/"]

    with patch("requests.Session.request", lambda self, method, url, **kw: idp.request(self, method, url, **kw)):
        res = client.get("/support/sso/oauth/callback/", {"code": "the-code", "state": query["state"][0]})
    assert res.status_code == 302
    assert signed_in(client) == str(alice.pk)
    assert idp.token_body["code"] == ["the-code"]
    verifier = idp.token_body["code_verifier"][0]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == query["code_challenge"][0]
    assert idp.userinfo_auth == "Bearer at-123"


def test_oauth_refuses_a_missing_or_mismatched_state_and_an_idp_error(client, oauth):
    oauth_start(client)
    assert refused(client.get("/support/sso/oauth/callback/", {"code": "c"}))
    oauth_start(client)
    assert refused(client.get("/support/sso/oauth/callback/", {"code": "c", "state": "forged"}))
    state = parse_qs(oauth_start(client).query)["state"][0]
    assert refused(client.get("/support/sso/oauth/callback/", {"error": "access_denied", "state": state}))
    assert signed_in(client) is None


# --- JWT ------------------------------------------------------------------------------------


@pytest.fixture
def jwt_sso(settings):
    turn_on(settings)
    configure(
        sso_provider="jwt", sso_url="https://idp.example.test/login", sso_jwt_secret=SECRET, sso_jwt_algorithm="HS256"
    )


def token(claims=None, key=SECRET, algorithm="HS256"):
    payload = {"email": "alice@example.test", "jti": uuid.uuid4().hex, "aud": AUD, "exp": int(time.time()) + 300}
    payload.update(claims or {})
    payload = {k: v for k, v in payload.items() if v is not None}
    return jwt.encode(payload, key, algorithm=algorithm)


def callback(client, value):
    return client.get("/support/sso/jwt/callback/", {"jwt": value})


def test_jwt_starts_at_the_login_url(client, jwt_sso):
    res = client.get("/support/sso/login/")
    assert parse_qs(urlparse(res["Location"]).query)["return_to"] == ["http://testserver/support/sso/jwt/callback/"]


def test_jwt_signs_in_by_get_or_post(client, jwt_sso, alice):
    assert callback(client, token()).status_code == 302
    assert signed_in(client) == str(alice.pk)
    client.logout()
    assert client.post("/support/sso/jwt/callback/", {"jwt": token()}).status_code == 302


def test_jwt_refuses_bad_signature_none_other_algorithm_and_confusion(client, jwt_sso, alice):
    assert refused(callback(client, token(key="another-secret-of-enough-length!!")))
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    body = (
        base64.urlsafe_b64encode(
            json.dumps({"email": "alice@example.test", "jti": "n", "aud": AUD, "exp": int(time.time()) + 60}).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    assert refused(callback(client, f"{header}.{body}."))
    assert refused(callback(client, token(algorithm="HS512")))

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    configure(sso_jwt_algorithm="RS256", sso_jwt_secret=public_pem)
    hs_header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    signature = (
        base64.urlsafe_b64encode(hmac.new(public_pem.encode(), f"{hs_header}.{body}".encode(), hashlib.sha256).digest())
        .rstrip(b"=")
        .decode()
    )
    assert refused(callback(client, f"{hs_header}.{body}.{signature}"))
    assert signed_in(client) is None

    assert callback(client, token(key=private, algorithm="RS256")).status_code == 302
    assert signed_in(client) == str(alice.pk)


def test_jwt_refuses_missing_or_past_exp_wrong_aud_and_missing_or_reused_jti(client, jwt_sso, alice):
    assert refused(callback(client, token({"exp": None})))
    assert refused(callback(client, token({"exp": int(time.time()) - 900})))
    assert refused(callback(client, token({"aud": "https://other.test"})))
    assert refused(callback(client, token({"jti": None})))
    once = token({"jti": "only-once"})
    assert callback(client, once).status_code == 302
    client.logout()
    assert refused(callback(client, once))


def test_unknown_email_refused_unless_creating_users_is_on(client, jwt_sso, settings):
    from django.contrib.auth import get_user_model

    assert refused(callback(client, token({"email": "new@example.test"})))
    turn_on(settings, create_users=True)
    assert callback(client, token({"email": "new@example.test", "name": "New"})).status_code == 302
    assert get_user_model().objects.filter(email="new@example.test").count() == 1


def test_role_mapping_only_with_roles_on_and_sync_roles_on(client, jwt_sso, settings, alice):
    call_command("seed_permissions", verbosity=0)
    light = Role.objects.get(slug="light_agent")

    callback(client, token({"role": "light_agent"}))
    assert not light.users.filter(pk=alice.pk).exists()

    turn_on(settings, sync_roles=True)
    callback(client, token({"role": "light_agent"}))
    assert not light.users.filter(pk=alice.pk).exists()  # roles & permissions is off

    turn_on(settings, roles=True, sync_roles=True)
    callback(client, token({"role": "no-such-role"}))
    assert not Role.objects.filter(users=alice).exists()
    callback(client, token({"role": "light_agent"}))
    assert light.users.filter(pk=alice.pk).exists()
