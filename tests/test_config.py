import json
import os
import stat
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from omarchy_calendar_sync import config

CALENDARS = [
    {"id": "a@example.com", "name": "Personal", "color": "#f83a22"},
    {"id": "b@example.com", "name": "Phases of the Moon", "color": "#fad165"},
    {"id": "c@example.com", "name": "Destify", "color": "#ffad46"},
]


class TestLoad(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        loaded = config.load(Path("/nonexistent/calendar-sync.json"))
        self.assertEqual(loaded, config.DEFAULTS)

    def test_partial_file_is_filled_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps({"window": {"futureDays": 90}}))
            loaded = config.load(path)
            self.assertEqual(loaded["window"]["futureDays"], 90)
            self.assertEqual(
                loaded["window"]["pastDays"], config.DEFAULTS["window"]["pastDays"]
            )
            self.assertEqual(loaded["calendars"], config.DEFAULTS["calendars"])

    def test_malformed_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text("{not json")
            with self.assertRaises(config.ConfigError):
                config.load(path)

    def test_defaults_are_not_mutated_by_a_returned_config(self):
        loaded = config.load(Path("/nonexistent/calendar-sync.json"))
        loaded["calendars"]["include"].append("leaked@example.com")
        self.assertEqual(config.DEFAULTS["calendars"]["include"], [])

    def test_null_calendars_and_window_keys_fill_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps({"calendars": None, "window": None}))
            loaded = config.load(path)
            self.assertEqual(loaded["calendars"], config.DEFAULTS["calendars"])
            self.assertEqual(loaded["window"], config.DEFAULTS["window"])

    def test_null_past_days_raises_config_error_naming_the_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps({"window": {"pastDays": None}}))
            with self.assertRaises(config.ConfigError) as ctx:
                config.load(path)
            self.assertIn("pastDays", str(ctx.exception))

    def test_non_numeric_future_days_raises_config_error_naming_the_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps({"window": {"futureDays": "soon"}}))
            with self.assertRaises(config.ConfigError) as ctx:
                config.load(path)
            self.assertIn("futureDays", str(ctx.exception))

    def test_include_as_a_string_raises_config_error_naming_the_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps({"calendars": {"include": "Personal"}}))
            with self.assertRaises(config.ConfigError) as ctx:
                config.load(path)
            self.assertIn("include", str(ctx.exception))


class TestSelectCalendars(unittest.TestCase):
    def test_empty_include_selects_all(self):
        selected = config.select_calendars(CALENDARS, config.DEFAULTS)
        self.assertEqual(len(selected), 3)

    def test_include_by_name(self):
        cfg = {"calendars": {"include": ["Personal"], "exclude": []}}
        selected = config.select_calendars(CALENDARS, cfg)
        self.assertEqual([c["name"] for c in selected], ["Personal"])

    def test_include_by_id(self):
        cfg = {"calendars": {"include": ["c@example.com"], "exclude": []}}
        selected = config.select_calendars(CALENDARS, cfg)
        self.assertEqual([c["name"] for c in selected], ["Destify"])

    def test_exclude_removes_from_all(self):
        cfg = {"calendars": {"include": [], "exclude": ["Phases of the Moon"]}}
        selected = config.select_calendars(CALENDARS, cfg)
        self.assertEqual([c["name"] for c in selected], ["Personal", "Destify"])

    def test_exclude_beats_include(self):
        cfg = {"calendars": {"include": ["Personal"], "exclude": ["Personal"]}}
        self.assertEqual(config.select_calendars(CALENDARS, cfg), [])

    def test_unknown_name_selects_nothing_rather_than_everything(self):
        cfg = {"calendars": {"include": ["Typo"], "exclude": []}}
        self.assertEqual(config.select_calendars(CALENDARS, cfg), [])


class TestWindowBounds(unittest.TestCase):
    def test_bounds_bracket_now(self):
        now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
        time_min, time_max = config.window_bounds(config.DEFAULTS, now)
        self.assertTrue(time_min.startswith("2026-08-03"))
        self.assertTrue(time_max.startswith("2026-10-09"))

    def test_bounds_respect_custom_window(self):
        now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
        cfg = {"window": {"pastDays": 1, "futureDays": 2}}
        time_min, time_max = config.window_bounds(cfg, now)
        self.assertTrue(time_min.startswith("2026-08-09"))
        self.assertTrue(time_max.startswith("2026-08-12"))


