from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from escalated.services.business_hours_service import BusinessHoursCalculator
from tests.factories import BusinessScheduleFactory, HolidayFactory


@pytest.mark.django_db
class TestBusinessHoursCalculator:
    def setup_method(self):
        self.calculator = BusinessHoursCalculator()

    def test_is_within_business_hours_weekday(self):
        schedule = BusinessScheduleFactory(timezone="UTC")
        # Monday at 10:00 UTC
        dt = datetime(2026, 3, 2, 10, 0, tzinfo=ZoneInfo("UTC"))
        assert self.calculator.is_within_business_hours(dt, schedule) is True

    def test_is_not_within_business_hours_weekend(self):
        schedule = BusinessScheduleFactory(timezone="UTC")
        # Saturday
        dt = datetime(2026, 2, 28, 10, 0, tzinfo=ZoneInfo("UTC"))
        assert self.calculator.is_within_business_hours(dt, schedule) is False

    def test_is_not_within_business_hours_outside_time(self):
        schedule = BusinessScheduleFactory(timezone="UTC")
        # Monday at 20:00 UTC
        dt = datetime(2026, 3, 2, 20, 0, tzinfo=ZoneInfo("UTC"))
        assert self.calculator.is_within_business_hours(dt, schedule) is False

    def test_is_not_within_business_hours_before_start(self):
        schedule = BusinessScheduleFactory(timezone="UTC")
        # Monday at 07:00 UTC
        dt = datetime(2026, 3, 2, 7, 0, tzinfo=ZoneInfo("UTC"))
        assert self.calculator.is_within_business_hours(dt, schedule) is False

    def test_is_not_within_business_hours_holiday(self):
        schedule = BusinessScheduleFactory(timezone="UTC")
        HolidayFactory(
            schedule=schedule,
            name="Test Holiday",
            date=date(2026, 3, 2),
            recurring=False,
        )
        dt = datetime(2026, 3, 2, 10, 0, tzinfo=ZoneInfo("UTC"))
        assert self.calculator.is_within_business_hours(dt, schedule) is False

    def test_add_business_hours_same_day(self):
        schedule = BusinessScheduleFactory(timezone="UTC")
        # Monday at 09:00, add 2 hours = Monday 11:00
        start = datetime(2026, 3, 2, 9, 0, tzinfo=ZoneInfo("UTC"))
        result = self.calculator.add_business_hours(start, 2, schedule)
        assert result.hour == 11
        assert result.day == 2

    def test_add_business_hours_crosses_end_of_day(self):
        schedule = BusinessScheduleFactory(timezone="UTC")
        # Monday at 15:00, add 4 hours = Tuesday 11:00
        start = datetime(2026, 3, 2, 15, 0, tzinfo=ZoneInfo("UTC"))
        result = self.calculator.add_business_hours(start, 4, schedule)
        assert result.day == 3  # Tuesday
        assert result.hour == 11

    def test_add_business_hours_skips_weekend(self):
        schedule = BusinessScheduleFactory(timezone="UTC")
        # Friday at 15:00, add 4 hours = Monday 11:00
        start = datetime(2026, 2, 27, 15, 0, tzinfo=ZoneInfo("UTC"))
        result = self.calculator.add_business_hours(start, 4, schedule)
        assert result.weekday() == 0  # Monday
        assert result.hour == 11

    def test_add_business_hours_starts_outside_hours(self):
        schedule = BusinessScheduleFactory(timezone="UTC")
        # Monday at 06:00 (before business hours), add 1 hour = Monday 10:00
        start = datetime(2026, 3, 2, 6, 0, tzinfo=ZoneInfo("UTC"))
        result = self.calculator.add_business_hours(start, 1, schedule)
        assert result.day == 2
        assert result.hour == 10

    def test_recurring_holiday_matches_any_year(self):
        schedule = BusinessScheduleFactory(timezone="UTC")
        HolidayFactory(
            schedule=schedule,
            name="Christmas",
            date=date(2025, 12, 25),
            recurring=True,
        )
        # Christmas 2026 should also be a holiday
        dt = datetime(2026, 12, 25, 10, 0, tzinfo=ZoneInfo("UTC"))
        assert self.calculator.is_within_business_hours(dt, schedule) is False

    def test_non_recurring_holiday_only_matches_exact_date(self):
        schedule = BusinessScheduleFactory(timezone="UTC")
        HolidayFactory(
            schedule=schedule,
            name="Company Event",
            date=date(2026, 3, 2),
            recurring=False,
        )
        # Same date = holiday
        dt1 = datetime(2026, 3, 2, 10, 0, tzinfo=ZoneInfo("UTC"))
        assert self.calculator.is_within_business_hours(dt1, schedule) is False

        # Different year = not a holiday (need fresh schedule to clear cache)
        schedule2 = BusinessScheduleFactory(timezone="UTC")
        HolidayFactory(
            schedule=schedule2,
            name="Company Event",
            date=date(2026, 3, 2),
            recurring=False,
        )
        dt2 = datetime(2027, 3, 2, 10, 0, tzinfo=ZoneInfo("UTC"))
        assert self.calculator.is_within_business_hours(dt2, schedule2) is True

    def test_timezone_conversion(self):
        schedule = BusinessScheduleFactory(timezone="America/New_York")
        # 14:00 UTC = 09:00 EST (within business hours)
        dt = datetime(2026, 3, 2, 14, 0, tzinfo=ZoneInfo("UTC"))
        assert self.calculator.is_within_business_hours(dt, schedule) is True

        # 13:00 UTC = 08:00 EST (before business hours)
        dt2 = datetime(2026, 3, 2, 13, 0, tzinfo=ZoneInfo("UTC"))
        assert self.calculator.is_within_business_hours(dt2, schedule) is False
