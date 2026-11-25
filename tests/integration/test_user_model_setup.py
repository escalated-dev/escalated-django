"""A host user model Escalated cannot gate fails with a clear error, and the
setup check reports it with the other setup gaps (B5, ecom-core 2026-11-24)."""

import io

import pytest
from django.core.management.base import OutputWrapper
from django.test import RequestFactory

from escalated import scheduler, setup_checks
from escalated.management.commands.install import Command as InstallCommand
from escalated.permissions import UserModelNotSupported, is_admin
from escalated.views import admin as admin_views
from tests.factories import DepartmentFactory, UserFactory


class BareUser:
    """A user on AbstractBaseUser alone: signed in, but no is_staff or is_superuser."""

    is_authenticated = True
    is_active = True
    pk = 1

    class _meta:
        label = "accounts.Member"


def test_is_admin_names_the_missing_contract_instead_of_an_attribute_error():
    with pytest.raises(UserModelNotSupported) as raised:
        is_admin(BareUser())
    message = str(raised.value)
    assert "accounts.Member" in message
    assert "is_staff" in message and "is_superuser" in message
    assert "AbstractUser" in message and "PermissionsMixin" in message


@pytest.mark.django_db
def test_a_staff_page_raises_the_clear_error_on_first_click():
    request = RequestFactory().get("/support/admin/settings/")
    request.user = BareUser()
    with pytest.raises(UserModelNotSupported):
        admin_views.settings_index(request)


@pytest.mark.django_db
def test_a_user_model_with_only_is_superuser_still_works(user):
    class SuperuserOnly(BareUser):
        is_superuser = True

    assert is_admin(SuperuserOnly()) is True
    assert is_admin(user) is False


def test_system_check_reports_the_user_model(monkeypatch):
    monkeypatch.setattr(setup_checks, "get_user_model", lambda: BareUser)
    [warning] = setup_checks.check_user_model(None)
    assert warning.id == "escalated.W004"
    assert "accounts.Member" in warning.msg


def test_system_check_is_quiet_for_the_default_user_model():
    assert setup_checks.check_user_model(None) == []


def _install_report():
    out = io.StringIO()
    command = InstallCommand(stdout=out)
    command.stdout = OutputWrapper(out)
    command.report_setup()
    return out.getvalue()


@pytest.mark.django_db
def test_install_reports_missing_admins_agents_roles_and_jobs(settings):
    settings.ESCALATED = {**settings.ESCALATED, "ACCESS": {"roles_permissions": True}}
    UserFactory()
    report = _install_report()
    assert "Setup check found problems" in report
    assert "No support admin" in report
    assert "No agents" in report
    assert "seed_permissions" in report
    assert "python manage.py check_sla" in report
    assert "python manage.py process_delayed_actions (every minute)" in report


@pytest.mark.django_db
def test_install_reports_a_user_model_it_cannot_gate(monkeypatch):
    monkeypatch.setattr(setup_checks, "get_user_model", lambda: BareUser)
    report = _install_report()
    assert "accounts.Member" in report


@pytest.mark.django_db
def test_install_reports_nothing_once_set_up(admin_user, agent_user):
    scheduler.record_heartbeat()
    DepartmentFactory().agents.add(agent_user)
    assert "no problems found" in _install_report()
