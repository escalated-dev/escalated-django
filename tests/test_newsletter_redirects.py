"""
The newsletter admin redirects to its own named URLs, so it follows wherever
the host includes ``escalated.urls`` (``/support/admin/newsletters/...`` in
the tests), not to a hard-coded ``/admin/newsletters``.
"""

import json

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from escalated.models import Newsletter, NewsletterList, NewsletterTemplate
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def newsletters_on():
    with override_settings(ESCALATED={"enable_newsletters": True, "UI_ENABLED": True, "app_url": "http://testserver"}):
        yield


@pytest.fixture
def client():
    client = Client()
    client.force_login(UserFactory(username="nl_admin", is_staff=True, is_superuser=True))
    return client


def send(client, method, url, body):
    return getattr(client, method)(url, data=json.dumps(body), content_type="application/json")


def test_creating_a_list_redirects_to_it(client):
    response = send(
        client, "post", reverse("escalated:admin_newsletters_lists_index"), {"name": "VIP", "kind": "static"}
    )
    lst = NewsletterList.objects.get()
    assert response.status_code == 302
    assert response["Location"] == reverse("escalated:admin_newsletters_lists_show", args=[lst.id])
    assert response["Location"].startswith("/support/admin/newsletters/lists/")


def test_deleting_a_list_redirects_to_the_lists(client):
    lst = NewsletterList.objects.create(name="Old", kind="static")
    response = client.delete(reverse("escalated:admin_newsletters_lists_show", args=[lst.id]))
    assert response["Location"] == reverse("escalated:admin_newsletters_lists_index")


def test_creating_a_template_redirects_to_the_templates(client):
    response = send(
        client,
        "post",
        reverse("escalated:admin_newsletters_templates_index"),
        {"name": "Monthly", "theme": "default", "body_markdown": "# Hi"},
    )
    assert NewsletterTemplate.objects.count() == 1
    assert response["Location"] == reverse("escalated:admin_newsletters_templates_index")


def test_saving_the_settings_redirects_to_the_settings(client):
    response = send(
        client,
        "put",
        reverse("escalated:admin_newsletters_settings_show"),
        {"default_theme": "default", "rate_limit_per_minute": 60, "batch_size": 50},
    )
    assert response["Location"] == reverse("escalated:admin_newsletters_settings_show")


def test_deleting_a_draft_redirects_to_the_newsletters(client):
    lst = NewsletterList.objects.create(name="All", kind="static")
    nl = Newsletter.objects.create(subject="Hi", from_email="a@example.com", target_list_id=lst.id, status="draft")
    response = client.delete(reverse("escalated:admin_newsletters_show", args=[nl.id]))
    assert response["Location"] == reverse("escalated:admin_newsletters_index")
