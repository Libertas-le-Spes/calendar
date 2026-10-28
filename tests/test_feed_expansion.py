import time
import unittest
from datetime import date, datetime, timezone
from unittest import mock

import icalendar

from omarchy_calendar_sync import feed_expansion
from omarchy_calendar_sync.errors import CalendarUnreadable, TooManyEvents

FIRST_DAY = date(2026, 10, 1)
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
        trimmed, left_out = feed_expansion.affordable_calendar(icalendar, calendar, FIRST_DAY, LAST_DAY)
        self.assertEqual(uids(trimmed), ["normal@example.invalid"])
        self.assertEqual(left_out, 1)

    def test_a_left_out_series_takes_its_changed_occurrences_with_it(self):
        override = vevent("flood@example.invalid")
        override.add("RECURRENCE-ID", date(2026, 10, 21))
        calendar = calendar_of(vevent("flood@example.invalid", {"FREQ": "SECONDLY"}), override)
        trimmed, _ = feed_expansion.affordable_calendar(icalendar, calendar, FIRST_DAY, LAST_DAY)
        self.assertEqual(uids(trimmed), [])

    def test_leaving_out_a_series_with_no_uid_keeps_the_timezones(self):
        timezone_component = icalendar.Timezone()
        timezone_component.add("TZID", "Made/Up")
        calendar = calendar_of(timezone_component, vevent(None, {"FREQ": "SECONDLY"}))
        trimmed, left_out = feed_expansion.affordable_calendar(icalendar, calendar, FIRST_DAY, LAST_DAY)
        self.assertEqual([component.name for component in trimmed.subcomponents], ["VTIMEZONE"])
        self.assertEqual(left_out, 1)

    def test_the_calendar_keeps_its_own_properties(self):
        trimmed, _ = feed_expansion.affordable_calendar(icalendar, calendar_of(vevent("a@example.invalid")), FIRST_DAY, LAST_DAY)
        self.assertEqual(str(trimmed.get("X-WR-CALNAME")), "Made-up feed")

    def test_affordable_series_that_together_cost_too_much_refuse_the_calendar(self):
        calendar = calendar_of(vevent("one@example.invalid", {"FREQ": "DAILY"}), vevent("two@example.invalid", {"FREQ": "DAILY"}))
        with mock.patch.object(feed_expansion, "REPEAT_STEPS_PER_CALENDAR", 21):
            with self.assertRaises(CalendarUnreadable):
                feed_expansion.affordable_calendar(icalendar, calendar, FIRST_DAY, LAST_DAY)

    def test_affordable_series_within_the_calendar_budget_are_all_kept(self):
        calendar = calendar_of(vevent("one@example.invalid", {"FREQ": "DAILY"}), vevent("two@example.invalid", {"FREQ": "DAILY"}))
        with mock.patch.object(feed_expansion, "REPEAT_STEPS_PER_CALENDAR", 22):
            trimmed, left_out = feed_expansion.affordable_calendar(icalendar, calendar, FIRST_DAY, LAST_DAY)
        self.assertEqual(uids(trimmed), ["one@example.invalid", "two@example.invalid"])
        self.assertEqual(left_out, 0)


def single(uid, day):
    event = icalendar.Event()
    event.add("UID", uid)
    event.add("DTSTART", day)
    return event


