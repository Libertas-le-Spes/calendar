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
import urllib.parse
from datetime import date, datetime, timedelta

from . import keyring
from .errors import CalendarUnreadable, FeedProblem, FeedTooLarge, SyncError
from .feed_download import download
from .feed_expansion import affordable_calendar, occurrences_in_window
from .feeds import feed_url, parse_feeds, redact, scrubbed, unsafe_reason
from .limits import PARSE_SECONDS, TOTAL_FEED_BYTES
from .localzone import resolve_local_timezone
from .resources import build_event
from .time_budget import TimeBudgetSpent, time_budget

ONE_DAY = timedelta(days=1)

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
_GOOGLE_UID_SUFFIX = "@google.com"


def google_calendar_id(url):
    """The Google calendar id a feed URL belongs to, or blank for other feeds."""
    parts = urllib.parse.urlsplit(feed_url(url))
    match = _GOOGLE_FEED_PATH.match(parts.path)
    if parts.hostname not in _GOOGLE_HOSTS or not match:
        return ""
    return urllib.parse.unquote(match.group(1))


def google_event_url(uid, calendar_id):
    """Google Calendar's page for an event, or blank when it cannot be built.

    The feed carries no link, but Google's own link is the event id and the
    calendar id, space separated, in unpadded base64url. The id is the UID
    minus "@google.com"; an event imported from elsewhere keeps a foreign UID
    and an id the feed never reveals. A recurring event's UID names the
    series, so every occurrence opens the series.
    """
    if not calendar_id or not uid.endswith(_GOOGLE_UID_SUFFIX):
        return ""
    event_id = uid[: -len(_GOOGLE_UID_SUFFIX)]
    eid = base64.urlsafe_b64encode(("%s %s" % (event_id, calendar_id)).encode())
    return "https://calendar.google.com/calendar/event?eid=" + eid.decode().rstrip("=")


