"""Which plain events the sync window can leave out before expanding.

A plain event neither repeats nor moves one occurrence of a series, so one
that does not reach the window has nothing to show there. An occurrence
that was moved is never left out: without it the series would show the
original date.
"""

from .repeat_cost import day_of, start_day


def is_single(vevent):
    """True for an event that neither repeats nor changes one occurrence of a series."""
    for name in ("RRULE", "RDATE", "RECURRENCE-ID"):
        if vevent.get(name) is not None:
            return False
    return True


def touches(vevent, window_first, window_last):
    """True when a single event lasts into the days between the two.

    An event whose end cannot be worked out is kept rather than dropped.
    """
    first_day = start_day(vevent)
    try:
        last_day = _last_day(vevent, first_day)
    except (ValueError, TypeError, OverflowError, AttributeError):
        return first_day <= window_last
    return first_day <= window_last and last_day >= window_first


def _last_day(vevent, first_day):
    end = vevent.get("DTEND")
    if end is not None:
        return day_of(end.dt)
    duration = vevent.get("DURATION")
    if duration is not None:
        return day_of(vevent.get("DTSTART").dt + duration.dt)
    return first_day
