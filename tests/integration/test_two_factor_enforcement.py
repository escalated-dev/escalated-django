"""
ADR 2026-10-29-configurable-access-features: two-factor is an install-level
switch (ESCALATED["ACCESS"]["two_factor"] / ESCALATED_TWO_FACTOR). Off, the
enrolment and challenge routes answer 404 and nobody is challenged. On, a staff
user with a confirmed enrolment must pass Auth/TwoFactorChallenge in their
session before any admin or agent view, and admins can require everyone to enrol.
"""

import json
import time

import pyotp
import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from escalated.models import EscalatedSetting, TwoFactor
from tests.factories import ApiTokenFactory, DepartmentFactory, TicketFactory, UserFactory

pytestmark = pytest.mark.django_db

CHALLENGE = "/support/two-factor/challenge/"
ENROL = "/support/admin/settings/two-factor/"
SHARE = "escalated.middleware.EscalatedInertiaShareMiddleware"

_seq = iter(range(10_000))


@pytest.fixture(autouse=True)
def setup(settings):
    cache.clear()
    settings.MIDDLEWARE = [*settings.MIDDLEWARE, SHARE]


def turn_on(settings, **two_factor):
    settings.ESCALATED = {**settings.ESCALATED, "ACCESS": {"two_factor": True}, "TWO_FACTOR": two_factor}


def staff(kind="agent"):
    n = next(_seq)
    if kind == "admin":
        return UserFactory(username=f"tfadmin{n}", is_staff=True, is_superuser=True)
    user = UserFactory(username=f"tfagent{n}")
    DepartmentFactory().agents.add(user)
    return user


def enrol(user, recovery=("AAAA1111-BBBB2222", "CCCC3333-DDDD4444")):
    secret = pyotp.random_base32(32)
    TwoFactor.objects.create(user=user, secret=secret, recovery_codes=list(recovery), confirmed_at=timezone.now())
    return secret


def code(secret, offset=0):
    return pyotp.TOTP(secret).at(int(time.time()) + offset * 30)


def get(client, url):
    return client.get(url, HTTP_X_INERTIA="true")


def post(client, url, data, json_api=False):
    extra = {"HTTP_ACCEPT": "application/json"} if json_api else {"HTTP_X_INERTIA": "true"}
    return client.post(url, data=json.dumps(data), content_type="application/json", **extra)


# --- Switched off (the default) ----------------------------------------------


def test_does_not_challenge_and_hides_the_two_factor_routes_while_off(client):
    user = staff("admin")
    enrol(user)
    client.force_login(user)
    assert get(client, reverse("escalated:agent_dashboard")).status_code == 200
    assert get(client, ENROL).status_code == 404
    assert post(client, ENROL + "setup/", {}).status_code == 404
    assert get(client, CHALLENGE).status_code == 404
    assert post(client, CHALLENGE, {"code": "000000"}).status_code == 404


def test_shares_the_switch_off_and_ignores_the_requirement(client):
    EscalatedSetting.set("two_factor_required", "1")
    client.force_login(staff())
    props = get(client, reverse("escalated:agent_dashboard")).json()["props"]
    assert props["escalated"]["features"]["two_factor"] is False
    assert props["escalated"]["two_factor_required"] is False


def test_cannot_be_turned_on_from_the_settings_store(client):
    for key in ("two_factor", "access.two_factor", "ESCALATED_TWO_FACTOR"):
        EscalatedSetting.set(key, "1")
    user = staff()
    enrol(user)
    client.force_login(user)
    assert get(client, reverse("escalated:agent_dashboard")).status_code == 200


# --- Switched on ---------------------------------------------------------------


def test_sends_an_enrolled_user_to_the_challenge_from_agent_and_admin_pages(client, settings):
    turn_on(settings)
    user = staff("admin")
    enrol(user)
    client.force_login(user)
    for url in (reverse("escalated:agent_dashboard"), reverse("escalated:admin_departments_index")):
        response = get(client, url)
        assert response.status_code == 302
        assert response["Location"] == CHALLENGE
    response = client.get(reverse("escalated:agent_ticket_list"), HTTP_ACCEPT="application/json")
    assert response.status_code == 403
    assert response.json()["two_factor_required"] is True


