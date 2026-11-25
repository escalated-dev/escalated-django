"""ESCALATED["CUSTOMER_ROUTE_DECORATORS"]: extra guards on the customer portal
and customer knowledge base, for staff-only installs (B3, ecom-core
2026-11-24)."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseForbidden

from escalated.models import EscalatedSetting
from tests.factories import ArticleFactory, TicketFactory, UserFactory

pytestmark = pytest.mark.django_db

STAFF_ONLY = "escalated.permissions.staff_only"


@pytest.fixture
def portal(db):
    EscalatedSetting.set("knowledge_base_enabled", "1")
    EscalatedSetting.set("knowledge_base_public", "1")
    customer = UserFactory(username="customer")
    ticket = TicketFactory(requester=customer)
    article = ArticleFactory(status="published")
    return customer, ticket, article


def _customer_urls(ticket, article):
    return [
        "/support/tickets/",
        "/support/tickets/create/",
        f"/support/tickets/{ticket.pk}/",
        "/support/kb/",
        f"/support/kb/{article.slug}/",
    ]


def test_by_default_any_signed_in_user_reaches_the_portal_and_kb(urls_with, client, portal):
    urls_with()
    customer, ticket, article = portal
    client.force_login(customer)
    for url in _customer_urls(ticket, article):
        assert client.get(url, HTTP_X_INERTIA="true").status_code == 200, url


def test_staff_only_refuses_a_signed_in_user_who_is_not_staff(urls_with, client, portal):
    urls_with(CUSTOMER_ROUTE_DECORATORS=[STAFF_ONLY])
    customer, ticket, article = portal
    client.force_login(customer)
    for url in _customer_urls(ticket, article):
        assert client.get(url, HTTP_X_INERTIA="true").status_code == 403, url
    store = client.post("/support/tickets/store/", {"subject": "x", "description": "y"}, HTTP_X_INERTIA="true")
    assert store.status_code == 403
    feedback = client.post(f"/support/kb/{article.slug}/feedback/", {"helpful": "1"}, HTTP_X_INERTIA="true")
    assert feedback.status_code == 403


def test_staff_only_sends_visitors_to_log_in_even_on_a_public_kb(urls_with, client, portal):
    urls_with(CUSTOMER_ROUTE_DECORATORS=[STAFF_ONLY])
    _, _, article = portal
    response = client.get(f"/support/kb/{article.slug}/", HTTP_X_INERTIA="true")
    assert response.status_code == 302
    assert "next=" in response["Location"]


def test_staff_only_lets_agents_and_admins_through(urls_with, client, portal, agent_user, admin_user):
    urls_with(CUSTOMER_ROUTE_DECORATORS=[STAFF_ONLY])
    for staff in (agent_user, admin_user):
        client.force_login(staff)
        assert client.get("/support/tickets/", HTTP_X_INERTIA="true").status_code == 200
        assert client.get("/support/kb/", HTTP_X_INERTIA="true").status_code == 200


def deny_all(view):
    return lambda request, *args, **kwargs: HttpResponseForbidden("no")


def test_any_view_decorator_or_its_dotted_path_works(urls_with, client, portal, agent_user):
    urls_with(CUSTOMER_ROUTE_DECORATORS=[deny_all])
    customer, ticket, article = portal
    client.force_login(customer)
    assert client.get("/support/tickets/", HTTP_X_INERTIA="true").status_code == 403

    urls_with(CUSTOMER_ROUTE_DECORATORS=[f"{__name__}.deny_all"])
    assert client.get("/support/kb/", HTTP_X_INERTIA="true").status_code == 403
    # Agent pages are not customer routes.
    client.force_login(agent_user)
    assert client.get("/support/agent/", HTTP_X_INERTIA="true").status_code == 200


def test_a_bad_entry_fails_loudly(urls_with):
    with pytest.raises(ImproperlyConfigured):
        urls_with(CUSTOMER_ROUTE_DECORATORS=["escalated.no_such_module.guard"])
