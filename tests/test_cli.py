import contextlib
import io
import json
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from omarchy_calendar_sync import cli, colors, config, contract, gws
from omarchy_calendar_sync.errors import CalendarUnreadable, TooManyEvents

BOGOTA = ZoneInfo("America/Bogota")
NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


class FakeGws:
    SOURCE_NAME = "gws"

    def __init__(self, calendars=None, events=None, raises=None):
        self._calendars = calendars if calendars is not None else [
            {"id": "a@example.com", "name": "Personal", "color": "#f83a22"}
        ]
        self._events = events if events is not None else [
            {
                "id": "evt1",
                "status": "confirmed",
                "summary": "Standup",
                "start": {"dateTime": "2026-08-10T09:00:00-05:00"},
                "end": {"dateTime": "2026-08-10T09:15:00-05:00"},
            }
        ]
        self._raises = raises

    def check(self):
        return None

    def version(self):
        return (0, 13, 2)

    def calendars(self):
        if self._raises:
            raise self._raises
        return self._calendars

    def events(self, calendar_id, time_min, time_max):
        if self._raises:
            raise self._raises
        # A dict gives each calendar its own copy of an event; a list is
        # returned for every calendar.
        if isinstance(self._events, dict):
            return self._events.get(calendar_id, [])
        return self._events

    def auth_hint(self, cfg):
        return "run gws auth login"


def run_quietly(*args):
    """cli.run without its one-line summary on the test output."""
    with contextlib.redirect_stdout(io.StringIO()):
        return cli.run(*args)


class TestWriteAtomic(unittest.TestCase):
    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "deeper" / "out.json"
            cli.write_atomic(path, '{"hello": "world"}\n')
            self.assertEqual(path.read_text(), '{"hello": "world"}\n')

    def test_leaves_no_temp_file_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.json"
            cli.write_atomic(path, "{}\n")
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["out.json"])


