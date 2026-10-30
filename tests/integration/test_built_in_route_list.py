"""The shared frontend's ``route()`` names, served by this package.

The shared pages (``@escalated-dev/escalated``) build every link and form
action with Ziggy's ``route('escalated....', params)``. A name the page cannot
resolve renders as ``#``: the button is there and does nothing. Escalated now
shares the table itself, as the ``ziggy`` Inertia prop in the shape ziggy-js
reads, and ships a small ``route()`` for hosts that do not run Ziggy.

These tests hold the table to the frontend's list (tests/fixtures/
frontend-route-names.txt) and to the real URLconf: every uri must resolve
through Django's router, wherever the host mounts the package.
"""

import json
import uuid
from pathlib import Path

import pytest
from django.template import Context, Template
from django.test import Client, override_settings
from django.urls import Resolver404, resolve

from escalated.models import Department
from escalated.route_list import ROUTES, escalated_routes
from tests.factories import DepartmentFactory, TicketFactory, UserFactory

NAMES = Path(__file__).resolve().parent.parent / "fixtures" / "frontend-route-names.txt"

# Names the frontend calls that this backend has no screen or endpoint for.
# Each is a missing feature, not a missing mapping: route() returns '#' for
# them until the feature is ported.
NOT_SERVED = {
    # Agents cannot snooze here; only the admin ticket screen has it.
    "escalated.agent.tickets.snooze",
    "escalated.agent.tickets.unsnooze",
    # Only per-workflow logs exist (admin/workflows/<id>/logs/), no global log page.
    "escalated.admin.workflows.logs",
}

# Views that already tell PUT/PATCH/DELETE apart themselves.
NATIVE_VERB_VIEWS = {
    "admin_skills_update",
    "admin_skills_destroy",
    "admin_workflow_update",
    "admin_users_role",
    "admin_users_roles",
}

INERTIA = {"HTTP_X_INERTIA": "true"}


def frontend_names():
    lines = NAMES.read_text(encoding="utf-8").splitlines()
    return sorted({line.strip() for line in lines if line.strip() and not line.startswith("#")})


def concrete(uri, ticket):
    """A real path for a uri template: placeholders filled with plausible values."""
    path = "/" + uri
    for name, value in {
        "ticket": ticket.reference,
        "jobId": str(uuid.uuid4()),
        "platform": "zendesk",
        "slug": "some-slug",
        "token": "a-guest-token",
    }.items():
        path = path.replace("{" + name + "}", value)
    while "{" in path:
        start = path.index("{")
        path = path[:start] + "1" + path[path.index("}", start) + 1 :]
    return path


def test_every_frontend_name_is_served_or_explicitly_not():
    routes = escalated_routes()

    unaccounted = [name for name in frontend_names() if name not in routes and name not in NOT_SERVED]
    assert unaccounted == [], "route() names with no mapping and no reason:\n  " + "\n  ".join(unaccounted)

    stale = sorted(NOT_SERVED & set(routes))
    assert stale == [], f"listed as not served, but mapped: {stale}"


def test_uris_are_ziggy_shaped():
    for name, route in escalated_routes().items():
        assert not route["uri"].startswith("/"), name
        assert route["methods"], name
        assert set(route["methods"]) <= {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}, name


@pytest.mark.django_db
def test_every_uri_resolves_through_the_router():
    ticket = TicketFactory()
    unresolved = []
    for name, route in escalated_routes().items():
        if name == "login":
            continue
        try:
            match = resolve(concrete(route["uri"], ticket))
        except Resolver404:
            unresolved.append(f"{name}: /{route['uri']}")
            continue
        assert match.namespace == "escalated", name
    assert unresolved == [], "uris the URLconf does not serve:\n  " + "\n  ".join(unresolved)


@pytest.mark.django_db
def test_every_declared_verb_reaches_the_view():
    """A PUT to a view that only checks for POST renders the edit page instead of saving."""
    ticket = TicketFactory()
    wrong = []
    for name, route in escalated_routes().items():
        verbs = set(route["methods"]) - {"GET", "HEAD", "POST"}
        if not verbs or name == "login":
            continue
        view = resolve(concrete(route["uri"], ticket)).func
        accepted = set(getattr(view, "escalated_accepts", ()))
        if ROUTES[name].url_name in NATIVE_VERB_VIEWS:
            continue
        if not verbs <= accepted:
            wrong.append(f"{name}: {sorted(verbs - accepted)}")
    assert wrong == [], "verbs the view would ignore:\n  " + "\n  ".join(wrong)


def test_honours_the_hosts_mount_point():
    assert escalated_routes()["escalated.agent.tickets.show"]["uri"] == "support/agent/tickets/{ticket}/"

    with override_settings(ROOT_URLCONF="tests.urls_helpdesk"):
        routes = escalated_routes()

    assert routes["escalated.agent.tickets.show"]["uri"] == "helpdesk/agent/tickets/{ticket}/"
    assert routes["escalated.admin.custom-objects.records.update"]["uri"] == (
        "helpdesk/admin/custom-objects/{custom_object}/records/{record}/update/"
    )
    assert routes["escalated.admin.import.progress"]["uri"] == "helpdesk/admin/import/progress/{jobId}/"


def test_parameter_names_match_what_the_pages_pass_by_name():
    routes = escalated_routes()
    # route('escalated.admin.reports.agent-detail', { id: ... })
    assert "{id}" in routes["escalated.admin.reports.agent-detail"]["uri"]
    assert routes["escalated.admin.tickets.pin"]["uri"].endswith("{ticket}/{reply}/pin/")


