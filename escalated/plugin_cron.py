"""
Five-field cron expressions (``minute hour day-of-month month day-of-week``),
as the plugin SDK's ``cron`` keys are written, evaluated in UTC.

Supports ``*``, numbers, ``a-b`` ranges, ``/step``, comma lists, month and
weekday names, 7 as Sunday, and the ``@hourly``-style shorthands. When both
day fields are restricted, either one matching is enough, as cron does.
"""

import re
from datetime import datetime, timezone

_SHORTHANDS = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}

_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]

# (min, max, names, offset of the first name)
_FIELDS = [
    (0, 59, [], 0),
    (0, 23, [], 0),
    (1, 31, [], 0),
    (1, 12, _MONTHS, 1),
    (0, 7, _DAYS, 0),
]


def due(expression: str, at: datetime) -> bool:
    """
    Whether *expression* is due in the minute containing *at* (UTC; a naive
    datetime is taken as UTC).

    Raises ``ValueError`` when the expression cannot be read.
    """
    text = str(expression).strip()
    text = _SHORTHANDS.get(text.lower(), text)
    parts = text.split() if text else []
    if len(parts) != 5:
        raise _invalid(expression)

    values = []
    anys = []
    for part, field in zip(parts, _FIELDS, strict=True):
        found, any_ = _parse(part, field, expression)
        values.append(found)
        anys.append(any_)
    if 7 in values[4]:
        values[4].add(0)

    utc = at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc)
    if utc.minute not in values[0] or utc.hour not in values[1] or utc.month not in values[3]:
        return False
    dom = utc.day in values[2]
    dow = (utc.isoweekday() % 7) in values[4]
    if not anys[2] and not anys[4]:
        return dom or dow
    return dom and dow


def _parse(text, field, expression):
    lo, hi = field[0], field[1]
    found = set()
    any_ = False
    for part in text.split(","):
        pieces = part.split("/")
        if len(pieces) > 2:
            raise _invalid(expression)
        step = _number(pieces[1], 1, 10**9, expression) if len(pieces) == 2 else 1
        rng = pieces[0]
        if rng == "*":
            start, end = lo, hi
            any_ = len(pieces) == 1
        elif "-" in rng:
            ends = rng.split("-")
            if len(ends) != 2:
                raise _invalid(expression)
            start = _value(ends[0], field, expression)
            end = _value(ends[1], field, expression)
            if start > end:
                raise _invalid(expression)
        else:
            start = _value(rng, field, expression)
            end = hi if len(pieces) == 2 else start
        found.update(range(start, end + 1, step))
    return found, any_


def _value(token, field, expression):
    names = field[2]
    if token.lower() in names:
        return names.index(token.lower()) + field[3]
    return _number(token, field[0], field[1], expression)


def _number(token, lo, hi, expression):
    if not token or len(token) > 9 or not re.fullmatch(r"[0-9]+", token):
        raise _invalid(expression)
    n = int(token)
    if n < lo or n > hi:
        raise _invalid(expression)
    return n


def _invalid(expression):
    return ValueError(f'Invalid cron expression "{expression}".')
