"""Five-field cron expressions for SDK plugin schedules (plugin contract, Cron)."""

from datetime import datetime

import pytest

from escalated.plugin_cron import due


@pytest.mark.parametrize(
    "expression,at,expected",
    [
        ("* * * * *", "2026-10-29T13:37:00+00:00", True),
        ("37 13 * * *", "2026-10-29T13:37:45+00:00", True),
        ("38 13 * * *", "2026-10-29T13:37:00+00:00", False),
        ("*/15 * * * *", "2026-10-29T13:45:00+00:00", True),
        ("*/15 * * * *", "2026-10-29T13:46:00+00:00", False),
        ("0-10/5 9-17 * * *", "2026-10-29T09:10:00+00:00", True),
        ("0-10/5 9-17 * * *", "2026-10-29T18:10:00+00:00", False),
        ("1,2,3 * * * *", "2026-10-29T13:02:00+00:00", True),
        # 2026-10-29 is a Thursday; 2026-11-01 a Sunday.
        ("0 9 * * thu", "2026-10-29T09:00:00+00:00", True),
        ("0 9 * * MON-WED", "2026-10-29T09:00:00+00:00", False),
        ("0 0 * * 7", "2026-11-01T00:00:00+00:00", True),
        ("0 0 1 nov *", "2026-11-01T00:00:00+00:00", True),
        ("0 0 13 * 4", "2026-10-29T00:00:00+00:00", True),
        ("0 0 13 * 5", "2026-10-29T00:00:00+00:00", False),
        ("0 0 29 * *", "2026-10-29T00:00:00+00:00", True),
        ("0 9 * * *", "2026-10-29T05:00:00-04:00", True),
        ("@hourly", "2026-10-29T13:00:00+00:00", True),
        ("@daily", "2026-10-29T13:00:00+00:00", False),
        ("@weekly", "2026-11-01T00:00:00+00:00", True),
    ],
)
def test_is_due_in_the_minute_in_utc(expression, at, expected):
    assert due(expression, datetime.fromisoformat(at)) is expected


def test_a_naive_time_is_read_as_utc():
    assert due("0 9 * * *", datetime(2026, 10, 29, 9, 0)) is True


@pytest.mark.parametrize(
    "expression",
    ["", "* * * *", "61 * * * *", "* * * * * *", "a b c d e", "*/0 * * * *", "5-1 * * * *"],
)
def test_refuses_what_it_cannot_read(expression):
    with pytest.raises(ValueError):
        due(expression, datetime(2026, 10, 29, 9, 0))
