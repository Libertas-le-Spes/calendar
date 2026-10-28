import unittest
from datetime import date, datetime, timezone
from unittest import mock

import icalendar

from omarchy_calendar_sync import feed_expansion
from omarchy_calendar_sync.errors import CalendarUnreadable, TooManyEvents

LAST_DAY = date(2026, 10, 30)
START = datetime(2026, 10, 1, tzinfo=timezone.utc)
END = datetime(2026, 10, 31, tzinfo=timezone.utc)


def vevent(uid, rule=None):
    event = icalendar.Event()
    if uid is not None:
        event.add("UID", uid)
    event.add("DTSTART", date(2026, 10, 20))
    if rule is not None:
        event.add("RRULE", rule)
    return event


def calendar_of(*components):
    calendar = icalendar.Calendar()
    calendar.add("X-WR-CALNAME", "Made-up feed")
    for component in components:
        calendar.add_component(component)
    return calendar


def uids(calendar):
    found = []
    for component in calendar.walk("VEVENT"):
        found.append(str(component.get("UID")))
    return found


class TestAffordableCalendar(unittest.TestCase):
    def test_a_series_that_repeats_every_second_is_left_out_and_counted(self):
        calendar = calendar_of(vevent("flood@example.invalid", {"FREQ": "SECONDLY"}), vevent("normal@example.invalid"))
        trimmed, left_out = feed_expansion.affordable_calendar(icalendar, calendar, LAST_DAY)
        self.assertEqual(uids(trimmed), ["normal@example.invalid"])
        self.assertEqual(left_out, 1)

    def test_a_left_out_series_takes_its_changed_occurrences_with_it(self):
        override = vevent("flood@example.invalid")
        override.add("RECURRENCE-ID", date(2026, 10, 21))
        calendar = calendar_of(vevent("flood@example.invalid", {"FREQ": "SECONDLY"}), override)
        trimmed, _ = feed_expansion.affordable_calendar(icalendar, calendar, LAST_DAY)
        self.assertEqual(uids(trimmed), [])

    def test_leaving_out_a_series_with_no_uid_keeps_the_timezones(self):
        timezone_component = icalendar.Timezone()
        timezone_component.add("TZID", "Made/Up")
        calendar = calendar_of(timezone_component, vevent(None, {"FREQ": "SECONDLY"}))
        trimmed, left_out = feed_expansion.affordable_calendar(icalendar, calendar, LAST_DAY)
        self.assertEqual([component.name for component in trimmed.subcomponents], ["VTIMEZONE"])
        self.assertEqual(left_out, 1)

    def test_the_calendar_keeps_its_own_properties(self):
        trimmed, _ = feed_expansion.affordable_calendar(icalendar, calendar_of(vevent("a@example.invalid")), LAST_DAY)
        self.assertEqual(str(trimmed.get("X-WR-CALNAME")), "Made-up feed")

    def test_affordable_series_that_together_cost_too_much_refuse_the_calendar(self):
        calendar = calendar_of(vevent("one@example.invalid", {"FREQ": "DAILY"}), vevent("two@example.invalid", {"FREQ": "DAILY"}))
        with mock.patch.object(feed_expansion, "REPEAT_STEPS_PER_CALENDAR", 21):
            with self.assertRaises(CalendarUnreadable):
                feed_expansion.affordable_calendar(icalendar, calendar, LAST_DAY)

    def test_affordable_series_within_the_calendar_budget_are_all_kept(self):
        calendar = calendar_of(vevent("one@example.invalid", {"FREQ": "DAILY"}), vevent("two@example.invalid", {"FREQ": "DAILY"}))
        with mock.patch.object(feed_expansion, "REPEAT_STEPS_PER_CALENDAR", 22):
            trimmed, left_out = feed_expansion.affordable_calendar(icalendar, calendar, LAST_DAY)
        self.assertEqual(uids(trimmed), ["one@example.invalid", "two@example.invalid"])
        self.assertEqual(left_out, 0)


class TestOccurrencesInWindow(unittest.TestCase):
    def library_returning(self, occurrences):
        library = mock.Mock()
        library.of.return_value.between.return_value = occurrences
        return library

    def test_the_library_is_asked_for_exactly_the_window_once(self):
        library = self.library_returning([])
        calendar = calendar_of()
        feed_expansion.occurrences_in_window(library, calendar, START, END)
        library.of.assert_called_once_with(calendar)
        library.of.return_value.between.assert_called_once_with(START, END)

    def test_a_calendar_at_the_limit_keeps_every_occurrence(self):
        library = self.library_returning(["first", "second"])
        with mock.patch.object(feed_expansion, "EVENTS_PER_CALENDAR", 2):
            found = feed_expansion.occurrences_in_window(library, calendar_of(), START, END)
        self.assertEqual(found, ["first", "second"])

    def test_a_calendar_over_the_limit_is_refused(self):
        library = self.library_returning(["first", "second", "third"])
        with mock.patch.object(feed_expansion, "EVENTS_PER_CALENDAR", 2):
            with self.assertRaises(TooManyEvents):
                feed_expansion.occurrences_in_window(library, calendar_of(), START, END)


if __name__ == "__main__":
    unittest.main()
