"""The occurrences of one parsed feed inside the sync window, at a bounded cost.

A repeating event whose expansion would cost too much is left out before
anything is expanded, and a calendar whose events together would still cost
too much, or that holds more events than the sync takes, is refused.

The window is always closed at both ends. Walking forward with no end lets
an event that lasts a thousand years keep the walk going in small steps for
as long as it lasts.
"""

from .errors import TooManyEvents
from .limits import EVENTS_PER_CALENDAR, REPEAT_STEPS_PER_CALENDAR, REPEAT_STEPS_PER_SERIES
from .repeat_cost import series_cost


def affordable_calendar(icalendar, calendar, last_day):
    """`calendar` without its costly series, and how many series were left out."""
    costs = _series_costs(calendar, last_day)
    costly = _costly_series(costs)
    if _total_cost(costs, costly) > REPEAT_STEPS_PER_CALENDAR:
        raise TooManyEvents("its repeating events would take too long to expand")
    trimmed = icalendar.Calendar()
    trimmed.update(calendar)
    for component in calendar.subcomponents:
        if not _left_out(component, costly):
            trimmed.add_component(component)
    return trimmed, len(costly)


def occurrences_in_window(rie, calendar, start, end):
    """Expanded components between `start` and `end`, refusing a calendar that holds too many."""
    found = rie.of(calendar).between(start, end)
    if len(found) > EVENTS_PER_CALENDAR:
        raise TooManyEvents("more than %d events in the sync window" % EVENTS_PER_CALENDAR)
    return found


def _series_costs(calendar, last_day):
    costs = {}
    for vevent in calendar.walk("VEVENT"):
        key = _series_key(vevent)
        costs[key] = costs.get(key, 0) + series_cost(vevent, last_day)
    return costs


def _costly_series(costs):
    costly = set()
    for key, cost in costs.items():
        if cost > REPEAT_STEPS_PER_SERIES:
            costly.add(key)
    return costly


def _total_cost(costs, costly):
    total = 0
    for key, cost in costs.items():
        if key not in costly:
            total += cost
    return total


def _left_out(component, costly):
    return component.name == "VEVENT" and _series_key(component) in costly


def _series_key(vevent):
    uid = vevent.get("UID")
    if uid is None:
        return ("no uid", id(vevent))
    return str(uid)
