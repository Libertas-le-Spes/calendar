from datetime import date
"""Tests for the iCal feed backend."""

import base64
import contextlib
import io
import unittest
from unittest import mock
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from omarchy_calendar_sync import cli, config, ics, keyring, normalize
from omarchy_calendar_sync.errors import CalendarUnreadable
from omarchy_calendar_sync.config import DayWindow

WIDE_WINDOW = DayWindow(date(2000, 1, 1), date(2100, 12, 31))

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
URL = "https://calendar.google.com/calendar/ical/me%40example.com/private-abc123/basic.ics"

FEED = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Google Inc//Google Calendar 70.9054//EN
X-WR-CALNAME:me@example.com
X-WR-TIMEZONE:America/Sao_Paulo
BEGIN:VEVENT
UID:standup@google.com
DTSTART;TZID=America/Sao_Paulo:20261001T090000
DTEND;TZID=America/Sao_Paulo:20261001T091500
RRULE:FREQ=DAILY;COUNT=5
SUMMARY:Standup
X-GOOGLE-CONFERENCE:https://meet.google.com/abc-defg-hij
ATTENDEE;PARTSTAT=ACCEPTED:mailto:me@example.com
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:This is an event reminder
TRIGGER:-PT10M
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:standup@google.com
RECURRENCE-ID;TZID=America/Sao_Paulo:20261003T090000
DTSTART;TZID=America/Sao_Paulo:20261003T090000
DTEND;TZID=America/Sao_Paulo:20261003T091500
SUMMARY:Standup
STATUS:CANCELLED
END:VEVENT
BEGIN:VEVENT
UID:trip@google.com
DTSTART;VALUE=DATE:20261010
DTEND;VALUE=DATE:20261013
SUMMARY:Trip
BEGIN:VALARM
ACTION:DISPLAY
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:dentist@google.com
DTSTART:20261005T170000Z
DTEND:20261005T180000Z
SUMMARY:Dentist
LOCATION:Rua A
DESCRIPTION:Bring the <b>x-ray</b><br>Parking &amp; entrance on Rua B
ATTENDEE;PARTSTAT=DECLINED:mailto:me@example.com
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER:-PT30M
END:VALARM
BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-P1D
END:VALARM
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER:-PT30M
END:VALARM
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER:PT0S
END:VALARM
BEGIN:VALARM
ACTION:EMAIL
SUMMARY:Reminder
DESCRIPTION:Reminder
ATTENDEE:mailto:me@example.com
TRIGGER:-PT2H
END:VALARM
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER;RELATED=END:-PT5M
END:VALARM
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER;VALUE=DATE-TIME:20261005T160000Z
END:VALARM
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER:PT15M
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:imported-42@example.org
DTSTART:20261007T170000Z
DTEND:20261007T180000Z
SUMMARY:Imported
END:VEVENT
BEGIN:VEVENT
UID:floating@google.com
DTSTART:20261006T100000
DURATION:PT30M
SUMMARY:Floating
END:VEVENT
BEGIN:VEVENT
UID:old@google.com
DTSTART:20250101T100000Z
DTEND:20250101T110000Z
SUMMARY:Too old
END:VEVENT
END:VCALENDAR
"""

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


def client(fetch=None, feeds=None, identity="me@example.com"):
    return ics.Ics(
        feeds if feeds is not None else [URL],
        identity=identity,
        fetch=fetch or (lambda url: FEED),
        local_tz=SAO_PAULO,
    )


def sync_rows(c):
    c.check()
    calendars = c.calendars()
    cfg = dict(config.DEFAULTS)
    lo, hi = config.window_bounds(cfg, NOW)
    rows = []
    for cal in calendars:
        rows.extend(normalize.normalize_all(c.events(cal["id"], lo, hi), cal, SAO_PAULO, WIDE_WINDOW))
    return calendars, rows


class TestFeeds(unittest.TestCase):
    def test_config_shapes(self):
        feeds, _refused = ics.parse_feeds(URL)
        self.assertEqual(feeds[0].url, URL)
        feeds, _refused = ics.parse_feeds([{"url": "webcal://x.example/a.ics", "name": "N"}])
        self.assertEqual((feeds[0].url, feeds[0].name, feeds[0].color), ("https://x.example/a.ics", "N", ""))
        self.assertEqual(ics.parse_feeds([None, "", {"name": "no url"}]), ([], []))

    def test_the_secret_url_never_reaches_ids_or_names(self):
        self.assertNotIn("private", ics.feed_id(URL))
        self.assertEqual(ics.redact(URL), "https://calendar.google.com/...")

    def test_public_and_embed_links_are_named_as_the_wrong_address(self):
        self.assertEqual(ics.url_problem(URL), "")
        self.assertEqual(ics.url_problem("webcal://x.example/a.ics"), "")
        public = "https://calendar.google.com/calendar/ical/me%40example.com/public/basic.ics"
        embed = "https://calendar.google.com/calendar/embed?src=abc%40group.calendar.google.com"
        self.assertIn("public address", ics.url_problem(public))
        self.assertIn("embed link", ics.url_problem(embed))
        self.assertIn("https://", ics.url_problem("not a url"))

    def test_no_feeds_is_an_error(self):
        with self.assertRaises(ics.IcsError):
            client(feeds=[]).check()


class TestExpansion(unittest.TestCase):
    def setUp(self):
        self.calendars, self.rows = sync_rows(client())
        self.by_title = {}
        for row in self.rows:
            self.by_title.setdefault(row["title"], []).append(row)

    def test_calendar_name_comes_from_the_feed(self):
        self.assertEqual(self.calendars[0]["name"], "me@example.com")
        self.assertEqual(self.calendars[0]["color"], ics.FEED_COLORS[0])

    def test_feeds_without_a_colour_get_distinct_ones(self):
        other = "https://calendar.google.com/calendar/ical/b%40example.com/private-x/basic.ics"
        calendars = client(feeds=[URL, other]).calendars()
        self.assertEqual([c["color"] for c in calendars], list(ics.FEED_COLORS[:2]))

    def test_recurrence_is_expanded_and_cancelled_instance_dropped(self):
        days = [row["dateKey"] for row in self.by_title["Standup"]]
        self.assertEqual(days, ["2026-10-01", "2026-10-02", "2026-10-04", "2026-10-05"])
        self.assertEqual(len({row["id"] for row in self.by_title["Standup"]}), 4)

    def test_meet_link_and_answer(self):
        standup = self.by_title["Standup"][0]
        self.assertEqual(standup["meetingUrl"], "https://meet.google.com/abc-defg-hij")
        self.assertEqual(standup["responseStatus"], "accepted")
        self.assertEqual(self.by_title["Dentist"][0]["responseStatus"], "declined")

    def test_all_day_spans_days_with_exclusive_end(self):
        trip = self.by_title["Trip"]
        self.assertTrue(trip[0]["allDay"])
        self.assertEqual([r["dateKey"] for r in trip], ["2026-10-10", "2026-10-11", "2026-10-12"])

    def test_utc_and_floating_times_land_in_local_time(self):
        self.assertEqual(self.by_title["Dentist"][0]["start"], "2026-10-05T14:00:00-03:00")
        floating = self.by_title["Floating"][0]
        self.assertEqual(floating["start"], "2026-10-06T10:00:00-03:00")
        self.assertEqual(floating["end"], "2026-10-06T10:30:00-03:00")

    def test_events_outside_the_window_are_skipped(self):
        self.assertNotIn("Too old", self.by_title)


class TestNewFields(unittest.TestCase):
    def setUp(self):
        _calendars, rows = sync_rows(client())
        self.by_title = {}
        for row in rows:
            self.by_title.setdefault(row["title"], []).append(row)

    def test_display_and_audio_alarms_before_the_start_become_reminders(self):
        # Email, end-relative, absolute and after-start alarms are left out.
        self.assertEqual(self.by_title["Dentist"][0]["reminders"], [0, 30, 1440])

    def test_every_occurrence_of_a_series_keeps_its_alarm(self):
        self.assertEqual({tuple(r["reminders"]) for r in self.by_title["Standup"]}, {(10,)})

    def test_an_alarm_without_a_trigger_is_no_reminder(self):
        self.assertEqual(self.by_title["Trip"][0]["reminders"], [])

    def test_description_is_plain_text(self):
        self.assertEqual(self.by_title["Dentist"][0]["description"],
                         "Bring the x-ray\nParking & entrance on Rua B")

    def test_google_events_link_to_google_calendar(self):
        eid = base64.urlsafe_b64encode(b"dentist me@example.com").decode().rstrip("=")
        self.assertEqual(self.by_title["Dentist"][0]["eventUrl"],
                         "https://calendar.google.com/calendar/event?eid=" + eid)

    def test_occurrences_link_to_their_series(self):
        eid = base64.urlsafe_b64encode(b"standup me@example.com").decode().rstrip("=")
        self.assertEqual({r["eventUrl"] for r in self.by_title["Standup"]},
                         {"https://calendar.google.com/calendar/event?eid=" + eid})

    def test_an_imported_uid_gets_no_link(self):
        self.assertEqual(self.by_title["Imported"][0]["eventUrl"], "")

    def test_a_feed_from_elsewhere_gets_no_links(self):
        _calendars, rows = sync_rows(client(feeds=["https://cloud.example.com/remote.php/dav/me.ics"]))
        self.assertEqual({row["eventUrl"] for row in rows}, {""})


class TestGoogleLinks(unittest.TestCase):
    def test_calendar_id_comes_from_secret_and_public_paths(self):
        self.assertEqual(ics.google_calendar_id(URL), "me@example.com")
        group = "webcal://calendar.google.com/calendar/ical/abc%40group.calendar.google.com/public/basic.ics"
        self.assertEqual(ics.google_calendar_id(group), "abc@group.calendar.google.com")

    def test_other_hosts_and_paths_have_no_calendar_id(self):
        for url in (
            "https://evil.example/calendar/ical/me%40example.com/private-abc/basic.ics",
            "https://calendar.google.com/calendar/embed?src=me%40example.com",
            "https://calendar.google.com/calendar/ical/me%40example.com/private-abc/other.ics",
            "",
        ):
            self.assertEqual(ics.google_calendar_id(url), "", url)

    def test_event_url_is_unpadded_base64url_of_id_and_calendar(self):
        url = ics.google_event_url("abc123@google.com", "me@example.com")
        prefix, eid = url.split("eid=", 1)
        self.assertEqual(prefix, "https://calendar.google.com/calendar/event?")
        self.assertNotIn("=", eid)
        padded = eid + "=" * (-len(eid) % 4)
        self.assertEqual(base64.urlsafe_b64decode(padded), b"abc123 me@example.com")

    def test_no_link_without_a_google_uid_or_calendar(self):
        self.assertEqual(ics.google_event_url("abc@example.org", "me@example.com"), "")
        self.assertEqual(ics.google_event_url("abc@google.com", ""), "")


class TestFailures(unittest.TestCase):
    def test_one_broken_feed_does_not_sink_the_others(self):
        def fetch(url):
            if "broken" in url:
                raise OSError("boom")
            return FEED

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            calendars = client(fetch=fetch, feeds=["https://broken.example/a.ics", URL]).calendars()
        self.assertEqual(len(calendars), 1)
        self.assertIn("skipping https://broken.example/...: OSError while reading the feed", stdout.getvalue())

    def test_every_feed_failing_is_a_sync_error_that_hides_the_secret_path(self):
        def fetch(url):
            raise OSError("boom")

        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ics.IcsError) as caught:
            client(fetch=fetch).calendars()
        self.assertNotIn("private", str(caught.exception))


class TestBackendSelection(unittest.TestCase):
    def test_ics_backend_is_selectable(self):
        cfg = dict(config.DEFAULTS, backend="ics", ics=[URL])
        built = cli.build_client(cfg)
        self.assertEqual(built.SOURCE_NAME, "ics")
        self.assertFalse(built.can_write)


if __name__ == "__main__":
    unittest.main()


class FakeStream:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.reads = 0

    def read(self, amount):
        self.reads += 1
        if not self.chunks:
            return b""
        return self.chunks.pop(0)


class FakeClock:
    def __init__(self, *readings):
        self.readings = list(readings)

    def __call__(self):
        return self.readings.pop(0)


def always(reading):
    return lambda: reading


class TestFeedSize(unittest.TestCase):
    def test_a_feed_at_the_limit_is_returned_whole(self):
        body = ics.read_capped(FakeStream([b"xxxx", b"xxxxxx"]), 10, 100, clock=always(0))
        self.assertEqual(body, b"x" * 10)

    def test_a_feed_over_the_limit_is_refused(self):
        with self.assertRaises(ics.FeedTooLarge):
            ics.read_capped(FakeStream([b"xxxxxx", b"xxxxx"]), 10, 100, clock=always(0))

    def test_reading_stops_at_the_chunk_that_passes_the_limit(self):
        stream = FakeStream([b"xxxxxx", b"xxxxx", b"never read"])
        with self.assertRaises(ics.FeedTooLarge):
            ics.read_capped(stream, 10, 100, clock=always(0))
        self.assertEqual(stream.reads, 2)

    def test_each_read_asks_for_one_chunk(self):
        stream = mock.Mock()
        stream.read.side_effect = [b"x", b""]
        ics.read_capped(stream, 10, 100, clock=always(0))
        self.assertEqual(stream.read.call_args_list, [mock.call(ics.CHUNK_BYTES), mock.call(ics.CHUNK_BYTES)])


class TestFeedDeadline(unittest.TestCase):
    def test_a_feed_that_arrives_before_the_deadline_is_read(self):
        body = ics.read_capped(FakeStream([b"a", b"b"]), 10, 100, clock=FakeClock(98, 99, 100))
        self.assertEqual(body, b"ab")

    def test_a_feed_still_arriving_after_the_deadline_is_refused(self):
        stream = FakeStream([b"a", b"b", b"c"])
        with self.assertRaises(ics.FeedProblem):
            ics.read_capped(stream, 10, 100, clock=FakeClock(99, 101))
        self.assertEqual(stream.reads, 1)

    def test_an_oversized_feed_is_skipped_like_any_broken_feed(self):
        good = "https://feeds.example.invalid/good.ics"
        big = "https://feeds.example.invalid/big.ics"

        def fetch(url):
            if url == big:
                raise ics.FeedTooLarge("too large")
            return FEED

        with contextlib.redirect_stdout(io.StringIO()):
            calendars = client(fetch=fetch, feeds=[big, good]).calendars()
        self.assertEqual(len(calendars), 1)
        self.assertEqual(calendars[0]["id"], ics.feed_id(good))


class TestExpansionFailure(unittest.TestCase):
    def test_a_feed_that_cannot_be_expanded_is_unreadable_on_its_own_without_quoting_the_error(self):
        c = client()
        calendars = c.calendars()
        failure = ValueError("private-SECRETMADEUP in the message")
        with mock.patch.object(ics, "occurrences_in_window", side_effect=failure):
            with self.assertRaises(CalendarUnreadable) as raised:
                c.events(calendars[0]["id"], "2026-10-01T00:00:00+00:00", "2026-10-31T00:00:00+00:00")
        self.assertNotIn("SECRETMADEUP", str(raised.exception))


SECRET = "https://calendar.example.invalid/ical/made-up/private-SECRETMADEUP/basic.ics?token=QUERYMADEUP"


class TestFeedAddressRules(unittest.TestCase):
    def test_an_https_address_is_safe(self):
        self.assertEqual(ics.unsafe_reason("https://feeds.example.invalid/a.ics"), "")

    def test_a_webcal_address_is_read_as_https(self):
        self.assertEqual(ics.unsafe_reason(ics.feed_url("webcal://feeds.example.invalid/a.ics")), "")

    def test_a_plain_http_address_is_refused(self):
        self.assertIn("https://", ics.unsafe_reason("http://feeds.example.invalid/a.ics"))

    def test_an_address_with_a_user_name_and_password_is_refused(self):
        self.assertIn("password", ics.unsafe_reason("https://madeup:PASSWORD@feeds.example.invalid/a.ics"))

    def test_an_address_with_a_space_a_control_character_or_a_backslash_is_refused(self):
        for address in ("https://feeds.example.invalid/a b.ics", "https://feeds.example.invalid/a\x07.ics", "https://evil.example\\@feeds.example.invalid/"):
            with self.subTest(address=address):
                self.assertNotEqual(ics.unsafe_reason(address), "")

    def test_an_address_with_no_host_is_refused(self):
        self.assertIn("host", ics.unsafe_reason("https:///a.ics"))

    def test_an_unsafe_feed_is_set_apart_from_the_feeds(self):
        feeds, refused = ics.parse_feeds(["http://feeds.example.invalid/a.ics", "https://feeds.example.invalid/b.ics"])
        self.assertEqual([feed.url for feed in feeds], ["https://feeds.example.invalid/b.ics"])
        self.assertEqual(refused, ["http://feeds.example.invalid/a.ics"])

    def test_an_unsafe_feed_is_never_fetched_and_its_host_alone_is_logged(self):
        fetched = []

        def fetch(url):
            fetched.append(url)
            return FEED

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            client(fetch=fetch, feeds=["http://feeds.example.invalid/private-SECRETMADEUP.ics", URL]).calendars()
        self.assertEqual(fetched, [URL])
        self.assertIn("skipping http://feeds.example.invalid/...", stdout.getvalue())
        self.assertNotIn("SECRETMADEUP", stdout.getvalue())


class TestSecretsStayOutOfTheLog(unittest.TestCase):
    def test_redact_keeps_only_the_scheme_and_host(self):
        self.assertEqual(ics.redact(SECRET), "https://calendar.example.invalid/...")

    def test_redact_drops_a_user_name_and_password(self):
        self.assertEqual(ics.redact("https://madeup:PASSWORD@dav.example.invalid/x.ics"), "https://dav.example.invalid/...")

    def test_scrubbed_takes_out_the_path_and_query(self):
        text = ics.scrubbed("failed: /ical/made-up/private-SECRETMADEUP/basic.ics and token=QUERYMADEUP", SECRET)
        self.assertNotIn("SECRETMADEUP", text)
        self.assertNotIn("QUERYMADEUP", text)

    def test_a_failure_whose_message_quotes_the_address_logs_only_its_kind(self):
        def fetch(url):
            raise ValueError("unknown url type: %r" % url)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(ics.IcsError) as raised:
                client(fetch=fetch, feeds=[SECRET]).calendars()
        self.assertIn("ValueError while reading the feed", stdout.getvalue())
        self.assertNotIn("SECRETMADEUP", stdout.getvalue())
        self.assertNotIn("SECRETMADEUP", str(raised.exception))

    def test_a_server_error_is_logged_as_its_status(self):
        def fetch(url):
            raise ics.FeedProblem("the server answered HTTP 404")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(ics.IcsError):
            client(fetch=fetch, feeds=[SECRET]).calendars()
        self.assertIn("skipping https://calendar.example.invalid/...: the server answered HTTP 404", stdout.getvalue())


class TestScrubLayer(unittest.TestCase):
    def test_even_a_message_of_our_own_that_quotes_the_secret_path_is_scrubbed(self):
        def fetch(url):
            raise ics.FeedProblem("the server moved /ical/made-up/private-SECRETMADEUP/basic.ics")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(ics.IcsError) as raised:
            client(fetch=fetch, feeds=[SECRET]).calendars()
        self.assertIn("the server moved …", stdout.getvalue())
        self.assertNotIn("SECRETMADEUP", stdout.getvalue())
        self.assertNotIn("SECRETMADEUP", str(raised.exception))


KEYRING_ID = "ics-0123456789ab"


def keyring_lookup(stored):
    def lookup(secret_id):
        if secret_id not in stored:
            raise keyring.KeyringMissing("the keyring holds no address for this feed; run sync/setup --ics")
        return stored[secret_id]
    return lookup


class TestKeyringFeeds(unittest.TestCase):
    def test_a_feed_named_by_a_keyring_id_becomes_a_keyring_feed(self):
        feeds, _refused = ics.parse_feeds([{"secret": KEYRING_ID, "name": "Made-up"}])
        self.assertIsInstance(feeds[0], ics.KeyringFeed)
        self.assertEqual(feeds[0].ident(), KEYRING_ID)

    def test_the_address_is_looked_up_once_and_fetched(self):
        fetched = []
        looked_up = mock.Mock(side_effect=keyring_lookup({KEYRING_ID: URL}))

        def fetch(url):
            fetched.append(url)
            return FEED

        c = ics.Ics([{"secret": KEYRING_ID}], fetch=fetch, local_tz=SAO_PAULO, lookup=looked_up)
        calendars = c.calendars()
        looked_up.assert_called_once_with(KEYRING_ID)
        self.assertEqual(fetched, [URL])
        self.assertEqual(calendars[0]["id"], KEYRING_ID)

    def test_a_feed_missing_from_the_keyring_is_skipped_and_named_by_its_id(self):
        stdout = io.StringIO()
        c = ics.Ics([{"secret": KEYRING_ID}, URL], fetch=lambda url: FEED, local_tz=SAO_PAULO, lookup=keyring_lookup({}))
        with contextlib.redirect_stdout(stdout):
            calendars = c.calendars()
        self.assertEqual(len(calendars), 1)
        self.assertIn("skipping keyring feed %s: the keyring holds no address" % KEYRING_ID, stdout.getvalue())

    def test_an_unsafe_address_in_the_keyring_is_never_fetched(self):
        fetched = []
        stdout = io.StringIO()
        c = ics.Ics([{"secret": KEYRING_ID}], fetch=fetched.append, local_tz=SAO_PAULO,
                    lookup=keyring_lookup({KEYRING_ID: "http://feeds.example.invalid/private-SECRETMADEUP.ics"}))
        with contextlib.redirect_stdout(stdout), self.assertRaises(ics.IcsError):
            c.calendars()
        self.assertEqual(fetched, [])
        self.assertNotIn("SECRETMADEUP", stdout.getvalue())


class TestLibraryVersion(unittest.TestCase):
    def check_with(self, version):
        library = mock.Mock(__version__=version)
        with mock.patch.object(ics, "_load_libs", return_value=(library, mock.Mock())):
            client(feeds=[URL]).check()

    def test_the_minimum_version_is_accepted(self):
        self.check_with("7.2.2")

    def test_an_older_version_with_known_denial_of_service_bugs_is_refused(self):
        with self.assertRaises(ics.IcsMissing) as raised:
            self.check_with("7.2.1")
        self.assertIn("7.2.2 or newer is required, found 7.2.1", str(raised.exception))


class TestOnlyUnsafeFeeds(unittest.TestCase):
    def test_a_config_whose_feeds_are_all_unsafe_is_told_why_rather_than_that_it_has_none(self):
        c = client(feeds=["http://feeds.example.invalid/a.ics"])
        c.check()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(ics.IcsError) as raised:
            c.calendars()
        self.assertIn("expected an https:// or webcal:// address", str(raised.exception))