def test_renders_the_shared_challenge_page_with_the_action(client, settings):
    turn_on(settings)
    user = staff()
    enrol(user)
    client.force_login(user)
    page = get(client, CHALLENGE).json()
    assert page["component"] == "Escalated/Auth/TwoFactorChallenge"
    assert page["props"]["action"] == f"http://testserver{CHALLENGE}"
    assert "error" in page["props"]


def test_accepts_a_valid_code_and_returns_to_the_page_asked_for(client, settings):
    turn_on(settings)
    user = staff()
    secret = enrol(user)
    ticket = TicketFactory()
    client.force_login(user)
    target = reverse("escalated:agent_ticket_show", args=[ticket.pk])

    assert get(client, target)["Location"] == CHALLENGE
    response = post(client, CHALLENGE, {"code": code(secret)})
    assert response.status_code == 303
    assert response["Location"] == target
    assert get(client, target).status_code == 200


def test_refuses_a_wrong_code_with_a_code_error(client, settings):
    turn_on(settings)
    user = staff()
    secret = enrol(user)
    client.force_login(user)
    wrong = str((int(code(secret)) + 1) % 1_000_000).zfill(6)
    response = post(client, CHALLENGE, {"code": wrong}, json_api=True)
    assert response.status_code == 422
    assert response.json()["errors"] == {"code": "That code is not valid."}
    assert get(client, reverse("escalated:agent_dashboard")).status_code == 302


def test_refuses_a_code_that_was_already_used_after_a_new_login(client, settings):
    turn_on(settings)
    user = staff()
    secret = enrol(user)
    once = code(secret)
    client.force_login(user)
    assert post(client, CHALLENGE, {"code": once}).status_code == 303

    client.force_login(user)  # a new login
    response = post(client, CHALLENGE, {"code": once}, json_api=True)
    assert response.status_code == 422
    assert "code" in response.json()["errors"]


def test_accepts_a_recovery_code_once(client, settings):
    turn_on(settings)
    user = staff()
    enrol(user)
    client.force_login(user)
    assert post(client, CHALLENGE, {"recovery_code": "aaaa1111-bbbb2222"}).status_code == 303
    assert get(client, reverse("escalated:agent_dashboard")).status_code == 200

    client.force_login(user)
    response = post(client, CHALLENGE, {"recovery_code": "AAAA1111-BBBB2222"}, json_api=True)
    assert response.status_code == 422
    assert "recovery_code" in response.json()["errors"]
    assert TwoFactor.objects.get(user=user).recovery_codes == ["CCCC3333-DDDD4444"]


def test_throttles_the_verify_route(client, settings):
    turn_on(settings)
    user = staff()
    enrol(user)
    client.force_login(user)
    for _ in range(5):
        post(client, CHALLENGE, {"code": "000000"}, json_api=True)
    assert post(client, CHALLENGE, {"code": "000000"}, json_api=True).status_code == 429


def test_challenges_again_after_a_new_login(client, settings):
    turn_on(settings)
    user = staff()
    secret = enrol(user)
    client.force_login(user)
    post(client, CHALLENGE, {"code": code(secret)})
    assert get(client, reverse("escalated:agent_dashboard")).status_code == 200

    client.force_login(user)
    assert get(client, reverse("escalated:agent_dashboard"))["Location"] == CHALLENGE


def test_does_not_pass_a_session_for_one_user_on_to_another(client, settings):
    turn_on(settings)
    first, second = staff(), staff()
    secret = enrol(first)
    enrol(second)
    client.force_login(first)
    post(client, CHALLENGE, {"code": code(secret)})
    client.force_login(second)
    assert get(client, reverse("escalated:agent_dashboard"))["Location"] == CHALLENGE


def test_does_not_let_an_unchallenged_session_switch_two_factor_off(client, settings):
    turn_on(settings)
    user = staff()
    enrol(user)
    client.force_login(user)
    response = post(client, ENROL + "disable/", {})
    assert response.status_code == 303
    assert response["Location"] == CHALLENGE
    assert TwoFactor.objects.filter(user=user).exists()


