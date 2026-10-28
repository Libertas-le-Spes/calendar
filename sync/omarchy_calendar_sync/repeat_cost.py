"""What expanding one repeating event would cost, before it is expanded.

Expanding a repeat rule walks every occurrence from the rule's first one,
including those long before the sync window. A rule that repeats every
second from years ago would keep the sync busy for hours, so its cost is
worked out from the rule itself first.
"""

from datetime import date, datetime

SECONDS_IN_DAY = 86400

FREQUENCY_SECONDS = {
    "SECONDLY": 1,
    "MINUTELY": 60,
    "HOURLY": 3600,
    "DAILY": SECONDS_IN_DAY,
    "WEEKLY": 7 * SECONDS_IN_DAY,
    "MONTHLY": 28 * SECONDS_IN_DAY,
    "YEARLY": 365 * SECONDS_IN_DAY,
}

TIME_OF_DAY_PARTS = {
    "BYHOUR": 3600,
    "BYMINUTE": 60,
    "BYSECOND": 1,
}


def series_cost(vevent, last_day):
    """An upper bound on the occurrences expanding `vevent` up to `last_day` walks."""
    start = vevent.get("DTSTART")
    if start is None:
        return 0
    first_day = _day_of(start.dt)
    days = max((last_day - first_day).days + 1, 1)
    cost = _extra_dates(vevent.get("RDATE"))
    for rule in _listed(vevent.get("RRULE")):
        cost += _rule_cost(rule, days)
    return cost


def _extra_dates(rdates):
    count = 0
    for rdate in _listed(rdates):
        count += len(getattr(rdate, "dts", [rdate]))
    return count


def _rule_cost(rule, days):
    walked = _occurrences_per_day(rule) * days
    count = _first(rule.get("COUNT"))
    if isinstance(count, int) and count < walked:
        return count
    return walked


def _occurrences_per_day(rule):
    frequency_seconds = FREQUENCY_SECONDS.get(str(_first(rule.get("FREQ"))).upper(), 1)
    per_day = _slots_per_day(frequency_seconds, _interval(rule))
    for part, unit_seconds in TIME_OF_DAY_PARTS.items():
        values = _listed(rule.get(part))
        if values and unit_seconds < frequency_seconds:
            per_day *= len(values)
    return per_day


def _slots_per_day(frequency_seconds, interval):
    if frequency_seconds >= SECONDS_IN_DAY:
        return 1
    return max(SECONDS_IN_DAY // (frequency_seconds * interval), 1)


def _interval(rule):
    interval = _first(rule.get("INTERVAL"))
    if isinstance(interval, int) and interval > 0:
        return interval
    return 1


def _day_of(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError("DTSTART is neither a date nor a date-time")


def _listed(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _first(values):
    listed = _listed(values)
    if not listed:
        return None
    return listed[0]