def to_node(value, local_tz):
    """A date or datetime from icalendar as a Google start/end node.

    A floating time (no TZID, no Z) means "local time wherever you are" in
    iCalendar, so it is pinned to the local zone rather than refused.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=local_tz)
        return {"dateTime": value.isoformat()}
    if isinstance(value, date):
        return {"date": value.isoformat()}
    return None


def _text(component, name):
    value = component.get(name)
    return str(value) if value is not None else ""


def _own_partstat(component, identity):
    """The PARTSTAT of the attendee matching `identity`, or blank."""
    if not identity:
        return ""
    wanted = "mailto:%s" % identity.strip().lower()
    attendees = component.get("ATTENDEE")
    if attendees is None:
        return ""
    if not isinstance(attendees, list):
        attendees = [attendees]
    for attendee in attendees:
        if str(attendee).strip().lower() == wanted:
            return str(getattr(attendee, "params", {}).get("PARTSTAT", ""))
    return ""


def _popup_reminders(component):
    """Minutes before the start of the VALARMs that show or sound something.

    Alarms tied to the end or to an absolute time are left out: the contract
    counts back from the start. EMAIL alarms are not the widget's to raise.
    """
    minutes = set()
    for alarm in component.walk("VALARM"):
        if str(alarm.get("ACTION") or "").upper() not in ("DISPLAY", "AUDIO"):
            continue
        # getattr: a malformed TRIGGER must cost one alarm, not the whole sync.
        trigger = alarm.get("TRIGGER")
        related = getattr(trigger, "params", {}).get("RELATED", "START")
        if str(related).upper() != "START":
            continue
        offset = getattr(trigger, "dt", None)
        if isinstance(offset, timedelta) and offset <= timedelta(0):
            minutes.add(int(-offset.total_seconds()) // 60)
    return sorted(minutes)


def occurrence_to_event(component, local_tz, identity="", calendar_id=""):
    """One expanded VEVENT occurrence as a Google event resource.

    `calendar_id` is the Google calendar the feed belongs to, blank for a
    feed from anywhere else.
    """
    start = component.get("DTSTART")
    if start is None:
        return None
    start_value = start.dt

    end_value = None
    if component.get("DTEND") is not None:
        end_value = component["DTEND"].dt
    elif component.get("DURATION") is not None:
        end_value = start_value + component["DURATION"].dt
    elif isinstance(start_value, datetime):
        end_value = start_value
    else:
        # RFC 5545: an all-day event without DTEND lasts one day.
        end_value = start_value + timedelta(days=1)

    start_node = to_node(start_value, local_tz)
    end_node = to_node(end_value, local_tz)
    if start_node is None:
        return None

    uid = _text(component, "UID")
    cancelled = _text(component, "STATUS").upper() == "CANCELLED"
    return build_event(
        uid=uid,
        start_node=start_node,
        end_node=end_node,
        summary=_text(component, "SUMMARY"),
        location=_text(component, "LOCATION"),
        description=_text(component, "DESCRIPTION"),
        status="cancelled" if cancelled else "",
        conference_url=_text(component, "X-GOOGLE-CONFERENCE"),
        partstat=_own_partstat(component, identity),
        reminders=_popup_reminders(component),
        html_link=google_event_url(uid, calendar_id),
    )


def _parse(icalendar, body):
    try:
        with time_budget(PARSE_SECONDS):
            return icalendar.Calendar.from_ical(body)
    except TimeBudgetSpent:
        raise FeedProblem("the feed took longer than %d seconds to read" % PARSE_SECONDS) from None


def _first_given(*choices):
    for choice in choices:
        if choice:
            return choice
    return ""


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

    def __init__(self, feeds, identity="", fetch=None, local_tz=None, lookup=keyring.lookup):
        self._feeds, self._refused = parse_feeds(feeds, lookup)
        self._identity = identity
        self._fetch = fetch or download
        self._local_tz = local_tz if local_tz is not None else resolve_local_timezone()
        # Feed id -> (parsed calendar, Google calendar id or blank).
        self._parsed = {}
        self._bytes_read = 0

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
        icalendar, _rie = _load_libs()
        found = []
        failures = []
        for url in self._refused:
            failures.append(_skip(redact(url), unsafe_reason(url), url))
        for feed in self._feeds:
            url = ""
            try:
                url = feed.address()
                body = self._fetch(url)
                self._take_bytes(len(body))
                calendar = _parse(icalendar, body)
            except FeedProblem as problem:
                failures.append(_skip(feed.label(), str(problem), url))
                continue
            except Exception as error:
                failures.append(_skip(feed.label(), "%s while reading the feed" % type(error).__name__, url))
                continue

            ident = feed.ident()
            self._parsed[ident] = (calendar, google_calendar_id(url))
            found.append(
                {
                    "id": ident,
                    "name": _first_given(feed.name, _text(calendar, "X-WR-CALNAME"), redact(url)),
                    "color": _first_given(feed.color, _text(calendar, "X-APPLE-CALENDAR-COLOR")),
                }
            )

        if failures and not found:
            # Every feed failed. Writing an empty file would wipe the panel.
            raise IcsError("; ".join(failures))
        return found

    def _take_bytes(self, size):
        if self._bytes_read + size > TOTAL_FEED_BYTES:
            raise FeedTooLarge("the feeds together are larger than %d bytes" % TOTAL_FEED_BYTES)
        self._bytes_read += size

    def events(self, calendar_id, time_min, time_max):
        icalendar, rie = _load_libs()
        if calendar_id not in self._parsed:
            raise IcsError("calendar %s was never fetched" % calendar_id)
        calendar, google_id = self._parsed[calendar_id]

        start = datetime.fromisoformat(time_min)
        end = datetime.fromisoformat(time_max)
        try:
            affordable, left_out = affordable_calendar(icalendar, calendar, start.date() - ONE_DAY, end.date() + ONE_DAY)
            if left_out:
                print("skipping %d repeating events in %s: they cannot be read or repeat too often to expand" % (left_out, calendar_id))
            occurrences = occurrences_in_window(rie, affordable, start, end)
        except CalendarUnreadable:
            raise
        except Exception as error:
            raise CalendarUnreadable("its events cannot be expanded (%s)" % type(error).__name__)

        events = []
        for component in occurrences:
            event = self._event_or_none(component, google_id, calendar_id)
            if event is not None:
                events.append(event)
        return events

    def _event_or_none(self, component, google_id, calendar_id):
        try:
            return occurrence_to_event(component, self._local_tz, self._identity, google_id)
        except (ValueError, TypeError, OverflowError, AttributeError) as error:
            print("skipping an event in %s: it cannot be read (%s)" % (calendar_id, type(error).__name__))
            return None

    def auth_hint(self, _cfg):
        return (
            "check the feed URL in ~/.config/omarchy/calendar-sync.json; a "
            "Google secret address stops working if it is reset in Google "
            "Calendar settings"
        )
