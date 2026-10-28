import unittest
from datetime import date, timedelta

import icalendar

from omarchy_calendar_sync import window_events


def vevent(start, rule=None):
    event = icalendar.Event()
    event.add("UID", "made-up@example.invalid")
    event.add("DTSTART", start)
    if rule is not None:
        event.add("RRULE", rule)
    return event


class TestWhichEventsArePlain(unittest.TestCase):
    def test_an_event_that_neither_repeats_nor_moves_an_occurrence_is_plain(self):
        self.assertTrue(window_events.is_single(vevent(date(2026, 10, 9))))

    def test_a_repeating_event_is_not_plain(self):
        self.assertFalse(window_events.is_single(vevent(date(2026, 10, 9), {"FREQ": "DAILY"})))

    def test_a_plain_event_ending_inside_the_window_touches_it(self):
        event = vevent(date(2026, 9, 1))
        event.add("DTEND", date(2026, 10, 2))
        self.assertTrue(window_events.touches(event, date(2026, 10, 1), date(2026, 10, 31)))

    def test_a_plain_event_before_the_window_does_not_touch_it(self):
        self.assertFalse(window_events.touches(vevent(date(2026, 9, 1)), date(2026, 10, 1), date(2026, 10, 31)))

    def test_a_moved_occurrence_is_not_plain(self):
        moved = vevent(date(2026, 10, 9))
        moved.add("RECURRENCE-ID", date(2026, 10, 8))
        self.assertFalse(window_events.is_single(moved))


class TestEventsWithADuration(unittest.TestCase):
    WINDOW = (date(2026, 10, 21), date(2026, 12, 27))

    def test_an_event_whose_duration_runs_into_the_window_touches_it(self):
        event = vevent(date(2026, 10, 15))
        event.add("DURATION", timedelta(days=20))
        self.assertTrue(window_events.touches(event, *self.WINDOW))

    def test_an_event_whose_duration_ends_before_the_window_does_not_touch_it(self):
        event = vevent(date(2026, 10, 1))
        event.add("DURATION", timedelta(days=2))
        self.assertFalse(window_events.touches(event, *self.WINDOW))

    def test_an_event_whose_end_cannot_be_read_is_kept(self):
        event = vevent(date(2026, 10, 1))
        event["DTEND"] = icalendar.vText("not a date")
        self.assertTrue(window_events.touches(event, *self.WINDOW))


if __name__ == "__main__":
    unittest.main()
