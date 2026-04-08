from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from escalated.models import Ticket
from tests.factories import TicketFactory, UserFactory


@pytest.mark.django_db
class TestTicketSnoozeModel:
    def test_snooze_sets_fields(self):
        ticket = TicketFactory(status=Ticket.Status.OPEN)
        user = UserFactory()
        future = timezone.now() + timedelta(hours=24)

        ticket.snooze(until=future, user=user)
        ticket.refresh_from_db()

        assert ticket.snoozed_until == future
        assert ticket.snoozed_by == user
        assert ticket.status_before_snooze == Ticket.Status.OPEN
        assert ticket.status == Ticket.Status.CLOSED

    def test_is_snoozed_true_when_future(self):
        ticket = TicketFactory()
        user = UserFactory()
        future = timezone.now() + timedelta(hours=24)
        ticket.snooze(until=future, user=user)
        ticket.refresh_from_db()

        assert ticket.is_snoozed is True

    def test_is_snoozed_false_when_past(self):
        ticket = TicketFactory()
        past = timezone.now() - timedelta(hours=1)
        ticket.snoozed_until = past
        ticket.save()

        assert ticket.is_snoozed is False

    def test_is_snoozed_false_when_none(self):
        ticket = TicketFactory()

        assert ticket.is_snoozed is False

    def test_unsnooze_restores_status(self):
        ticket = TicketFactory(status=Ticket.Status.IN_PROGRESS)
        user = UserFactory()
        future = timezone.now() + timedelta(hours=24)
        ticket.snooze(until=future, user=user)
        ticket.refresh_from_db()

        ticket.unsnooze()
        ticket.refresh_from_db()

        assert ticket.status == Ticket.Status.IN_PROGRESS
        assert ticket.snoozed_until is None
        assert ticket.snoozed_by is None
        assert ticket.status_before_snooze is None

    def test_unsnooze_defaults_to_open(self):
        ticket = TicketFactory(status=Ticket.Status.OPEN)
        ticket.snoozed_until = timezone.now() + timedelta(hours=1)
        ticket.status = Ticket.Status.CLOSED
        ticket.status_before_snooze = None  # Edge case: missing
        ticket.save()

        ticket.unsnooze()
        ticket.refresh_from_db()

        assert ticket.status == Ticket.Status.OPEN


@pytest.mark.django_db
class TestTicketSnoozeQuerySet:
    def test_snoozed_returns_snoozed_tickets(self):
        user = UserFactory()
        t1 = TicketFactory()
        t1.snooze(until=timezone.now() + timedelta(hours=24), user=user)

        t2 = TicketFactory()  # not snoozed

        snoozed = Ticket.objects.snoozed()
        assert t1 in snoozed
        assert t2 not in snoozed

    def test_not_snoozed_excludes_snoozed(self):
        user = UserFactory()
        t1 = TicketFactory()
        t1.snooze(until=timezone.now() + timedelta(hours=24), user=user)

        t2 = TicketFactory()

        not_snoozed = Ticket.objects.not_snoozed()
        assert t1 not in not_snoozed
        assert t2 in not_snoozed

    def test_snooze_expired_returns_expired(self):
        user = UserFactory()
        t1 = TicketFactory()
        # Manually set snooze to past
        t1.snoozed_until = timezone.now() - timedelta(hours=1)
        t1.status_before_snooze = Ticket.Status.OPEN
        t1.snoozed_by = user
        t1.save()

        t2 = TicketFactory()
        t2.snooze(until=timezone.now() + timedelta(hours=24), user=user)

        expired = Ticket.objects.snooze_expired()
        assert t1 in expired
        assert t2 not in expired


@pytest.mark.django_db
class TestWakeSnoozedTicketsCommand:
    def test_wakes_expired_tickets(self):
        user = UserFactory()
        ticket = TicketFactory(status=Ticket.Status.IN_PROGRESS)
        ticket.snooze(until=timezone.now() + timedelta(hours=24), user=user)
        ticket.refresh_from_db()

        # Manually move snooze to past
        ticket.snoozed_until = timezone.now() - timedelta(hours=1)
        ticket.save(update_fields=["snoozed_until"])

        out = StringIO()
        call_command("wake_snoozed_tickets", stdout=out)

        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.IN_PROGRESS
        assert ticket.snoozed_until is None
        assert "Unsnoozed 1 tickets" in out.getvalue()

    def test_no_tickets_to_wake(self):
        out = StringIO()
        call_command("wake_snoozed_tickets", stdout=out)
        assert "No snoozed tickets to wake" in out.getvalue()

    def test_dry_run(self):
        user = UserFactory()
        ticket = TicketFactory(status=Ticket.Status.OPEN)
        ticket.snooze(until=timezone.now() + timedelta(hours=24), user=user)
        ticket.refresh_from_db()

        ticket.snoozed_until = timezone.now() - timedelta(hours=1)
        ticket.save(update_fields=["snoozed_until"])

        out = StringIO()
        call_command("wake_snoozed_tickets", "--dry-run", stdout=out)

        ticket.refresh_from_db()
        # Should still be snoozed (dry run)
        assert ticket.snoozed_until is not None
        assert "DRY RUN" in out.getvalue()

    def test_does_not_wake_future_snoozed(self):
        user = UserFactory()
        ticket = TicketFactory(status=Ticket.Status.OPEN)
        future = timezone.now() + timedelta(hours=24)
        ticket.snooze(until=future, user=user)
        ticket.refresh_from_db()

        out = StringIO()
        call_command("wake_snoozed_tickets", stdout=out)

        ticket.refresh_from_db()
        assert ticket.is_snoozed is True
        assert "No snoozed tickets to wake" in out.getvalue()
