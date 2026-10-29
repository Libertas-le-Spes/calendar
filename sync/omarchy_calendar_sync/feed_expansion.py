"""The occurrences of one parsed feed inside the sync window, at a bounded cost.

Before anything is expanded, each series is costed from its rule. A series
that would cost too much, or that cannot be read, is left out on its own; a
plain event outside the window is dropped; and a calendar whose remaining
events would still cost too much, or land more dates in the window than the
sync takes, is refused. All of it runs in the feed's own limited process (feed_worker).

The window is always closed at both ends. Walking forward with no end lets
an event that lasts a thousand years keep the walk going in small steps for
as long as it lasts.
"""

from .errors import CalendarUnreadable, TooManyEvents
from .limits import DATES_BEFORE_EXPANSION, EVENTS_PER_CALENDAR, REPEAT_STEPS_PER_CALENDAR, REPEAT_STEPS_PER_SERIES
from .repeat_cost import series_cost, window_dates
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


def expand_by_series(icalendar, rie, calendar, start, end):
    """Expanded components between `start` and `end`, one series at a time.

    Plain events are expanded together, and one by one only when that
    fails, so a bad event or series is left out on its own. Returns the
    components and how many were left out; a calendar that holds more
    events than the sync takes is refused.
    """
    shared, singles, series = _split(calendar)
    found = []
    unreadable = 0
    for members in [singles] + list(series.values()):
        expanded, failed = _expand_members(icalendar, rie, calendar, shared, members, start, end)
        found.extend(expanded)
        unreadable += failed
        if len(found) > EVENTS_PER_CALENDAR:
            raise TooManyEvents()
    return found, unreadable


def _split(calendar):
    shared = []
    singles = []
    series = {}
    for component in calendar.subcomponents:
        if component.name != "VEVENT":
            shared.append(component)
        elif is_single(component):
            singles.append(component)
        else:
            series.setdefault(_series_key(component), []).append(component)
    return shared, singles, series


def _expand_members(icalendar, rie, calendar, shared, members, start, end):
    if not members:
        return [], 0
    try:
        return rie.of(_calendar_of(icalendar, calendar, shared, members)).between(start, end), 0
    except Exception:
        return _expand_one_by_one(icalendar, rie, calendar, shared, members, start, end)


def _expand_one_by_one(icalendar, rie, calendar, shared, members, start, end):
    if len(members) == 1 or not is_single(members[0]):
        return [], 1
    found = []
    failed = 0
    for member in members:
        expanded, member_failed = _expand_members(icalendar, rie, calendar, shared, [member], start, end)
        found.extend(expanded)
        failed += member_failed
    return found, failed


def _calendar_of(icalendar, calendar, shared, members):
    group = icalendar.Calendar()
    group.update(calendar)
    for component in shared + members:
        group.add_component(component)
    return group


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
    if dates > DATES_BEFORE_EXPANSION:
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
