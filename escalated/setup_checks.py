"""
Setup checks: what stops staff from using Escalated on this install.

``python manage.py install`` prints these after setting up. The user-model
check is also a Django system check (``escalated.W004``), so ``manage.py
check`` and ``runserver`` report it, and the rest are database checks
(``manage.py check --database default``).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.checks import Tags, register
from django.core.checks import Warning as CheckWarning

from escalated.permissions import user_model_problem


def user_model_issue() -> str | None:
    """Why the host's user model cannot pass the admin gate, or None."""
    return user_model_problem(get_user_model())


def data_issues() -> list[str]:
    """Problems found in the database: no admins, no agents, roles nobody holds, jobs not running."""
    from escalated import scheduler
    from escalated.access import feature_enabled
    from escalated.models import Department, Permission, Role

    issues = []
    User = get_user_model()
    if user_model_problem(User) is None:
        flags = {name: True for name in ("is_staff", "is_superuser") if _is_field(User, name)}
        if flags and not any(User._default_manager.filter(**{name: True}).exists() for name in flags):
            issues.append(
                "No support admin: no user has is_staff or is_superuser, so nobody can open the Escalated admin. "
                "Make one with: python manage.py createsuperuser"
            )
    if not Department.objects.filter(is_active=True, agents__isnull=False).exists():
        issues.append(
            "No agents: agents are the users in an active department's agents, and no active department has any. "
            "Add staff to a department (Admin > Departments, or department.agents.add(user))."
        )
    if feature_enabled("roles_permissions"):
        if not Permission.objects.exists():
            issues.append("Roles & permissions is on but no permissions exist: python manage.py seed_permissions")
        elif not Role.objects.filter(users__isnull=False).exists():
            issues.append(
                "Roles & permissions is on but no user holds a role, so every staff page answers 403: "
                "python manage.py assign_role <user> admin"
            )
    current = scheduler.status()
    if current is not None and not current["healthy"]:
        issues.append(current["message"])
    return issues


def _is_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
    except Exception:
        return False
    return True


@register(Tags.models)
def check_user_model(app_configs, **kwargs):
    problem = user_model_issue()
    if problem is None:
        return []
    return [CheckWarning(problem, id="escalated.W004")]


@register(Tags.database)
def check_setup_data(app_configs, databases=None, **kwargs):
    if not databases:
        return []
    try:
        issues = data_issues()
    except Exception:
        # Not migrated yet: the install command reports these afterwards.
        return []
    return [CheckWarning(issue, id="escalated.W003") for issue in issues]
