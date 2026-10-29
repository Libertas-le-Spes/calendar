"""iCalendar feeds as a calendar source.

Why this exists alongside gws and eds: Google publishes every calendar at a
private iCal address (Settings > your calendar > Integrate calendar > Secret
address in iCal format). Reading that needs no Google Cloud project, no OAuth
client, no consent screen and no refresh token, just the URL. The trade is
that it is read only, and Google refreshes the feed on its own schedule, so a
change can take a while to show up.

Any other https iCal feed (Nextcloud, Outlook, Fastmail, a webcal:// link)
works the same way.

Like eds, this emits Google event resources (see resources.py) rather than
contract rows.

The icalendar imports are deliberately lazy, so the module stays importable
on a machine without python-icalendar and python-recurring-ical-events.
"""

import base64
import re
import time
import urllib.parse

from . import keyring
from .errors import CalendarUnreadable, FeedProblem, SyncError
from .feed_download import download
from .feed_header import feed_header
from .feed_request import describe_zone
from .feeds import feed_url, parse_feeds, redact, scrubbed, unsafe_reason
from .limits import DOWNLOAD_RESERVE_SECONDS, RUN_SECONDS, WORKER_MARGIN_SECONDS, WORKER_SECONDS
from .localzone import resolve_local_timezone
from .worker_process import WorkerFailed, run_worker

MINIMUM_ICALENDAR = (7, 2, 2)


class IcsError(SyncError):
    """A feed could not be fetched or parsed."""


class IcsMissing(IcsError):
    """python-icalendar or python-recurring-ical-events is not installed."""


def _load_libs():
    try:
        import icalendar
        import recurring_ical_events

        return icalendar, recurring_ical_events
    except ImportError as error:
        raise IcsMissing(
            "%s; install python-icalendar and python-recurring-ical-events"
            % error
        ) from error


_GOOGLE_HOSTS = ("calendar.google.com", "www.google.com")
_GOOGLE_FEED_PATH = re.compile(r"^/calendar/ical/([^/]+)/(?:private-[^/]+|public)/basic\.ics$")


def google_calendar_id(url):
    """The Google calendar id a feed URL belongs to, or blank for other feeds."""
    parts = urllib.parse.urlsplit(feed_url(url))
    match = _GOOGLE_FEED_PATH.match(parts.path)
    if parts.hostname not in _GOOGLE_HOSTS or not match:
        return ""
    return urllib.parse.unquote(match.group(1))


def _first_given(*choices):
    for choice in choices:
        if choice:
            return choice
    return ""


def _report(calendar_id, answer):
    if answer.get("left_out"):
        print("skipping %d entries in %s: they cannot be read or repeat too often to expand" % (answer["left_out"], calendar_id))
    if answer.get("unconvertible"):
        print("skipping %d events in %s: they cannot be read" % (answer["unconvertible"], calendar_id))


def _skip(label, reason, url):
    failure = scrubbed("%s: %s" % (label, reason), url)
    print("skipping " + failure)
    return failure


def _dotted(version):
    parts = []
    for part in version:
        parts.append(str(part))
    return ".".join(parts)


class Ics:
    """A calendar client backed by one or more iCalendar URLs.

    Presents the same surface as Gws and Eds -- check, version, calendars,
    events -- so cli.run drives it without knowing which it has.
    """

    SOURCE_NAME = "ics"

    # Feeds are read only.
    can_write = False

    def __init__(self, feeds, identity="", fetch=None, local_tz=None, lookup=keyring.lookup, worker=run_worker, clock=time.monotonic):
        self._feeds, self._refused = parse_feeds(feeds, lookup)
        self._identity = identity
        self._fetch = fetch or download
        self._local_tz = local_tz if local_tz is not None else resolve_local_timezone()
        self._worker = worker
        self._clock = clock
        self._deadline = clock() + RUN_SECONDS
        self._bodies = {}

    def version(self):
        icalendar, _rie = _load_libs()
        parts = []
        for piece in str(getattr(icalendar, "__version__", "0")).split("."):
            digits = "".join(ch for ch in piece if ch.isdigit())
            parts.append(int(digits or 0))
        return tuple(parts[:3]) or (0,)

    def check(self):
        _load_libs()
        found = self.version()
        if found < MINIMUM_ICALENDAR:
            raise IcsMissing(
                "python-icalendar %s or newer is required, found %s; update the system packages"
                % (_dotted(MINIMUM_ICALENDAR), _dotted(found))
            )
        if not self._feeds and not self._refused:
            raise IcsError(
                "no feeds configured; add your calendar's secret iCal address "
                "under \"ics\" in ~/.config/omarchy/calendar-sync.json"
            )

    def calendars(self):
        found = []
        failures = []
        for url in self._refused:
            failures.append(_skip(redact(url), unsafe_reason(url), url))
        for feed in self._feeds:
            url = ""
            try:
                self._require_time(DOWNLOAD_RESERVE_SECONDS)
                url = feed.address()
                body = self._fetch(url)
            except FeedProblem as problem:
                failures.append(_skip(feed.label(), str(problem), url))
                continue
            except Exception as error:
                failures.append(_skip(feed.label(), "%s while reading the feed" % type(error).__name__, url))
                continue

            ident = feed.ident()
            self._bodies[ident] = (body, google_calendar_id(url))
            header = feed_header(body)
            found.append(
                {
                    "id": ident,
                    "name": _first_given(feed.name, header["name"], redact(url)),
                    "color": _first_given(feed.color, header["color"]),
                }
            )

        if failures and not found:
            raise IcsError("; ".join(failures))
        return found

    def events(self, calendar_id, time_min, time_max):
        if calendar_id not in self._bodies:
            raise IcsError("calendar %s was never fetched" % calendar_id)
        body, google_id = self._bodies.pop(calendar_id)
        seconds = self._seconds_for_worker()
        request = {
            "body": base64.b64encode(body).decode("ascii"),
            "start": time_min,
            "end": time_max,
            "zone": describe_zone(self._local_tz),
            "identity": self._identity,
            "google_id": google_id,
            "seconds": seconds - WORKER_MARGIN_SECONDS,
        }
        try:
            answer = self._worker(request, seconds)
        except WorkerFailed as failed:
            raise CalendarUnreadable(str(failed)) from None
        if "problem" in answer:
            raise CalendarUnreadable(str(answer["problem"]))
        _report(calendar_id, answer)
        return answer["events"]

    def _seconds_for_worker(self):
        left = self._deadline - self._clock()
        if left < WORKER_MARGIN_SECONDS * 2:
            raise CalendarUnreadable("no time was left in this run to read its events")
        return min(WORKER_SECONDS + WORKER_MARGIN_SECONDS, int(left))

    def _require_time(self, seconds):
        if self._deadline - self._clock() < seconds:
            raise FeedProblem("no time was left in this run to download it")

    def auth_hint(self, _cfg):
        return (
            "check the feed URL in ~/.config/omarchy/calendar-sync.json; a "
            "Google secret address stops working if it is reset in Google "
            "Calendar settings"
        )