def status(mode, owner=None):
    if owner is None:
        owner = os.getuid()
    return os.stat_result((mode, 0, 0, 1, owner, 0, 0, 0, 0, 0))


PRIVATE_FILE = status(stat.S_IFREG | 0o600)
PRIVATE_FOLDER = status(stat.S_IFDIR | 0o700)


def load_text(text, file_status=PRIVATE_FILE, folder_status=PRIVATE_FOLDER):
    statuses = {"calendar-sync.json": file_status, ".": folder_status}

    def fake_stat(path):
        return statuses[str(path)]

    with mock.patch.object(config.Path, "exists", return_value=True), \
            mock.patch.object(config.Path, "read_text", return_value=text), \
            mock.patch.object(config.Path, "stat", autospec=True, side_effect=fake_stat):
        return config.load(Path("calendar-sync.json"))


class TestWindowSize(unittest.TestCase):
    def test_a_window_of_the_largest_allowed_size_loads(self):
        loaded = load_text(json.dumps({"window": {"pastDays": 0, "futureDays": config.MAX_WINDOW_DAYS}}))
        self.assertEqual(loaded["window"]["futureDays"], config.MAX_WINDOW_DAYS)

    def test_a_window_one_day_too_long_is_refused(self):
        with self.assertRaises(config.ConfigError):
            load_text(json.dumps({"window": {"futureDays": config.MAX_WINDOW_DAYS + 1}}))

    def test_a_negative_window_is_refused(self):
        with self.assertRaises(config.ConfigError):
            load_text(json.dumps({"window": {"pastDays": -1}}))


class TestLocalDaysInWindow(unittest.TestCase):
    def test_the_days_are_the_local_days_of_the_window_ends(self):
        now = datetime(2026, 8, 10, 3, 0, tzinfo=timezone.utc)
        cfg = {"window": {"pastDays": 1, "futureDays": 2}}
        days = config.local_days_in_window(cfg, now, ZoneInfo("America/Bogota"))
        self.assertEqual(days, config.DayWindow(date(2026, 8, 8), date(2026, 8, 11)))


class TestGwsPath(unittest.TestCase):
    def test_defaults_to_the_bare_name(self):
        self.assertEqual(config.DEFAULTS["gwsPath"], "gws")

    def test_an_absolute_path_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps({"gwsPath": "/opt/bin/gws"}))
            self.assertEqual(config.load(path)["gwsPath"], "/opt/bin/gws")


if __name__ == "__main__":
    unittest.main()


FEEDS = json.dumps({"backend": "ics", "ics": ["https://feeds.example.invalid/private-made-up.ics"]})
KEYRING_FEEDS = json.dumps({"backend": "ics", "ics": [{"secret": "ics-0123456789ab"}]})


class TestConfigPermissions(unittest.TestCase):
    def test_a_private_config_holding_feed_addresses_loads(self):
        self.assertEqual(load_text(FEEDS)["backend"], "ics")

    def test_a_config_another_user_owns_is_refused(self):
        with self.assertRaises(config.ConfigError) as raised:
            load_text("{}", file_status=status(stat.S_IFREG | 0o600, owner=os.getuid() + 1))
        self.assertIn("another user", str(raised.exception))

    def test_a_config_others_can_change_is_refused_even_without_secrets(self):
        for mode in (0o620, 0o602):
            with self.subTest(mode=oct(mode)):
                with self.assertRaises(config.ConfigError):
                    load_text("{}", file_status=status(stat.S_IFREG | mode))

    def test_a_config_in_a_folder_others_can_change_is_refused(self):
        with self.assertRaises(config.ConfigError) as raised:
            load_text("{}", folder_status=status(stat.S_IFDIR | 0o777))
        self.assertIn("folder", str(raised.exception))

    def test_feed_addresses_others_can_read_are_refused(self):
        for mode in (0o640, 0o604):
            with self.subTest(mode=oct(mode)):
                with self.assertRaises(config.ConfigError) as raised:
                    load_text(FEEDS, file_status=status(stat.S_IFREG | mode))
                self.assertIn("chmod 600", str(raised.exception))

    def test_a_readable_config_without_feed_addresses_loads(self):
        self.assertEqual(load_text("{}", file_status=status(stat.S_IFREG | 0o644))["backend"], "gws")

    def test_feeds_kept_in_the_keyring_may_sit_in_a_readable_config(self):
        self.assertEqual(load_text(KEYRING_FEEDS, file_status=status(stat.S_IFREG | 0o644))["backend"], "ics")
