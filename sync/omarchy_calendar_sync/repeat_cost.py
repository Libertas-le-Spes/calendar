"""What expanding one repeating event would cost, and how many dates it lands
in the window, worked out before anything is expanded.

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
    """An estimate of the dates expanding `vevent` up to `last_day` tries.

    Raises ValueError for an event whose dates or rule cannot be read.
    """
    first_day = start_day(vevent)
    cost = _extra_dates(vevent.get("RDATE"))
    for rule in _listed(vevent.get("RRULE")):
        cost += _rule_dates(rule, first_day, last_day)
    return cost


def window_dates(vevent, window_first, window_last):
    """An estimate of the dates `vevent` lands on between the two days.

    Extra dates and a moved occurrence count only when they fall between
    the two days; a rule counts the periods it walks there.
    """
    first_day = start_day(vevent)
    dates = _extra_dates_between(vevent.get("RDATE"), window_first, window_last)
    rules = _listed(vevent.get("RRULE"))
    if not rules:
        return dates + _own_date_between(vevent, first_day, window_first, window_last)
    from_day = max(first_day, window_first)
    for rule in rules:
        dates += _rule_dates(rule, from_day, window_last)
    return dates


def _own_date_between(vevent, first_day, window_first, window_last):
    days = [first_day]
    moved_from = vevent.get("RECURRENCE-ID")
    if moved_from is not None:
        days.append(day_of(moved_from.dt))
    for day in days:
        if window_first <= day <= window_last:
            return 1
    return 0


def _extra_dates_between(rdates, window_first, window_last):
    count = 0
    for rdate in _listed(rdates):
        for value in getattr(rdate, "dts", [rdate]):
            if window_first <= day_of(value.dt) <= window_last:
                count += 1
    return count


def start_day(vevent):
    start = vevent.get("DTSTART")
    if start is None:
        raise ValueError("an event has no start")
    return day_of(start.dt)


def _rule_dates(rule, from_day, last_day):
    end_day = _end_day(rule, last_day)
    if end_day < from_day:
        return 0
    days = (end_day - from_day).days + 1
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
    return min(day_of(until), last_day)


def _extra_dates(rdates):
    count = 0
    for rdate in _listed(rdates):
        count += len(getattr(rdate, "dts", [rdate]))
    return count


def _interval(rule):
    interval = _first(rule.get("INTERVAL"))
    if interval is None:
        return 1
    if isinstance(interval, int) and interval > 0:
        return interval
    raise ValueError("a repeat rule's interval must be a positive whole number")


def day_of(value):
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
