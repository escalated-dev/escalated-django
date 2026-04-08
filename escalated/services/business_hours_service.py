from datetime import timedelta, timezone
from zoneinfo import ZoneInfo


class BusinessHoursCalculator:
    """Calculate business hours considering schedules and holidays."""

    def is_within_business_hours(self, dt, schedule):
        """Check if a datetime falls within business hours."""
        tz = ZoneInfo(schedule.timezone)
        dt_local = dt.astimezone(tz)

        if self._is_holiday(dt_local, schedule):
            return False

        day_schedule = self._get_day_schedule(dt_local, schedule)
        if not day_schedule or not day_schedule.get("start") or not day_schedule.get("end"):
            return False

        time_str = dt_local.strftime("%H:%M")
        return day_schedule["start"] <= time_str < day_schedule["end"]

    def add_business_hours(self, start, hours, schedule):
        """Add business hours to a start datetime, skipping non-business time."""
        tz = ZoneInfo(schedule.timezone)
        current = start.astimezone(tz)
        remaining_minutes = hours * 60
        max_iterations = 365

        while remaining_minutes > 0 and max_iterations > 0:
            max_iterations -= 1

            if self._is_holiday(current, schedule):
                current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                continue

            day_schedule = self._get_day_schedule(current, schedule)
            if not day_schedule or not day_schedule.get("start") or not day_schedule.get("end"):
                current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                continue

            start_parts = day_schedule["start"].split(":")
            end_parts = day_schedule["end"].split(":")
            day_start = current.replace(
                hour=int(start_parts[0]),
                minute=int(start_parts[1]),
                second=0,
                microsecond=0,
            )
            day_end = current.replace(
                hour=int(end_parts[0]),
                minute=int(end_parts[1]),
                second=0,
                microsecond=0,
            )

            if current < day_start:
                current = day_start

            if current >= day_end:
                current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                continue

            available_minutes = (day_end - current).total_seconds() / 60

            if remaining_minutes <= available_minutes:
                current = current + timedelta(minutes=remaining_minutes)
                remaining_minutes = 0
            else:
                remaining_minutes -= available_minutes
                current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        return current.astimezone(timezone.utc)

    def _get_day_schedule(self, dt_local, schedule):
        """Get the schedule for a specific day of the week."""
        day_name = dt_local.strftime("%A").lower()
        schedule_data = schedule.schedule or {}
        return schedule_data.get(day_name)

    def _is_holiday(self, dt_local, schedule):
        """Check if a date is a holiday."""
        if not hasattr(schedule, "_prefetched_holidays"):
            schedule._prefetched_holidays = list(schedule.holidays.all())

        for holiday in schedule._prefetched_holidays:
            if holiday.recurring:
                if dt_local.month == holiday.date.month and dt_local.day == holiday.date.day:
                    return True
            else:
                if dt_local.date() == holiday.date:
                    return True
        return False
