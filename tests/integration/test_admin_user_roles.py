"""
The users screen's roles picker (PUT escalated.admin.users.roles with
{"role_ids": [...]}), mirroring escalated-laravel's
Admin\\UserController::updateRoles: only while roles & permissions is on, needs
role.manage, validates the ids, refuses removing your own role management and
redirects back with "User updated.".
"""

import json

import pytest
from django.core.management import call_command
from django.urls import reverse

from escalated.models import Permission, Role
from tests.factories import DepartmentFactory, UserFactory

pytestmark = pytest.mark.django_db

SHARE = "escalated.middleware.EscalatedInertiaShareMiddleware"


@pytest.fixture(autouse=True)
def seeded(settings):
    call_command("seed_permissions", verbosity=0)
    settings.MIDDLEWARE = [*settings.MIDDLEWARE, SHARE]


def enforce(settings):
    settings.ESCALATED = {**settings.ESCALATED, "ACCESS": {"roles_permissions": True}}


_seq = iter(range(10_000))


def user_with(kind, role=None):
    n = next(_seq)
    if kind == "admin":
        user = UserFactory(username=f"admin{n}", is_staff=True, is_superuser=True)
    elif kind == "agent":
        user = UserFactory(username=f"agent{n}")
        DepartmentFactory().agents.add(user)
    else:
        user = UserFactory(username=f"plain{n}")
    if isinstance(role, str):
        Role.objects.get(slug=role).users.add(user)
    elif isinstance(role, list):
        custom = Role.objects.create(name=f"Custom {n}", slug=f"custom-{n}")
        custom.permissions.set(Permission.objects.filter(slug__in=role))
        custom.users.add(user)
    return user


def slugs(user):
    return sorted(Role.objects.filter(users=user).values_list("slug", flat=True))


def put_roles(client, user_id, body):
    return client.put(
        reverse("escalated:admin_users_roles", args=[user_id]),
        data=json.dumps(body),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )


def index_props(client):
    response = client.get(reverse("escalated:admin_users_index"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    return response.json()["props"]


def light():
    return Role.objects.get(slug="light_agent")


def test_is_not_there_while_off_and_the_screen_sends_no_roles(client):
    admin = user_with("admin", "admin")
    agent = user_with("agent", "agent")
    client.force_login(admin)

    assert put_roles(client, agent.pk, {"role_ids": [light().pk]}).status_code == 404
    assert slugs(agent) == ["agent"]

    props = index_props(client)
    assert "roles" not in props
    assert all("roles" not in row for row in props["users"]["data"])


def test_sends_the_roles_and_each_users_role_slugs(client, settings):
    enforce(settings)
    admin = user_with("admin", "admin")
    agent = user_with("agent", "light_agent")
    plain = user_with("plain")
    client.force_login(admin)

    props = index_props(client)
    names = [role["name"] for role in props["roles"]]
    assert names == sorted(names)
    assert set(props["roles"][0]) == {"id", "name", "slug"}
    assert {"admin", "agent", "light_agent"} <= {role["slug"] for role in props["roles"]}
    rows = {row["id"]: row["roles"] for row in props["users"]["data"]}
    assert rows[admin.pk] == ["admin"]
    assert rows[agent.pk] == ["light_agent"]
    assert rows[plain.pk] == []


def test_replaces_a_users_roles_and_redirects_back_with_the_flash(client, settings):
    enforce(settings)
    admin = user_with("admin", "admin")
    agent = user_with("agent", "agent")
    client.force_login(admin)

    response = put_roles(client, agent.pk, {"role_ids": [light().pk]})
    assert response.status_code in (302, 303)
    assert response["Location"] == reverse("escalated:admin_users_index")
    assert slugs(agent) == ["light_agent"]
    assert index_props(client)["flash"] == {"success": "User updated."}

    from escalated import access

    granted = access.user_permissions(agent)
    assert "reply.create_internal" in granted
    assert "ticket.assign" not in granted

    put_roles(client, agent.pk, {"role_ids": [light().pk, Role.objects.get(slug="agent").pk]})
    assert slugs(agent) == ["agent", "light_agent"]

    put_roles(client, agent.pk, {"role_ids": []})
    assert slugs(agent) == []


@pytest.mark.parametrize("body", [{}, {"role_ids": "admin"}, {"role_ids": ["x"]}, {"role_ids": [987654]}])
def test_validates_role_ids_as_laravel_does(client, settings, body):
    enforce(settings)
    admin = user_with("admin", "admin")
    agent = user_with("agent", "agent")
    client.force_login(admin)

    response = put_roles(client, agent.pk, body)
    assert response.status_code in (302, 303)
    errors = index_props(client)["errors"]
    assert len(errors) == 1
    assert next(iter(errors)) in ("role_ids", "role_ids.0")
    assert slugs(agent) == ["agent"]


def test_needs_role_manage(client, settings):
    enforce(settings)
    manager = user_with("admin", ["user.view", "user.manage"])
    agent = user_with("agent", "agent")
    client.force_login(manager)

    assert put_roles(client, agent.pk, {"role_ids": [light().pk]}).status_code == 403
    assert slugs(agent) == ["agent"]


def test_does_not_let_a_role_manager_remove_their_own_role_management(client, settings):
    enforce(settings)
    admin = user_with("admin", "admin")
    client.force_login(admin)

    response = put_roles(client, admin.pk, {"role_ids": [light().pk]})
    assert response.status_code in (302, 303)
    assert index_props(client)["flash"] == {"error": "You cannot remove your own role management."}
    assert slugs(admin) == ["admin"]


def test_answers_404_for_an_unknown_user(client, settings):
    enforce(settings)
    client.force_login(user_with("admin", "admin"))
    assert put_roles(client, 987654, {"role_ids": [light().pk]}).status_code == 404