def test_lets_an_agent_enrol_with_the_secret_sealed_at_rest(client, settings):
    turn_on(settings)
    agent = staff()
    client.force_login(agent)
    page = get(client, ENROL).json()
    assert page["component"] == "Escalated/Admin/Settings/TwoFactor"
    assert page["props"]["enabled"] is False and page["props"]["required"] is False

    assert post(client, ENROL + "setup/", {}).status_code == 303
    shown = get(client, ENROL).json()["props"]
    data = shown["flash"]["two_factor_setup"]
    assert len(data["recovery_codes"]) == 8
    secret = TwoFactor.objects.get(user=agent).secret
    assert len(secret) >= 32
    assert f"secret={secret}" in data["qr_uri"]
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT secret, recovery_codes FROM {TwoFactor._meta.db_table} WHERE user_id = %s", [agent.pk])
        raw_secret, raw_codes = cursor.fetchone()
    assert secret not in raw_secret
    assert data["recovery_codes"][0] not in str(raw_codes)

    assert post(client, ENROL + "confirm/", {"code": code(secret)}).status_code == 303
    after = get(client, ENROL).json()["props"]
    assert after["enabled"] is True
    assert after["flash"]["two_factor_confirmed"]["recovery_codes"] == data["recovery_codes"]
    # Confirming proves the second factor for this session.
    assert get(client, reverse("escalated:agent_dashboard")).status_code == 200


def test_sends_staff_without_an_enrolment_to_enrol_when_required(client, settings):
    turn_on(settings, REQUIRED=True)
    agent = staff()
    client.force_login(agent)
    assert get(client, reverse("escalated:agent_dashboard"))["Location"] == ENROL
    page = get(client, ENROL).json()
    assert page["props"]["required"] is True
    assert page["props"]["escalated"]["two_factor_required"] is True
    assert post(client, ENROL + "setup/", {}).status_code == 303
    assert TwoFactor.objects.filter(user=agent).exists()


def test_lets_an_admin_require_two_factor_at_runtime_with_a_partial_post(client, settings):
    turn_on(settings)
    EscalatedSetting.set("guest_tickets_enabled", "1")
    admin = staff("admin")
    client.force_login(admin)
    assert get(client, reverse("escalated:agent_dashboard")).status_code == 200

    post(client, reverse("escalated:admin_settings_update"), {"two_factor_required": True})
    assert EscalatedSetting.get("two_factor_required") == "1"
    assert EscalatedSetting.get("guest_tickets_enabled") == "1"
    assert get(client, reverse("escalated:agent_dashboard"))["Location"] == ENROL


def test_does_not_challenge_the_token_api(client, settings):
    from django.contrib.contenttypes.models import ContentType

    turn_on(settings)
    settings.MIDDLEWARE = [*settings.MIDDLEWARE, "escalated.api_middleware.AuthenticateApiToken"]
    user = staff()
    enrol(user)
    token = ApiTokenFactory()
    token.tokenable_content_type = ContentType.objects.get_for_model(user)
    token.tokenable_object_id = user.pk
    token.save()
    response = client.get(
        reverse("escalated:escalated_api:ticket_list"), HTTP_AUTHORIZATION=f"Bearer {token.plain_text}"
    )
    assert response.status_code == 200


def test_reads_an_enrolment_stored_before_secrets_were_sealed(client, settings):
    turn_on(settings)
    user = staff()
    secret = pyotp.random_base32(32)
    enrolment = TwoFactor.objects.create(user=user, secret="x", confirmed_at=timezone.now())
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE {TwoFactor._meta.db_table} SET secret = %s WHERE id = %s", [secret, enrolment.pk])
    client.force_login(user)
    assert post(client, CHALLENGE, {"code": code(secret)}).status_code == 303
    assert get(client, reverse("escalated:agent_dashboard")).status_code == 200


def test_reset_command_removes_an_enrolment():
    user = staff()
    enrol(user)
    call_command("reset_two_factor", user.username)
    assert not TwoFactor.objects.filter(user=user).exists()
