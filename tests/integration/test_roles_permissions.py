"""
ADR 2026-10-29-configurable-access-features: roles & permissions is an
install-level switch (ESCALATED["ACCESS"]["roles_permissions"] /
ESCALATED_ROLES_PERMISSIONS). Off, the host gates decide everything and the
roles screens answer 404. On, every admin, agent and staff API view also needs
its permission from the user's Escalated roles.
"""

import json
from fnmatch import fnmatchcase

import pytest
from django.core.management import call_command
from django.urls import get_resolver, reverse

from escalated import access
from escalated.management.commands.seed_permissions import PERMISSIONS
from escalated.models import Department, Permission, Role, Ticket
from tests.factories import ApiTokenFactory, DepartmentFactory, TicketFactory, UserFactory

pytestmark = pytest.mark.django_db

SHARE = "escalated.middleware.EscalatedInertiaShareMiddleware"
API = "escalated.api_middleware.AuthenticateApiToken"


@pytest.fixture(autouse=True)
def seeded(settings):
    call_command("seed_permissions", verbosity=0)
    settings.MIDDLEWARE = [*settings.MIDDLEWARE, SHARE]


def enforce(settings, on=True):
    settings.ESCALATED = {**settings.ESCALATED, "ACCESS": {"roles_permissions": on}}


_seq = iter(range(10_000))


def staff(kind, role=None):
    n = next(_seq)
    if kind == "admin":
        user = UserFactory(username=f"admin{n}", is_staff=True, is_superuser=True)
    else:
        user = UserFactory(username=f"agent{n}")
        DepartmentFactory().agents.add(user)
    if isinstance(role, str):
        Role.objects.get(slug=role).users.add(user)
    elif isinstance(role, list):
        custom = Role.objects.create(name=f"Custom {n}", slug=f"custom-{n}")
        custom.permissions.set(Permission.objects.filter(slug__in=role))
        custom.users.add(user)
    return user


def inertia_get(client, url):
    return client.get(url, HTTP_X_INERTIA="true")


def post(client, url, data):
    return client.post(url, data=json.dumps(data), content_type="application/json", HTTP_X_INERTIA="true")


# --- Switched off (the default) ----------------------------------------------


def test_is_off_by_default():
    assert access.feature_enabled("roles_permissions") is False


def test_hides_the_roles_screens(client):
    client.force_login(staff("admin", "admin"))
    assert inertia_get(client, reverse("escalated:admin_roles_index")).status_code == 404
    assert inertia_get(client, reverse("escalated:admin_roles_create")).status_code == 404
    before = Role.objects.count()
    assert post(client, reverse("escalated:admin_roles_create"), {"name": "X"}).status_code == 404
    assert Role.objects.count() == before


def test_lets_the_gates_alone_decide(client):
    agent = staff("agent", "light_agent")
    other = staff("agent")
    ticket = TicketFactory()
    client.force_login(agent)
    response = post(client, reverse("escalated:agent_ticket_assign", args=[ticket.pk]), {"agent_id": other.pk})
    assert response.status_code in (302, 303)
    ticket.refresh_from_db()
    assert ticket.assigned_to_id == other.pk

    client.force_login(staff("admin"))
    assert inertia_get(client, reverse("escalated:admin_departments_index")).status_code == 200


def test_shares_the_switches_off_and_a_wildcard_permission_set_for_staff(client):
    client.force_login(staff("admin"))
    props = inertia_get(client, reverse("escalated:admin_departments_index")).json()["props"]
    assert props["escalated"]["features"]["roles_permissions"] is False
    assert props["escalated"]["features"]["two_factor"] is False
    assert props["escalated"]["features"]["sso"] is False
    assert props["escalated"]["permissions"] == ["*"]


def test_cannot_be_turned_on_from_the_settings_store(client):
    from escalated.models import EscalatedSetting

    for key in ("roles_permissions", "access.roles_permissions", "ESCALATED_ROLES_PERMISSIONS"):
        EscalatedSetting.set(key, "1")
    client.force_login(staff("admin", "admin"))
    assert inertia_get(client, reverse("escalated:admin_roles_index")).status_code == 404


def test_newsletter_permissions_apply_only_while_on(rf, settings):
    from escalated.newsletter_permissions import user_has_newsletter_permission

    admin = staff("admin")
    assert user_has_newsletter_permission(admin, "newsletters.send") is True
    enforce(settings)
    assert user_has_newsletter_permission(admin, "newsletters.manage") is False
    assert user_has_newsletter_permission(staff("admin", "admin"), "newsletters.send") is True


