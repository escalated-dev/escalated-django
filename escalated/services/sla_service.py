import logging
from datetime import datetime, time, timedelta

from django.utils import timezone

from escalated.conf import get_setting
from escalated.models import Ticket, SlaPolicy
from escalated.signals import sla_breached, sla_warning

logger = logging.getLogger("escalated")


class SlaService:
    """
    Manages SLA policy enforcement, deadline calculation, and breach detection.
    """

    @staticmethod
    def apply_sla_deadlines(ticket):
        """
        Apply SLA deadlines to a ticket based on its SLA policy and priority.
        Modifies the ticket in place (does not save).
        """
        if not ticket.sla_policy:
            return

        policy = ticket.sla_policy
        priority = ticket.priority
        now = timezone.now()

        # First response deadline
        first_response_hours = policy.get_first_response_hours(priority)
        if first_response_hours is not None:
            if policy.business_hours_only:
                ticket.first_response_due_at = SlaService._add_business_hours(
                    now, first_response_hours
                )
            else:
                ticket.first_response_due_at = now + timedelta(
                    hours=first_response_hours
                )

        # Resolution deadline
        resolution_hours = policy.get_resolution_hours(priority)
        if resolution_hours is not None:
            if policy.business_hours_only:
                ticket.resolution_due_at = SlaService._add_business_hours(
                    now, resolution_hours
                )
            else:
                ticket.resolution_due_at = now + timedelta(hours=resolution_hours)

    @staticmethod
    def check_breach(ticket):
        """
        Check if a ticket has breached any SLA deadlines. Updates breach flags
        and fires signals.
        """
        if not ticket.is_open:
            return False

        now = timezone.now()
        breached = False

        # Check first response breach
        if (
            ticket.first_response_due_at
            and not ticket.first_response_at
            and not ticket.sla_first_response_breached
            and now > ticket.first_response_due_at
        ):
            ticket.sla_first_response_breached = True
            breached = True
            sla_breached.send(
                sender=Ticket,
                ticket=ticket,
                breach_type="first_response",
            )
            logger.warning(
                f"SLA first response breached on ticket {ticket.reference}"
            )

        # Check resolution breach
        if (
            ticket.resolution_due_at
            and not ticket.resolved_at
            and not ticket.sla_resolution_breached
            and now > ticket.resolution_due_at
        ):
            ticket.sla_resolution_breached = True
            breached = True
            sla_breached.send(
                sender=Ticket,
                ticket=ticket,
                breach_type="resolution",
            )
            logger.warning(
                f"SLA resolution breached on ticket {ticket.reference}"
            )

        if breached:
            ticket.save(
                update_fields=[
                    "sla_first_response_breached",
                    "sla_resolution_breached",
                    "updated_at",
                ]
            )

        return breached

    @staticmethod
    def check_warning(ticket, warning_threshold_minutes=30):
        """
        Check if a ticket is approaching an SLA deadline and send a warning.
        """
        if not ticket.is_open:
            return False

        now = timezone.now()
        threshold = timedelta(minutes=warning_threshold_minutes)
        warned = False

        # First response warning
        if (
            ticket.first_response_due_at
            and not ticket.first_response_at
            and not ticket.sla_first_response_breached
        ):
            remaining = ticket.first_response_due_at - now
            if timedelta(0) < remaining <= threshold:
                sla_warning.send(
                    sender=Ticket,
                    ticket=ticket,
                    warning_type="first_response",
                    remaining=remaining,
                )
                warned = True

        # Resolution warning
        if (
            ticket.resolution_due_at
            and not ticket.resolved_at
            and not ticket.sla_resolution_breached
        ):
            remaining = ticket.resolution_due_at - now
            if timedelta(0) < remaining <= threshold:
                sla_warning.send(
                    sender=Ticket,
                    ticket=ticket,
                    warning_type="resolution",
                    remaining=remaining,
                )
                warned = True

        return warned

    @staticmethod
    def check_all_tickets():
        """
        Check SLA breaches and warnings for all open tickets.
        Called by the check_sla management command.
        """
        open_tickets = Ticket.objects.open().filter(
            sla_policy__isnull=False
        ).select_related("sla_policy")

        breached_count = 0
        warned_count = 0

        for ticket in open_tickets:
            if SlaService.check_breach(ticket):
                breached_count += 1
            if SlaService.check_warning(ticket):
                warned_count += 1

        return breached_count, warned_count

    @staticmethod
    def _add_business_hours(start_dt, hours):
        """
        Add a number of business hours to a datetime, respecting the
        configured business hours schedule.
        """
        sla_config = get_setting("SLA")
        bh = sla_config.get("BUSINESS_HOURS", {})
        start_time = datetime.strptime(bh.get("START", "09:00"), "%H:%M").time()
        end_time = datetime.strptime(bh.get("END", "17:00"), "%H:%M").time()
        business_days = bh.get("DAYS", [1, 2, 3, 4, 5])  # Mon=1 to Fri=5

        # Calculate daily business hours
        daily_start = timedelta(hours=start_time.hour, minutes=start_time.minute)
        daily_end = timedelta(hours=end_time.hour, minutes=end_time.minute)
        daily_business_seconds = (daily_end - daily_start).total_seconds()

        if daily_business_seconds <= 0:
            # Fallback to calendar hours if business hours config is invalid
            return start_dt + timedelta(hours=hours)

        remaining_seconds = hours * 3600
        current = start_dt

        while remaining_seconds > 0:
            # isoweekday: Mon=1, Sun=7
            if current.isoweekday() not in business_days:
                current += timedelta(days=1)
                current = current.replace(
                    hour=start_time.hour,
                    minute=start_time.minute,
                    second=0,
                    microsecond=0,
                )
                continue

            current_time = current.time()

            # If before business hours, move to start
            if current_time < start_time:
                current = current.replace(
                    hour=start_time.hour,
                    minute=start_time.minute,
                    second=0,
                    microsecond=0,
                )
                current_time = start_time

            # If after business hours, move to next day
            if current_time >= end_time:
                current += timedelta(days=1)
                current = current.replace(
                    hour=start_time.hour,
                    minute=start_time.minute,
                    second=0,
                    microsecond=0,
                )
                continue

            # Calculate remaining seconds in current business day
            end_of_day = current.replace(
                hour=end_time.hour,
                minute=end_time.minute,
                second=0,
                microsecond=0,
            )
            available_seconds = (end_of_day - current).total_seconds()

            if remaining_seconds <= available_seconds:
                current += timedelta(seconds=remaining_seconds)
                remaining_seconds = 0
            else:
                remaining_seconds -= available_seconds
                current += timedelta(days=1)
                current = current.replace(
                    hour=start_time.hour,
                    minute=start_time.minute,
                    second=0,
                    microsecond=0,
                )

        return current

    @staticmethod
    def get_default_policy():
        """Return the default SLA policy, or None if none exists."""
        return SlaPolicy.objects.filter(is_default=True, is_active=True).first()
