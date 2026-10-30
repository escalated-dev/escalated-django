"""
Remove a user's two-factor enrolment, for a lost device (ADR
2026-10-29-configurable-access-features).

Usage:
    python manage.py reset_two_factor you@example.com
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from escalated.models import TwoFactor


class Command(BaseCommand):
    help = "Remove the two-factor enrolment of a user (email, username or id)."

    def add_arguments(self, parser):
        parser.add_argument("user")

    def handle(self, *args, **options):
        model = get_user_model()
        ref = str(options["user"])
        query = Q(email__iexact=ref) | Q(**{model.USERNAME_FIELD: ref})
        if ref.isdigit():
            query |= Q(pk=ref)
        user = model.objects.filter(query).first()
        if user is None:
            raise CommandError(f"No user [{ref}].")
        TwoFactor.objects.filter(user=user).delete()
        self.stdout.write(f"Removed the two-factor enrolment of user {user.pk}.")