# --- Switched on --------------------------------------------------------------


def test_shows_the_roles_screens_to_a_role_manager(client, settings):
    enforce(settings)
    client.force_login(staff("admin", "admin"))
    response = inertia_get(client, reverse("escalated:admin_roles_index"))
    assert response.status_code == 200
    slugs = {role["slug"] for role in response.json()["props"]["roles"]}
    assert {"admin", "agent", "light_agent"} <= slugs


def test_grants_nothing_to_an_admin_without_a_role(client, settings):
    enforce(settings)
    client.force_login(staff("admin"))
    assert inertia_get(client, reverse("escalated:admin_departments_index")).status_code == 403
    assert inertia_get(client, reverse("escalated:admin_roles_index")).status_code == 403
    assert post(client, reverse("escalated:admin_settings_update"), {}).status_code == 403


def test_lets_an_admin_with_the_admin_role_through(client, settings):
    enforce(settings)
    client.force_login(staff("admin", "admin"))
    assert inertia_get(client, reverse("escalated:admin_departments_index")).status_code == 200
    assert inertia_get(client, reverse("escalated:admin_settings")).status_code == 200


def test_checks_admin_reads_and_writes_against_separate_permissions(client, settings):
    enforce(settings)
    client.force_login(staff("admin", ["department.view"]))
    assert inertia_get(client, reverse("escalated:admin_departments_index")).status_code == 200
    before = Department.objects.count()
    assert post(client, reverse("escalated:admin_departments_create"), {"name": "Billing"}).status_code == 403
    assert Department.objects.count() == before
    assert inertia_get(client, reverse("escalated:admin_webhooks_index")).status_code == 403


def test_shares_the_users_permission_slugs_and_the_switch(client, settings):
    enforce(settings)
    client.force_login(staff("admin", ["department.view"]))
    props = inertia_get(client, reverse("escalated:admin_departments_index")).json()["props"]
    assert props["escalated"]["features"]["roles_permissions"] is True
    assert props["escalated"]["permissions"] == ["department.view"]


def test_limits_a_light_agent_to_viewing_and_notes(client, settings):
    enforce(settings)
    agent = staff("agent", "light_agent")
    ticket = TicketFactory()
    client.force_login(agent)

    assert inertia_get(client, reverse("escalated:agent_ticket_show", args=[ticket.pk])).status_code == 200
    note = post(client, reverse("escalated:agent_ticket_note", args=[ticket.pk]), {"body": "Internal"})
    assert note.status_code in (302, 303)
    assert ticket.replies.filter(is_internal_note=True).count() == 1

    url = lambda name: reverse(f"escalated:{name}", args=[ticket.pk])  # noqa: E731
    assert post(client, url("agent_ticket_assign"), {"agent_id": agent.pk}).status_code == 403
    assert post(client, url("agent_ticket_priority"), {"priority": "high"}).status_code == 403
    assert post(client, url("agent_ticket_status"), {"status": "closed"}).status_code == 403

    ticket.refresh_from_db()
    assert ticket.assigned_to_id is None
    assert ticket.priority == "medium"
    assert ticket.status == "open"


def test_lets_a_full_agent_assign(client, settings):
    enforce(settings)
    agent = staff("agent", "agent")
    ticket = TicketFactory()
    client.force_login(agent)
    response = post(client, reverse("escalated:agent_ticket_assign", args=[ticket.pk]), {"agent_id": agent.pk})
    assert response.status_code in (302, 303)
    ticket.refresh_from_db()
    assert ticket.assigned_to_id == agent.pk


def test_needs_ticket_close_only_to_close_resolve_or_reopen(client, settings):
    enforce(settings)
    ticket = TicketFactory()
    client.force_login(staff("agent", ["ticket.view", "ticket.edit"]))
    url = reverse("escalated:agent_ticket_status", args=[ticket.pk])

    assert post(client, url, {"status": "closed"}).status_code == 403
    assert post(client, url, {"status": "resolved"}).status_code == 403
    assert post(client, url, {"status": "in_progress"}).status_code in (302, 303)
    ticket.refresh_from_db()
    assert ticket.status == "in_progress"

    client.force_login(staff("agent", ["ticket.view", "ticket.edit", "ticket.close"]))
    assert post(client, url, {"status": "resolved"}).status_code in (302, 303)
    ticket.refresh_from_db()
    assert ticket.status == "resolved"