class TestRun(unittest.TestCase):
    def test_writes_a_valid_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "calendar-events.json"
            code = run_quietly(FakeGws(), config.DEFAULTS, NOW, out, BOGOTA)
            self.assertEqual(code, 0)
            doc = json.loads(out.read_text())
            self.assertEqual(contract.validate(doc), [])
            self.assertEqual(len(doc["events"]), 1)
            self.assertEqual(doc["events"][0]["title"], "Standup")
            self.assertEqual(doc["events"][0]["dateKey"], "2026-08-10")

    def test_records_source_and_synced_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            run_quietly(FakeGws(), config.DEFAULTS, NOW, out, BOGOTA)
            doc = json.loads(out.read_text())
            self.assertEqual(doc["source"], "gws/0.13.2")
            self.assertEqual(doc["syncedAt"], NOW.isoformat())

    def test_excluded_calendar_contributes_nothing(self):
        cfg = dict(config.DEFAULTS)
        cfg["calendars"] = {"include": [], "exclude": ["Personal"]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            run_quietly(FakeGws(), cfg, NOW, out, BOGOTA)
            self.assertEqual(json.loads(out.read_text())["events"], [])

    def test_events_are_sorted_by_date_then_start(self):
        events = [
            {
                "id": "later",
                "status": "confirmed",
                "summary": "Later",
                "start": {"dateTime": "2026-08-10T18:00:00-05:00"},
                "end": {"dateTime": "2026-08-10T19:00:00-05:00"},
            },
            {
                "id": "earlier",
                "status": "confirmed",
                "summary": "Earlier",
                "start": {"dateTime": "2026-08-10T08:00:00-05:00"},
                "end": {"dateTime": "2026-08-10T09:00:00-05:00"},
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            run_quietly(FakeGws(events=events), config.DEFAULTS, NOW, out, BOGOTA)
            titles = [e["title"] for e in json.loads(out.read_text())["events"]]
            self.assertEqual(titles, ["Earlier", "Later"])

    def test_auth_failure_leaves_previous_file_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            out.write_text('{"version": 1, "events": ["previous"]}')
            code = run_quietly(
                FakeGws(raises=gws.GwsAuthError("401: invalid_grant")),
                config.DEFAULTS,
                NOW,
                out,
                BOGOTA,
            )
            self.assertEqual(code, 1)
            self.assertIn("previous", out.read_text())

    def test_api_failure_does_not_create_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            code = run_quietly(
                FakeGws(raises=gws.GwsApiError("500: boom")),
                config.DEFAULTS,
                NOW,
                out,
                BOGOTA,
            )
            self.assertEqual(code, 1)
            self.assertFalse(out.exists())


def gevent(uid, start, summary="Event", event_id=None):
    return {
        "id": event_id or f"{uid}-{start}",
        "status": "confirmed",
        "summary": summary,
        "iCalUID": uid,
        "start": {"dateTime": start},
        "end": {"dateTime": start},
    }


class TestOccurrenceKey(unittest.TestCase):
    def test_same_event_in_two_calendars_shares_a_key(self):
        a = gevent("shared@google.com", "2026-08-10T19:15:00-05:00")
        b = gevent("shared@google.com", "2026-08-10T19:15:00-05:00", event_id="other")
        self.assertEqual(cli.occurrence_key(a), cli.occurrence_key(b))

    def test_two_instances_of_a_series_have_different_keys(self):
        # A recurring series shares one iCalUID across every instance. Live
        # data confirmed this: a daily standup returned five events with five
        # ids and a single iCalUID. The start is what separates them.
        monday = gevent("standup@google.com", "2026-08-10T09:00:00-05:00")
        wednesday = gevent("standup@google.com", "2026-08-12T09:00:00-05:00")
        self.assertNotEqual(cli.occurrence_key(monday), cli.occurrence_key(wednesday))

    def test_event_without_ical_uid_is_never_deduplicated(self):
        bare = {"id": "x", "start": {"dateTime": "2026-08-10T09:00:00-05:00"}}
        self.assertIsNone(cli.occurrence_key(bare))

    def test_all_day_events_key_on_their_date(self):
        a = {"id": "x", "iCalUID": "u@g", "start": {"date": "2026-08-17"}}
        self.assertEqual(cli.occurrence_key(a), ("u@g", "2026-08-17"))


class TestDeduplicationAcrossCalendars(unittest.TestCase):
    def test_a_recurring_series_survives_intact(self):
        series = [
            gevent("standup@google.com", f"2026-08-{day:02d}T09:00:00-05:00")
            for day in (10, 12, 14, 17, 19)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            run_quietly(FakeGws(events=series), config.DEFAULTS, NOW, out, BOGOTA)
            titles = json.loads(out.read_text())["events"]
            self.assertEqual(len(titles), 5)

    def test_the_same_event_seen_from_two_calendars_is_listed_once(self):
        shared = gevent("shared@google.com", "2026-08-10T19:15:00-05:00", "Impuestos")
        calendars = [
            {"id": "a@example.com", "name": "Alpha", "color": "#f83a22"},
            {"id": "b@example.com", "name": "Beta", "color": "#7bd148"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            run_quietly(
                FakeGws(calendars=calendars, events=[shared]),
                config.DEFAULTS,
                NOW,
                out,
                BOGOTA,
            )
            events = json.loads(out.read_text())["events"]
            self.assertEqual(len(events), 1)
            # First calendar by name wins, so the surviving copy is stable.
            self.assertEqual(events[0]["calendarName"], "Alpha")

    def test_the_primary_calendars_copy_wins_over_one_that_sorts_first(self):
        # A colleague's calendar shared as free/busy returns the same
        # occurrence with no title, and it sorts before yours by name.
        start = "2026-08-10T19:15:00-05:00"
        calendars = [
            {"id": "alice@example.com", "name": "Alice", "color": "#f83a22"},
            {"id": "me@example.com", "name": "me@example.com", "color": "#7bd148", "primary": True},
        ]
        copies = {
            "alice@example.com": [gevent("shared@google.com", start, "")],
            "me@example.com": [gevent("shared@google.com", start, "Impuestos")],
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            run_quietly(
                FakeGws(calendars=calendars, events=copies),
                config.DEFAULTS,
                NOW,
                out,
                BOGOTA,
            )
            events = json.loads(out.read_text())["events"]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["calendarName"], "me@example.com")
            self.assertEqual(events[0]["title"], "Impuestos")


class TestWritableCalendars(unittest.TestCase):
    CALS = [
        {"id": "me@example.com", "name": "Me", "color": "#7bd148", "primary": True, "writable": True},
        {"id": "team@example.com", "name": "Team", "color": "#f83a22", "writable": False},
    ]

    def sync_with(self, cfg_changes, can_write=True):
        client = FakeGws(calendars=self.CALS, events=[])
        client.can_write = can_write
        cfg = {**config.DEFAULTS, **cfg_changes}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            run_quietly(client, cfg, NOW, out, BOGOTA)
            return json.loads(out.read_text())

    def test_writable_calendars_are_listed_when_writing_is_on(self):
        doc = self.sync_with({"write": True})
        self.assertEqual(
            doc["writableCalendars"],
            [{"id": "me@example.com", "name": "Me", "color": "#7bd148"}],
        )

    def test_no_writable_calendars_when_writing_is_off(self):
        self.assertNotIn("writableCalendars", self.sync_with({"write": False}))

    def test_no_writable_calendars_when_the_backend_cannot_write(self):
        self.assertNotIn("writableCalendars", self.sync_with({"write": True}, can_write=False))

    def test_guest_suggestions_are_published_with_writing(self):
        client = FakeGws(calendars=self.CALS, events=[{
            "id": "e1", "status": "confirmed", "summary": "Sync", "iCalUID": "u1",
            "start": {"dateTime": "2026-08-10T09:00:00-05:00"},
            "end": {"dateTime": "2026-08-10T09:30:00-05:00"},
            "attendees": [{"email": "me@example.com", "self": True}, {"email": "ana@example.com"}],
        }])
        client.can_write = True
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            run_quietly(client, {**config.DEFAULTS, "write": True}, NOW, out, BOGOTA)
            doc = json.loads(out.read_text())
        self.assertEqual(doc["guestSuggestions"], [{"email": "ana@example.com", "name": ""}])

    def test_no_guest_suggestions_without_writing(self):
        self.assertNotIn("guestSuggestions", self.sync_with({"write": False}))

    def test_writing_is_off_by_default(self):
        self.assertIs(config.DEFAULTS["write"], False)


if __name__ == "__main__":
    unittest.main()


class CrowdedCalendarGws(FakeGws):
    def events(self, calendar_id, time_min, time_max):
        if calendar_id == "crowded@example.com":
            raise TooManyEvents()
        return super().events(calendar_id, time_min, time_max)


class TestCrowdedCalendar(unittest.TestCase):
    CALENDARS = [
        {"id": "crowded@example.com", "name": "Made-up crowded", "color": "#f83a22"},
        {"id": "quiet@example.com", "name": "Made-up quiet", "color": "#7bd148"},
    ]

    def run_sync(self):
        client = CrowdedCalendarGws(calendars=self.CALENDARS)
        written = mock.create_autospec(cli.write_atomic)
        stderr = io.StringIO()
        with mock.patch.object(cli, "write_atomic", written), contextlib.redirect_stderr(stderr):
            code = run_quietly(client, config.DEFAULTS, NOW, "events.json", BOGOTA)
        return code, written, stderr.getvalue()

    def test_the_other_calendars_are_still_written(self):
        code, written, _ = self.run_sync()
        self.assertEqual(code, cli.EXIT_OK)
        written.assert_called_once()
        calendar_ids = set()
        for row in json.loads(written.call_args.args[1])["events"]:
            calendar_ids.add(row["calendarId"])
        self.assertEqual(calendar_ids, {"quiet@example.com"})

    def test_the_skipped_calendar_is_named_in_the_log(self):
        _, _, log = self.run_sync()
        self.assertIn("skipping calendar 'Made-up crowded'", log)


def made_up_event(event_id, **changes):
    event = {
        "id": event_id,
        "status": "confirmed",
        "summary": "Made-up meeting",
        "start": {"dateTime": "2026-08-10T09:00:00-05:00"},
        "end": {"dateTime": "2026-08-10T09:15:00-05:00"},
    }
    event.update(changes)
    return event


def sync_capturing(client):
    written = mock.create_autospec(cli.write_atomic)
    stderr = io.StringIO()
    with mock.patch.object(cli, "write_atomic", written), contextlib.redirect_stderr(stderr):
        code = run_quietly(client, config.DEFAULTS, NOW, "events.json", BOGOTA)
    return code, written, stderr.getvalue()


def written_rows(written):
    return json.loads(written.call_args.args[1])["events"]


class UnreadableGws(FakeGws):
    def __init__(self, unreadable, **kwargs):
        super().__init__(**kwargs)
        self.unreadable = unreadable

    def events(self, calendar_id, time_min, time_max):
        if calendar_id in self.unreadable:
            raise CalendarUnreadable("its events cannot be expanded (ValueError)")
        return super().events(calendar_id, time_min, time_max)


class TestOneBadCalendar(unittest.TestCase):
    TWO = [
        {"id": "broken@example.com", "name": "Made-up broken", "color": "#f83a22"},
        {"id": "fine@example.com", "name": "Made-up fine", "color": "#7bd148"},
    ]

    def test_a_calendar_color_outside_the_contract_takes_a_palette_color(self):
        calendars = [{"id": "a@example.com", "name": "Made-up feed", "color": "#a1b2c3ff"}]
        code, written, _ = sync_capturing(FakeGws(calendars=calendars))
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(written_rows(written)[0]["color"], colors.CALENDAR_COLORS[0])

    def test_a_row_that_breaks_the_contract_is_dropped_and_the_rest_written(self):
        events = [made_up_event("x" * (contract.FIELD_LENGTHS["id"] + 1)), made_up_event("kept")]
        code, written, log = sync_capturing(FakeGws(events=events))
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual([row["id"] for row in written_rows(written)], ["kept"])
        self.assertIn("dropping 1 rows from calendar 'Personal'", log)

    def test_an_unreadable_calendar_is_skipped_and_the_others_written(self):
        client = UnreadableGws({"broken@example.com"}, calendars=self.TWO)
        code, written, log = sync_capturing(client)
        self.assertEqual(code, cli.EXIT_OK)
        calendar_ids = set()
        for row in written_rows(written):
            calendar_ids.add(row["calendarId"])
        self.assertEqual(calendar_ids, {"fine@example.com"})
        self.assertIn("skipping calendar 'Made-up broken'", log)

    def test_when_every_calendar_is_skipped_nothing_is_written(self):
        client = UnreadableGws({"broken@example.com", "fine@example.com"}, calendars=self.TWO)
        code, written, _ = sync_capturing(client)
        self.assertEqual(code, cli.EXIT_SYNC_FAILED)
        written.assert_not_called()

    def test_a_document_over_the_size_ceiling_is_not_written(self):
        with mock.patch.object(contract, "MAX_DOCUMENT_BYTES", 10):
            code, written, log = sync_capturing(FakeGws())
        self.assertEqual(code, cli.EXIT_SYNC_FAILED)
        written.assert_not_called()
        self.assertIn("would make the events file too large", log)


class TestCopiesThatDiffer(unittest.TestCase):
    START = "2026-08-10T19:15:00-05:00"

    def rows_for(self, calendars, copies):
        code, written, _ = sync_capturing(FakeGws(calendars=calendars, events=copies))
        self.assertEqual(code, cli.EXIT_OK)
        return written_rows(written)

    def with_link(self, summary, link):
        event = gevent("shared@google.com", self.START, summary)
        event["hangoutLink"] = link
        return event

    def test_a_copy_from_someone_elses_calendar_that_sorts_first_cannot_replace_the_event(self):
        calendars = [
            {"id": "aaa@example.com", "name": "Aaa made-up", "color": "#f83a22"},
            {"id": "team@example.com", "name": "Team", "color": "#7bd148"},
        ]
        copies = {
            "aaa@example.com": [self.with_link("Made-up review", "https://evil.example.invalid/join")],
            "team@example.com": [self.with_link("Made-up review", "https://meet.google.com/abc-defg-hij")],
        }
        links = set()
        for row in self.rows_for(calendars, copies):
            links.add(row["meetingUrl"])
        self.assertEqual(links, {"https://evil.example.invalid/join", "https://meet.google.com/abc-defg-hij"})

    def test_a_calendar_shared_with_write_access_still_cannot_replace_the_event(self):
        calendars = [
            {"id": "aaa@example.com", "name": "Aaa made-up", "color": "#f83a22", "writable": True},
            {"id": "team@example.com", "name": "Team", "color": "#7bd148"},
        ]
        copies = {
            "aaa@example.com": [gevent("shared@google.com", self.START, "Something else")],
            "team@example.com": [gevent("shared@google.com", self.START, "Made-up review")],
        }
        titles = set()
        for row in self.rows_for(calendars, copies):
            titles.add(row["title"])
        self.assertEqual(titles, {"Something else", "Made-up review"})


class TestCalendarsWithoutAColour(unittest.TestCase):
    def test_two_calendars_without_a_colour_get_different_ones(self):
        calendars = [
            {"id": "a@example.com", "name": "Made-up one", "color": ""},
            {"id": "b@example.com", "name": "Made-up two", "color": ""},
        ]
        copies = {
            "a@example.com": [made_up_event("one")],
            "b@example.com": [made_up_event("two")],
        }
        _, written, _ = sync_capturing(FakeGws(calendars=calendars, events=copies))
        found = set()
        for row in written_rows(written):
            found.add(row["color"])
        self.assertEqual(found, {colors.CALENDAR_COLORS[0], colors.CALENDAR_COLORS[1]})


def all_day_event(event_id, start, end):
    return {"id": event_id, "status": "confirmed", "summary": "Made-up long", "start": {"date": start}, "end": {"date": end}}


class TestFloodedCalendar(unittest.TestCase):
    CALENDARS = [
        {"id": "flood@example.com", "name": "Made-up flood", "color": "#f83a22"},
        {"id": "quiet@example.com", "name": "Made-up quiet", "color": "#7bd148"},
    ]

    def test_a_calendar_whose_rows_would_pass_the_ceiling_is_skipped_and_the_others_written(self):
        copies = {
            "flood@example.com": [all_day_event("long", "2026-08-01", "2026-09-01")],
            "quiet@example.com": [made_up_event("kept")],
        }
        with mock.patch.object(contract, "MAX_EVENT_ROWS", 10):
            code, written, log = sync_capturing(FakeGws(calendars=self.CALENDARS, events=copies))
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual([row["id"] for row in written_rows(written)], ["kept"])
        self.assertIn("skipping calendar 'Made-up flood'", log)

    def test_a_skipped_calendar_does_not_hide_another_calendars_copy_of_an_event(self):
        shared = gevent("shared@google.com", "2026-08-10T19:15:00-05:00", "Made-up review")
        copies = {
            "flood@example.com": [all_day_event("long", "2026-08-01", "2026-09-01"), shared],
            "quiet@example.com": [dict(shared, id="quiet-copy")],
        }
        with mock.patch.object(contract, "MAX_EVENT_ROWS", 10):
            _, written, _ = sync_capturing(FakeGws(calendars=self.CALENDARS, events=copies))
        self.assertEqual([row["id"] for row in written_rows(written)], ["quiet-copy"])