class TestWhatReachesTheExpansion(unittest.TestCase):
    def test_a_series_whose_start_cannot_be_read_is_left_out_on_its_own(self):
        broken = icalendar.Event()
        broken.add("UID", "broken@example.invalid")
        broken.add("RRULE", {"FREQ": "DAILY"})
        broken["DTSTART"] = icalendar.vText("not a date")
        calendar = calendar_of(broken, vevent("normal@example.invalid"))
        trimmed, left_out = feed_expansion.affordable_calendar(icalendar, calendar, FIRST_DAY, LAST_DAY)
        self.assertEqual(uids(trimmed), ["normal@example.invalid"])
        self.assertEqual(left_out, 1)

    def test_a_series_with_an_interval_of_zero_is_left_out(self):
        calendar = calendar_of(vevent("zero@example.invalid", {"FREQ": "DAILY", "INTERVAL": 0}))
        trimmed, left_out = feed_expansion.affordable_calendar(icalendar, calendar, FIRST_DAY, LAST_DAY)
        self.assertEqual((uids(trimmed), left_out), ([], 1))

    def test_a_plain_event_outside_the_window_never_reaches_the_expansion(self):
        calendar = calendar_of(single("old@example.invalid", date(2020, 1, 1)), single("now@example.invalid", date(2026, 10, 9)))
        trimmed, left_out = feed_expansion.affordable_calendar(icalendar, calendar, FIRST_DAY, LAST_DAY)
        self.assertEqual((uids(trimmed), left_out), (["now@example.invalid"], 0))

    def test_a_moved_occurrence_outside_the_window_is_kept_so_the_original_date_stays_moved(self):
        moved = single("series@example.invalid", date(2027, 1, 5))
        moved.add("RECURRENCE-ID", date(2026, 10, 21))
        calendar = calendar_of(vevent("series@example.invalid", {"FREQ": "DAILY"}), moved)
        trimmed, _ = feed_expansion.affordable_calendar(icalendar, calendar, FIRST_DAY, LAST_DAY)
        self.assertEqual(uids(trimmed), ["series@example.invalid", "series@example.invalid"])

    def test_a_calendar_whose_events_would_land_too_many_dates_in_the_window_is_refused_before_expanding(self):
        calendar = calendar_of(vevent("one@example.invalid", {"FREQ": "DAILY"}), vevent("two@example.invalid", {"FREQ": "DAILY"}))
        with mock.patch.object(feed_expansion, "DATES_BEFORE_EXPANSION", 21):
            with self.assertRaises(TooManyEvents):
                feed_expansion.affordable_calendar(icalendar, calendar, FIRST_DAY, LAST_DAY)


class TestExpandBySeries(unittest.TestCase):
    def library_returning(self, occurrences):
        library = mock.Mock()
        library.of.return_value.between.return_value = occurrences
        return library

    def test_the_library_is_asked_for_exactly_the_window(self):
        library = self.library_returning([])
        feed_expansion.expand_by_series(icalendar, library, calendar_of(vevent("one@example.invalid", {"FREQ": "DAILY"})), START, END)
        library.of.return_value.between.assert_called_once_with(START, END)

    def test_each_series_is_expanded_on_its_own_and_plain_events_together(self):
        library = self.library_returning([])
        calendar = calendar_of(vevent("one@example.invalid", {"FREQ": "DAILY"}), vevent("two@example.invalid", {"FREQ": "WEEKLY"}),
                               single("a@example.invalid", date(2026, 10, 9)), single("b@example.invalid", date(2026, 10, 10)))
        feed_expansion.expand_by_series(icalendar, library, calendar, START, END)
        expanded = []
        for call in library.of.call_args_list:
            expanded.append(sorted(uids(call.args[0])))
        self.assertEqual(sorted(expanded), [["a@example.invalid", "b@example.invalid"], ["one@example.invalid"], ["two@example.invalid"]])

    def test_a_series_whose_expansion_raises_is_left_out_on_its_own(self):
        def between_unless_broken(start, end):
            raise ValueError("made-up")

        library = mock.Mock()
        healthy = mock.Mock()
        healthy.between.return_value = ["occurrence"]
        broken = mock.Mock()
        broken.between.side_effect = between_unless_broken
        library.of.side_effect = [healthy, broken]
        calendar = calendar_of(vevent("good@example.invalid", {"FREQ": "DAILY"}), vevent("bad@example.invalid", {"FREQ": "DAILY"}))
        found, unreadable = feed_expansion.expand_by_series(icalendar, library, calendar, START, END)
        self.assertEqual((found, unreadable), (["occurrence"], 1))

    def test_plain_events_that_fail_together_are_retried_one_by_one(self):
        library = mock.Mock()
        together = mock.Mock()
        together.between.side_effect = ValueError("made-up")
        good = mock.Mock()
        good.between.return_value = ["occurrence"]
        bad = mock.Mock()
        bad.between.side_effect = ValueError("made-up")
        library.of.side_effect = [together, good, bad]
        calendar = calendar_of(single("a@example.invalid", date(2026, 10, 9)), single("b@example.invalid", date(2026, 10, 10)))
        found, unreadable = feed_expansion.expand_by_series(icalendar, library, calendar, START, END)
        self.assertEqual((found, unreadable), (["occurrence"], 1))

    def test_a_calendar_at_the_limit_keeps_every_occurrence(self):
        library = self.library_returning(["first", "second"])
        with mock.patch.object(feed_expansion, "EVENTS_PER_CALENDAR", 2):
            found, _ = feed_expansion.expand_by_series(icalendar, library, calendar_of(vevent("one@example.invalid", {"FREQ": "DAILY"})), START, END)
        self.assertEqual(found, ["first", "second"])

    def test_a_calendar_over_the_limit_is_refused(self):
        library = self.library_returning(["first", "second", "third"])
        with mock.patch.object(feed_expansion, "EVENTS_PER_CALENDAR", 2):
            with self.assertRaises(TooManyEvents):
                feed_expansion.expand_by_series(icalendar, library, calendar_of(vevent("one@example.invalid", {"FREQ": "DAILY"})), START, END)