@override_settings(LOGIN_URL="/accounts/sign-in/")
def test_login_is_the_hosts_login_url():
    assert escalated_routes()["login"] == {"uri": "accounts/sign-in/", "methods": ["GET", "HEAD"]}


@override_settings(ESCALATED={"ROUTES": {"login": "/auth/login", "escalated.admin.reports": None}})
def test_routes_setting_overrides_single_names():
    routes = escalated_routes()

    assert routes["login"]["uri"] == "auth/login"
    assert "escalated.admin.reports" not in routes
    assert "escalated.agent.tickets.index" in routes


@pytest.mark.django_db
def test_ziggy_prop_is_on_every_escalated_page(client):
    agent = UserFactory(username="ziggy-agent", is_staff=True, is_superuser=True)
    client.force_login(agent)

    response = client.get("/support/agent/tickets/", **INERTIA)

    assert response.status_code == 200
    ziggy = json.loads(response.content)["props"]["ziggy"]
    assert ziggy["url"] == "http://testserver"
    assert ziggy["port"] is None
    assert ziggy["defaults"] == {}
    assert ziggy["location"] == "http://testserver/support/agent/tickets/"
    assert ziggy["routes"]["escalated.agent.tickets.show"] == {
        "uri": "support/agent/tickets/{ticket}/",
        "methods": ["GET", "HEAD"],
    }


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.urls_helpdesk")
def test_ziggy_prop_follows_the_mount_point(client):
    client.force_login(UserFactory(username="ziggy-helpdesk", is_staff=True, is_superuser=True))

    response = client.get("/helpdesk/agent/tickets/", **INERTIA)

    assert response.status_code == 200
    routes = json.loads(response.content)["props"]["ziggy"]["routes"]
    assert routes["escalated.admin.tickets.index"]["uri"] == "helpdesk/admin/tickets/"


class HostZiggyMiddleware:
    """A host that shares its own Ziggy table (e.g. from ziggy's generator)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from inertia import share

        share(
            request,
            ziggy={
                "url": "https://host.example",
                "routes": {
                    "escalated.agent.tickets.index": {"uri": "desk/queue", "methods": ["GET", "HEAD"]},
                    "home": {"uri": "", "methods": ["GET", "HEAD"]},
                },
            },
        )
        return self.get_response(request)


@pytest.mark.django_db
def test_a_host_shared_ziggy_table_wins_name_by_name():
    stack = [
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "tests.integration.test_built_in_route_list.HostZiggyMiddleware",
    ]
    with override_settings(MIDDLEWARE=stack):
        client = Client()
        client.force_login(UserFactory(username="ziggy-host", is_staff=True, is_superuser=True))
        response = client.get("/support/agent/tickets/", **INERTIA)

    ziggy = json.loads(response.content)["props"]["ziggy"]
    assert ziggy["url"] == "https://host.example"
    assert ziggy["routes"]["escalated.agent.tickets.index"]["uri"] == "desk/queue"
    assert ziggy["routes"]["home"]["uri"] == ""
    # Names the host did not map still come from the built-in table.
    assert ziggy["routes"]["escalated.agent.tickets.show"]["uri"] == "support/agent/tickets/{ticket}/"


@pytest.mark.django_db
def test_tickets_are_addressed_by_reference_as_the_pages_do(client):
    """route('escalated.agent.tickets.show', ticket.reference)."""
    client.force_login(UserFactory(username="ziggy-ref", is_staff=True, is_superuser=True))
    ticket = TicketFactory()

    by_reference = client.get(f"/support/agent/tickets/{ticket.reference}/", **INERTIA)
    by_id = client.get(f"/support/agent/tickets/{ticket.pk}/", **INERTIA)
    unknown = client.get("/support/agent/tickets/NOPE-000000/", **INERTIA)

    assert by_reference.status_code == 200
    assert json.loads(by_reference.content)["props"]["ticket"]["reference"] == ticket.reference
    assert by_id.status_code == 200
    assert unknown.status_code == 404


@pytest.mark.django_db
def test_update_by_put_and_destroy_by_delete_as_the_pages_send_them(client):
    client.force_login(UserFactory(username="ziggy-verbs", is_staff=True, is_superuser=True))
    department = DepartmentFactory(name="Before")
    routes = escalated_routes()

    update = "/" + routes["escalated.admin.departments.update"]["uri"].replace("{department}", str(department.pk))
    response = client.put(update, data=json.dumps({"name": "After"}), content_type="application/json")
    assert response.status_code == 302
    department.refresh_from_db()
    assert department.name == "After"

    destroy = "/" + routes["escalated.admin.departments.destroy"]["uri"].replace("{department}", str(department.pk))
    response = client.delete(destroy)
    assert response.status_code == 302
    assert not Department.objects.filter(pk=department.pk).exists()


def test_route_helper_template_tag():
    html = Template("{% load escalated_routes %}{% escalated_route_helper %}").render(Context({}))

    assert html.startswith("<script>")
    assert "typeof window.route === 'function'" in html
    assert "window.Ziggy" in html
    assert "page.props.ziggy" in html or "props.ziggy" in html


def test_route_helper_template_tag_with_nonce():
    html = Template('{% load escalated_routes %}{% escalated_route_helper nonce="abc" %}').render(Context({}))

    assert html.startswith('<script nonce="abc">')
