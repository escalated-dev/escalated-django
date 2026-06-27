"""
Integration tests for the general JSON API auth endpoints (host-callback).
"""

import json

import pytest
from django.test import RequestFactory, override_settings

from escalated.views import api_auth


@pytest.fixture
def rf():
    return RequestFactory()


def _post(rf, path="/auth/login/", body=None, token=None):
    request = rf.post(path, data=json.dumps(body or {}), content_type="application/json")
    if token:
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return request


class TestApiAuthLogin:
    def test_501_when_unconfigured(self, rf):
        with override_settings(ESCALATED={}):
            resp = api_auth.api_auth_login(_post(rf))
        assert resp.status_code == 501

    def test_delegates_to_authenticator(self, rf):
        def authenticator(params):
            return {"token": "abc", "email": params.get("email")}

        with override_settings(ESCALATED={"API_AUTHENTICATOR": authenticator}):
            resp = api_auth.api_auth_login(_post(rf, body={"email": "a@b.com"}))

        assert resp.status_code == 200
        assert json.loads(resp.content) == {"data": {"token": "abc", "email": "a@b.com"}}

    def test_401_when_callback_returns_falsy(self, rf):
        with override_settings(ESCALATED={"API_AUTHENTICATOR": lambda params: None}):
            resp = api_auth.api_auth_login(_post(rf))
        assert resp.status_code == 401


class TestApiAuthLogout:
    def test_always_succeeds_when_unconfigured(self, rf):
        with override_settings(ESCALATED={}):
            resp = api_auth.api_auth_logout(_post(rf, path="/auth/logout/"))
        assert resp.status_code == 200
        assert json.loads(resp.content) == {"data": {"success": True}}

    def test_forwards_token_to_callback(self, rf):
        seen = {}

        def logout(token):
            seen["token"] = token

        with override_settings(ESCALATED={"API_LOGOUT": logout}):
            resp = api_auth.api_auth_logout(_post(rf, path="/auth/logout/", token="tok123"))

        assert resp.status_code == 200
        assert seen["token"] == "tok123"


class TestApiAuthMe:
    def test_returns_request_user(self, rf):
        request = rf.get("/auth/me/")
        request.user = type(
            "U",
            (),
            {"pk": 7, "email": "u@e.com", "get_full_name": lambda self: "Pat"},
        )()

        resp = api_auth.api_auth_me(request)

        assert resp.status_code == 200
        assert json.loads(resp.content)["data"] == {"id": 7, "name": "Pat", "email": "u@e.com"}


def test_login_is_public():
    assert getattr(api_auth.api_auth_login, "_escalated_api_public", False) is True


def test_me_is_not_public():
    assert getattr(api_auth.api_auth_me, "_escalated_api_public", False) is False
