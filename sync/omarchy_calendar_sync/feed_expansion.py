"""The occurrences of one parsed feed inside the sync window, at a bounded cost.

Before anything is expanded, each series is costed from its rule. A series
that would cost too much, or that cannot be read, is left out on its own; a
plain event outside the window is dropped; and a calendar whose remaining
events would still cost too much, or land more dates in the window than the
sync takes, is refused. The expansion itself runs under a time budget.

The window is always closed at both ends. Walking forward with no end lets
an event that lasts a thousand years keep the walk going in small steps for
as long as it lasts.
"""

from .errors import CalendarUnreadable, TooManyEvents
from .limits import EVENTS_PER_CALENDAR, EXPANSION_SECONDS, REPEAT_STEPS_PER_CALENDAR, REPEAT_STEPS_PER_SERIES
from .repeat_cost import series_cost, window_dates
from .time_budget import TimeBudgetSpent, time_budget
from .window_events import is_single, touches


class _Series:
    def __init__(self):
        self.cost = 0
        self.dates = 0
        self.readable = True


def affordable_calendar(icalendar, calendar, first_day, last_day):
    """`calendar` with only what is worth expanding, and how many series were left out."""
    series = _weigh(calendar, first_day, last_day)
    left_out = _left_out_keys(series)
    _refuse_when_too_much(series, left_out)
    trimmed = icalendar.Calendar()
    trimmed.update(calendar)
    for component in calendar.subcomponents:
        if _kept(component, left_out, first_day, last_day):
            trimmed.add_component(component)
    return trimmed, len(left_out)


def occurrences_in_window(rie, calendar, start, end):
    """Expanded components between `start` and `end`, refusing a calendar that holds too many."""
    try:
        with time_budget(EXPANSION_SECONDS):
            found = rie.of(calendar).between(start, end)
    except TimeBudgetSpent:
        raise CalendarUnreadable("its events took longer than %d seconds to expand" % EXPANSION_SECONDS) from None
    if len(found) > EVENTS_PER_CALENDAR:
        raise TooManyEvents()
    return found


def _weigh(calendar, first_day, last_day):
    series = {}
    for vevent in calendar.walk("VEVENT"):
        series_weight = series.setdefault(_series_key(vevent), _Series())
        _add_weight(series_weight, vevent, first_day, last_day)
    return series


def _add_weight(series_weight, vevent, first_day, last_day):
    try:
        if is_single(vevent) and not touches(vevent, first_day, last_day):
            return
        series_weight.cost += series_cost(vevent, last_day)
        series_weight.dates += window_dates(vevent, first_day, last_day)
    except (ValueError, TypeError, OverflowError, AttributeError):
        series_weight.readable = False


def _left_out_keys(series):
    left_out = set()
    for key, series_weight in series.items():
        if not series_weight.readable or series_weight.cost > REPEAT_STEPS_PER_SERIES:
            left_out.add(key)
    return left_out


def _refuse_when_too_much(series, left_out):
    cost = 0
    dates = 0
    for key, series_weight in series.items():
        if key not in left_out:
            cost += series_weight.cost
            dates += series_weight.dates
    if cost > REPEAT_STEPS_PER_CALENDAR:
        raise CalendarUnreadable("its repeating events would take too long to expand")
    if dates > EVENTS_PER_CALENDAR:
        raise TooManyEvents()


def _kept(component, left_out, first_day, last_day):
    if component.name != "VEVENT":
        return True
    if _series_key(component) in left_out:
        return False
    if is_single(component):
        return touches(component, first_day, last_day)
    return True


def _series_key(vevent):
    uid = vevent.get("UID")
    if uid is None:
        return ("no uid", id(vevent))
    return str(uid)