def test_checks_each_bulk_action_against_its_own_permission(client, settings):
    enforce(settings)
    agent = staff("agent", "light_agent")
    ticket = TicketFactory()
    client.force_login(agent)
    url = reverse("escalated:agent_ticket_bulk")

    assert post(client, url, {"ticket_ids": [ticket.pk], "action": "assign", "value": agent.pk}).status_code == 403
    assert post(client, url, {"ticket_ids": [ticket.pk], "action": "delete"}).status_code == 403
    assert post(client, url, {"ticket_ids": [ticket.pk], "action": "status", "value": "closed"}).status_code == 403
    assert Ticket.objects.filter(pk=ticket.pk, assigned_to=None).exists()

    client.force_login(staff("agent", ["ticket.view", "ticket.edit"]))
    response = post(client, url, {"ticket_ids": [ticket.pk], "action": "priority", "value": "high"})
    assert response.status_code in (200, 302, 303)
    ticket.refresh_from_db()
    assert ticket.priority == "high"


def test_checks_the_api_token_owners_permissions(client, settings):
    enforce(settings)
    settings.MIDDLEWARE = [*settings.MIDDLEWARE, API]
    agent = staff("agent", "light_agent")
    token = ApiTokenFactory()
    # The factory's `user` is excluded from the model kwargs: own the token here.
    from django.contrib.contenttypes.models import ContentType

    token.tokenable_content_type = ContentType.objects.get_for_model(agent)
    token.tokenable_object_id = agent.pk
    token.save()
    ticket = TicketFactory()
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token.plain_text}"}

    show = client.get(reverse("escalated:escalated_api:ticket_show", args=[ticket.reference]), **headers)
    assert show.status_code == 200, show.content
    assign = client.post(
        reverse("escalated:escalated_api:ticket_assign", args=[ticket.reference]),
        data=json.dumps({"agent_id": agent.pk}),
        content_type="application/json",
        **headers,
    )
    assert assign.status_code == 403
    delete = client.delete(reverse("escalated:escalated_api:ticket_destroy", args=[ticket.reference]), **headers)
    assert delete.status_code == 403
    assert Ticket.objects.filter(pk=ticket.pk).exists()


def test_refuses_a_staff_url_that_has_no_permission_mapping(rf, settings):
    from django.http import HttpResponse

    enforce(settings)
    view = access.staff_view("admin", "admin_not_in_the_map", lambda request: HttpResponse("ok"))
    request = rf.get("/support/admin/not-in-the-map/")
    request.user = staff("admin", "admin")
    assert view(request).status_code == 403


def _staff_urls():
    names = []

    def walk(patterns, prefix=""):
        for pattern in patterns:
            if hasattr(pattern, "url_patterns"):
                walk(pattern.url_patterns, "api:" if pattern.namespace == "escalated_api" else prefix)
            elif pattern.name:
                names.append((prefix + pattern.name, pattern.callback))

    walk(get_resolver().url_patterns)
    return names


def test_maps_every_admin_agent_and_staff_api_url_to_a_permission():
    unguarded, unmapped = [], []
    for name, callback in _staff_urls():
        is_staff = fnmatchcase(name, "admin_*") or fnmatchcase(name, "agent_*") or name.startswith("api:")
        if not is_staff or name.startswith("api:mobile_guest_"):
            continue
        if name in ("api:auth_login", "api:auth_register", "api:auth_logout", "api:auth_refresh"):
            continue
        if not getattr(callback, "escalated_access_group", None):
            unguarded.append(name)
        if access.mapped_permissions(name) is None:
            unmapped.append(name)
    assert unguarded == []
    assert unmapped == []


def test_names_only_seeded_permissions():
    seeded = {p["slug"] for p in PERMISSIONS}
    named = {slug for _pattern, slugs in access.ROUTE_PERMISSIONS for slug in slugs}
    managed = {f"{group}.manage" for group in access.MANAGED_GROUPS}
    assert named - seeded == set()
    assert managed - seeded == set()


def test_assign_role_command(capsys):
    user = staff("admin")
    call_command("assign_role", user.username, "admin")
    assert "role.manage" in access.user_permissions(user)
    with pytest.raises(Exception):
        call_command("assign_role", "nobody-here", "admin")
    with pytest.raises(Exception):
        call_command("assign_role", user.username, "nope")
