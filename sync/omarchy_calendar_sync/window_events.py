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
    """True when a single event lasts into the days between the two."""
    first_day = start_day(vevent)
    end = vevent.get("DTEND")
    last_day = first_day
    if end is not None:
        last_day = day_of(end.dt)
    return first_day <= window_last and last_day >= window_first
