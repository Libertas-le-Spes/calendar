"""The work done on one feed inside its own limited process.

Parsing, costing, expanding and converting all run here, under one memory
limit and one time budget, so a hostile feed can exhaust only this
process. The answer is plain JSON: the events, or a problem safe to log.
"""

import base64
import json
import resource
import sys
from datetime import datetime, timedelta

from .errors import CalendarUnreadable, FeedProblem
from .feed_events import occurrence_to_event
from .feed_expansion import affordable_calendar, expand_by_series
from .feed_request import zone_from
from .limits import WORKER_MEMORY_BYTES, WORKER_SECONDS
from .time_budget import TimeBudgetSpent, time_budget

ONE_DAY = timedelta(days=1)
ANSWER_TEXT_LIMIT = 4096
ANSWER_TEXT_LIMITS = {"summary": 501, "location": 4096, "description": 8192}


def main():
    resource.setrlimit(resource.RLIMIT_AS, (WORKER_MEMORY_BYTES, WORKER_MEMORY_BYTES))
    request = json.loads(sys.stdin.read())
    sys.stdout.write(json.dumps(answer(request), ensure_ascii=False))


def answer(request):
    seconds = min(WORKER_SECONDS, request.get("seconds", WORKER_SECONDS))
    try:
        with time_budget(seconds):
            return expand(request)
    except TimeBudgetSpent:
        return problem("its events took longer than %d seconds to read" % seconds)
    except MemoryError:
        return problem("its events need more memory than one feed may use")
    except (CalendarUnreadable, FeedProblem) as refused:
        return problem(str(refused))
    except Exception as error:
        return problem("%s while reading its events" % type(error).__name__)


def problem(text):
    return {"problem": text}


def expand(request):
    icalendar, rie = _libraries()
    calendar = icalendar.Calendar.from_ical(base64.b64decode(request["body"]))
    start = datetime.fromisoformat(request["start"])
    end = datetime.fromisoformat(request["end"])
    affordable, left_out = affordable_calendar(icalendar, calendar, start.date() - ONE_DAY, end.date() + ONE_DAY)
    occurrences, unreadable = expand_by_series(icalendar, rie, affordable, start, end)
    local_tz = zone_from(request["zone"])
    events = []
    unconvertible = 0
    for component in occurrences:
        try:
            event = occurrence_to_event(component, local_tz, request["identity"], request["google_id"])
        except (ValueError, TypeError, OverflowError, AttributeError):
            unconvertible += 1
            continue
        if event is None:
            unconvertible += 1
            continue
        events.append(clipped(event))
    return {"events": events, "left_out": left_out + unreadable, "unconvertible": unconvertible}


def clipped(value, key=""):
    """`value` with every string cut to the most the sync will read of it."""
    if isinstance(value, str):
        return value[: ANSWER_TEXT_LIMITS.get(key, ANSWER_TEXT_LIMIT)]
    if isinstance(value, dict):
        found = {}
        for name, item in value.items():
            found[name] = clipped(item, name)
        return found
    if isinstance(value, list):
        found = []
        for item in value:
            found.append(clipped(item, key))
        return found
    return value


def _libraries():
    import icalendar
    import recurring_ical_events

    return icalendar, recurring_ical_events