class TestPastEvents(unittest.TestCase):
    def test_plain_events_from_before_the_window_do_not_count_towards_the_calendar_limit(self):
        past = []
        for number in range(5):
            past.append(single("past-%d@example.invalid" % number, date(2020, 1, number + 1)))
        calendar = calendar_of(*past, single("now@example.invalid", date(2026, 10, 9)))
        with mock.patch.object(feed_expansion, "EVENTS_PER_CALENDAR", 3):
            trimmed, left_out = feed_expansion.affordable_calendar(icalendar, calendar, FIRST_DAY, LAST_DAY)
        self.assertEqual((uids(trimmed), left_out), (["now@example.invalid"], 0))


class TestLongLivedCalendars(unittest.TestCase):
    def test_moved_occurrences_from_years_ago_do_not_count_towards_the_window(self):
        components = [vevent("standup@example.invalid", {"FREQ": "DAILY"})]
        for number in range(5):
            moved = single("standup@example.invalid", date(2018, 1, number + 2))
            moved.add("RECURRENCE-ID", date(2018, 1, number + 1))
            components.append(moved)
        with mock.patch.object(feed_expansion, "DATES_BEFORE_EXPANSION", 12):
            trimmed, _ = feed_expansion.affordable_calendar(icalendar, calendar_of(*components), FIRST_DAY, LAST_DAY)
        self.assertEqual(len(uids(trimmed)), 6)

    def test_extra_dates_from_years_ago_do_not_count_towards_the_window(self):
        event = single("listed@example.invalid", date(2018, 1, 1))
        event.add("RDATE", [date(2018, 2, 1), date(2018, 3, 1), date(2018, 4, 1)])
        with mock.patch.object(feed_expansion, "DATES_BEFORE_EXPANSION", 1):
            feed_expansion.affordable_calendar(icalendar, calendar_of(event), FIRST_DAY, LAST_DAY)

    def test_more_yearly_birthdays_than_the_display_limit_still_reach_the_expansion(self):
        birthdays = []
        for number in range(30):
            birthdays.append(vevent("birthday-%d@example.invalid" % number, {"FREQ": "YEARLY"}))
        with mock.patch.object(feed_expansion, "EVENTS_PER_CALENDAR", 20):
            trimmed, left_out = feed_expansion.affordable_calendar(icalendar, calendar_of(*birthdays), FIRST_DAY, LAST_DAY)
        self.assertEqual((len(uids(trimmed)), left_out), (30, 0))


if __name__ == "__main__":
    unittest.main()
