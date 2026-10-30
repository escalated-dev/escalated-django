"""
Give a user an Escalated role (ADR 2026-10-29-configurable-access-features):
how the first admin is bootstrapped before roles & permissions is switched on.

Usage:
    python manage.py assign_role you@example.com admin
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from escalated.models import Role


class Command(BaseCommand):
    help = "Give a user (email, username or id) an Escalated role by slug, keeping their other roles."

    def add_arguments(self, parser):
        parser.add_argument("user")
        parser.add_argument("role", nargs="?", default="admin")

    def handle(self, *args, **options):
        model = get_user_model()
        ref = str(options["user"])
        query = Q(email__iexact=ref) | Q(**{model.USERNAME_FIELD: ref})
        if ref.isdigit():
            query |= Q(pk=ref)
        user = model.objects.filter(query).first()
        if user is None:
            raise CommandError(f"No user [{ref}].")
        role = Role.objects.filter(slug=options["role"]).first()
        if role is None:
            raise CommandError(f"No role [{options['role']}]. Run seed_permissions first.")
        role.users.add(user)
        self.stdout.write(f"Gave user {user.pk} the {role.slug} role.")
