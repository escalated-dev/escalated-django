"""
The staff API checks the bearer token on every request, whether or not the
host installed escalated.api_middleware.AuthenticateApiToken: the token must
carry the route's ability (`agent` or `admin`, or `*`; abilities are not
hierarchical) and its owner must still be an agent, or an admin for admin
routes. Deleting a ticket is an admin route.
"""

import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from escalated.models import ApiToken, Department, Ticket
from tests.factories import DepartmentFactory, TicketFactory, UserFactory

pytestmark = pytest.mark.django_db

MIDDLEWARE = "escalated.api_middleware.AuthenticateApiToken"

_seq = iter(range(10_000))


@pytest.fixture(params=["without_middleware", "with_middleware"])
def api_client(request, client, settings):
    if request.param == "with_middleware":
        settings.MIDDLEWARE = [*settings.MIDDLEWARE, MIDDLEWARE]
    return client


def _user(kind):
    n = next(_seq)
    if kind == "admin":
        return UserFactory(username=f"tok_admin{n}", is_staff=True)
    user = UserFactory(username=f"tok_{kind}{n}")
    if kind == "agent":
        DepartmentFactory().agents.add(user)
    return user


def _bearer(user, abilities, **kwargs):
    plain = ApiToken.create_token(user, "test", abilities=abilities, **kwargs)["plain_text_token"]
    return {"HTTP_AUTHORIZATION": f"Bearer {plain}"}


def _url(name, *args):
    return reverse(f"escalated:escalated_api:{name}", args=args)


def _delete(client, ticket, headers):
    return client.delete(_url("ticket_destroy", ticket.reference), **headers)


def test_no_token_is_refused(api_client):
    ticket = TicketFactory()
    assert api_client.get(_url("ticket_list")).status_code == 401
    assert api_client.get(_url("ticket_show", ticket.reference)).status_code == 401
    assert _delete(api_client, ticket, {}).status_code == 401
    assert Ticket.objects.filter(pk=ticket.pk).exists()


def test_a_signed_in_session_is_not_a_token(api_client):
    ticket = TicketFactory()
    api_client.force_login(_user("admin"))
    assert api_client.get(_url("ticket_list")).status_code == 401
    assert _delete(api_client, ticket, {}).status_code == 401
    assert Ticket.objects.filter(pk=ticket.pk).exists()


def test_expired_token_is_refused(api_client):
    ticket = TicketFactory()
    headers = _bearer(_user("admin"), ["*"], expires_at=timezone.now() - timedelta(minutes=1))
    response = _delete(api_client, ticket, headers)
    assert response.status_code == 401
    assert json.loads(response.content)["message"] == "Token has expired."
    assert Ticket.objects.filter(pk=ticket.pk).exists()


def test_token_of_a_non_staff_user_is_refused(api_client):
    ticket = TicketFactory()
    headers = _bearer(_user("customer"), ["*"])
    listing = api_client.get(_url("ticket_list"), **headers)
    assert listing.status_code == 403
    assert json.loads(listing.content)["message"] == "User no longer has agent access."
    assert api_client.get(_url("ticket_show", ticket.reference), **headers).status_code == 403
    assert _delete(api_client, ticket, headers).status_code == 403
    assert Ticket.objects.filter(pk=ticket.pk).exists()


def test_token_without_a_staff_ability_is_refused(api_client):
    ticket = TicketFactory()
    headers = _bearer(_user("agent"), ["customer"])
    response = api_client.get(_url("ticket_list"), **headers)
    assert response.status_code == 403
    assert json.loads(response.content)["message"] == "Insufficient permissions."
    assert _delete(api_client, ticket, headers).status_code == 403
    assert Ticket.objects.filter(pk=ticket.pk).exists()


def test_agent_token_reads_but_cannot_delete(api_client):
    ticket = TicketFactory()
    headers = _bearer(_user("agent"), ["agent"])
    assert api_client.get(_url("ticket_show", ticket.reference), **headers).status_code == 200
    response = _delete(api_client, ticket, headers)
    assert response.status_code == 403
    assert json.loads(response.content)["message"] == "Insufficient permissions."
    assert Ticket.objects.filter(pk=ticket.pk).exists()


def test_wildcard_token_of_a_non_admin_agent_cannot_delete(api_client):
    ticket = TicketFactory()
    headers = _bearer(_user("agent"), ["*"])
    assert api_client.get(_url("ticket_show", ticket.reference), **headers).status_code == 200
    assert _delete(api_client, ticket, headers).status_code == 403
    assert Ticket.objects.filter(pk=ticket.pk).exists()


def test_admin_ability_does_not_imply_agent(api_client):
    ticket = TicketFactory()
    headers = _bearer(_user("admin"), ["admin"])
    assert api_client.get(_url("ticket_list"), **headers).status_code == 403
    assert _delete(api_client, ticket, headers).status_code == 200
    assert not Ticket.objects.filter(pk=ticket.pk).exists()


def test_admin_wildcard_token_deletes(api_client):
    ticket = TicketFactory()
    headers = _bearer(_user("admin"), ["*"])
    assert api_client.get(_url("ticket_list"), **headers).status_code == 200
    assert _delete(api_client, ticket, headers).status_code == 200
    assert not Ticket.objects.filter(pk=ticket.pk).exists()


def test_owner_who_left_every_department_is_refused(api_client):
    agent = _user("agent")
    headers = _bearer(agent, ["*"])
    assert api_client.get(_url("ticket_list"), **headers).status_code == 200
    for department in Department.objects.filter(agents=agent):
        department.agents.remove(agent)
    response = api_client.get(_url("ticket_list"), **headers)
    assert response.status_code == 403
    assert json.loads(response.content)["message"] == "User no longer has agent access."


def test_owner_who_lost_admin_cannot_delete(api_client):
    admin = _user("admin")
    DepartmentFactory().agents.add(admin)
    headers = _bearer(admin, ["*"])
    admin.is_staff = False
    admin.save()
    ticket = TicketFactory()
    assert api_client.get(_url("ticket_show", ticket.reference), **headers).status_code == 200
    assert _delete(api_client, ticket, headers).status_code == 403
    assert Ticket.objects.filter(pk=ticket.pk).exists()


def test_other_staff_routes_need_a_staff_token(api_client):
    ticket = TicketFactory()
    headers = _bearer(_user("customer"), ["*"])
    body = {"content_type": "application/json"}
    refused = [
        api_client.post(_url("auth_validate"), **headers),
        api_client.get(_url("dashboard"), **headers),
        api_client.get(_url("agents"), **headers),
        api_client.patch(
            _url("ticket_status", ticket.reference), data=json.dumps({"status": "closed"}), **body, **headers
        ),
        api_client.post(_url("ticket_reply", ticket.reference), data=json.dumps({"body": "x"}), **body, **headers),
    ]
    assert [r.status_code for r in refused] == [403] * len(refused)
    ticket.refresh_from_db()
    assert ticket.status != "closed"


def test_own_profile_routes_need_a_token_but_not_staff(api_client):
    customer = _user("customer")
    assert api_client.get(_url("auth_me")).status_code == 401
    response = api_client.get(_url("auth_me"), **_bearer(customer, ["customer"]))
    assert response.status_code == 200
    assert json.loads(response.content)["data"]["id"] == customer.pk
