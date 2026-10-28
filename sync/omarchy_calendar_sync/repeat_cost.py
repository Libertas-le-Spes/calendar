"""What expanding one repeating event would cost, before it is expanded.

Expanding a repeat rule walks every period from the rule's first one, so a
rule that repeats every second from years ago keeps the sync busy for hours.
The cost is worked out from the rule itself: the periods walked up to the
end of the window or the rule's UNTIL, times how many dates each period can
hold. COUNT is ignored, since it limits the dates kept, not the dates
tried. Anything this misses is caught by the expansion's time budget.
"""

from datetime import date, datetime

SECONDS_IN_DAY = 86400

FREQUENCY_SECONDS = {
    "SECONDLY": 1,
    "MINUTELY": 60,
    "HOURLY": 3600,
    "DAILY": SECONDS_IN_DAY,
    "WEEKLY": 7 * SECONDS_IN_DAY,
    "MONTHLY": 31 * SECONDS_IN_DAY,
    "YEARLY": 366 * SECONDS_IN_DAY,
}

TIME_OF_DAY_PARTS = {
    "BYHOUR": 3600,
    "BYMINUTE": 60,
    "BYSECOND": 1,
}

DATES_PER_LISTED_DAY = {
    "WEEKLY": {"BYDAY": 1},
    "MONTHLY": {"BYDAY": 5, "BYMONTHDAY": 1},
    "YEARLY": {"BYDAY": 53, "BYMONTHDAY": 12, "BYYEARDAY": 1, "BYWEEKNO": 7, "BYMONTH": 1},
}


def series_cost(vevent, last_day):
    """An estimate of the dates expanding `vevent` up to `last_day` tries."""
    start = vevent.get("DTSTART")
    if start is None:
        return 0
    first_day = _day_of(start.dt)
    cost = _extra_dates(vevent.get("RDATE"))
    for rule in _listed(vevent.get("RRULE")):
        cost += _rule_cost(rule, first_day, last_day)
    return cost


def _rule_cost(rule, first_day, last_day):
    end_day = _end_day(rule, last_day)
    days = max((end_day - first_day).days + 1, 1)
    frequency = str(_first(rule.get("FREQ"))).upper()
    frequency_seconds = FREQUENCY_SECONDS.get(frequency, 1)
    interval = _interval(rule)
    if frequency_seconds < SECONDS_IN_DAY:
        periods = days * max(SECONDS_IN_DAY // (frequency_seconds * interval), 1)
    else:
        periods = (days - 1) // (frequency_seconds // SECONDS_IN_DAY * interval) + 1
    return periods * _dates_per_period(rule, frequency, frequency_seconds)


def _dates_per_period(rule, frequency, frequency_seconds):
    dates = 1
    weights = DATES_PER_LISTED_DAY.get(frequency, {})
    for part, weight in weights.items():
        values = _listed(rule.get(part))
        if values:
            dates *= len(values) * weight
    dates = min(dates, max(frequency_seconds // SECONDS_IN_DAY, 1))
    for part, unit_seconds in TIME_OF_DAY_PARTS.items():
        values = _listed(rule.get(part))
        if values and unit_seconds < frequency_seconds:
            dates *= len(values)
    return dates


def _end_day(rule, last_day):
    until = _first(rule.get("UNTIL"))
    if until is None:
        return last_day
    return min(_day_of(until), last_day)


def _extra_dates(rdates):
    count = 0
    for rdate in _listed(rdates):
        count += len(getattr(rdate, "dts", [rdate]))
    return count


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
    raise ValueError("a date is neither a date nor a date-time")


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
