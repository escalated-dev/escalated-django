"""Tests for permissions.user_permissions (exposed via the escalated Inertia share)."""

import pytest

from escalated.models import Permission, Role
from escalated.permissions import user_permissions


@pytest.mark.django_db
def test_user_permissions_returns_role_slugs(django_user_model):
    user = django_user_model.objects.create_user(username="u1", password="x")
    perm = Permission.objects.create(name="Manage", slug="newsletters.manage", group="Newsletters")
    role = Role.objects.create(name="Editor", slug="editor")
    role.permissions.add(perm)
    role.users.add(user)

    assert user_permissions(user) == ["newsletters.manage"]


@pytest.mark.django_db
def test_user_permissions_empty_without_roles(django_user_model):
    user = django_user_model.objects.create_user(username="u2", password="x")

    assert user_permissions(user) == []


def test_user_permissions_empty_for_anonymous():
    from django.contrib.auth.models import AnonymousUser

    assert user_permissions(AnonymousUser()) == []
