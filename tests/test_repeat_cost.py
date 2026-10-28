import unittest
from datetime import date, datetime, timezone

import icalendar

from omarchy_calendar_sync import repeat_cost

LAST_DAY = date(2026, 10, 30)


def vevent(start, rule=None, rdates=None):
    event = icalendar.Event()
    event.add("UID", "made-up@example.invalid")
    if start is not None:
        event.add("DTSTART", start)
    if rule is not None:
        event.add("RRULE", rule)
    if rdates is not None:
        event.add("RDATE", rdates)
    return event


class TestSeriesCost(unittest.TestCase):
    def test_an_event_that_does_not_repeat_costs_nothing_to_expand(self):
        self.assertEqual(repeat_cost.series_cost(vevent(date(2026, 10, 1)), LAST_DAY), 0)

    def test_a_daily_series_costs_one_step_per_day_up_to_the_last_day(self):
        cost = repeat_cost.series_cost(vevent(date(2026, 10, 21), {"FREQ": "DAILY"}), LAST_DAY)
        self.assertEqual(cost, 10)

    def test_a_series_every_second_costs_every_second_of_every_day(self):
        start = datetime(2026, 10, 21, tzinfo=timezone.utc)
        cost = repeat_cost.series_cost(vevent(start, {"FREQ": "SECONDLY"}), LAST_DAY)
        self.assertEqual(cost, 10 * 86400)

    def test_an_interval_spreads_a_sub_daily_series_out(self):
        start = datetime(2026, 10, 30, tzinfo=timezone.utc)
        cost = repeat_cost.series_cost(vevent(start, {"FREQ": "HOURLY", "INTERVAL": 2}), LAST_DAY)
        self.assertEqual(cost, 12)

    def test_hours_minutes_and_seconds_listed_on_a_daily_series_multiply_its_cost(self):
        rule = {"FREQ": "DAILY", "BYHOUR": [9, 17], "BYMINUTE": [0, 30], "BYSECOND": [0, 1, 2]}
        cost = repeat_cost.series_cost(vevent(date(2026, 10, 30), rule), LAST_DAY)
        self.assertEqual(cost, 12)

    def test_minutes_listed_on_a_series_every_minute_narrow_it_rather_than_multiply(self):
        start = datetime(2026, 10, 30, tzinfo=timezone.utc)
        rule = {"FREQ": "MINUTELY", "BYMINUTE": [0, 30]}
        self.assertEqual(repeat_cost.series_cost(vevent(start, rule), LAST_DAY), 1440)

    def test_a_count_smaller_than_the_walk_is_the_cost(self):
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        rule = {"FREQ": "SECONDLY", "COUNT": 5}
        self.assertEqual(repeat_cost.series_cost(vevent(start, rule), LAST_DAY), 5)

    def test_an_unknown_frequency_is_costed_as_every_second(self):
        start = datetime(2026, 10, 30, tzinfo=timezone.utc)
        self.assertEqual(repeat_cost.series_cost(vevent(start, {"FREQ": "MADEUPLY"}), LAST_DAY), 86400)

    def test_each_extra_date_costs_one_step(self):
        extra = [date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4)]
        self.assertEqual(repeat_cost.series_cost(vevent(date(2026, 10, 1), rdates=extra), LAST_DAY), 3)

    def test_an_event_with_no_start_costs_nothing(self):
        self.assertEqual(repeat_cost.series_cost(vevent(None, {"FREQ": "SECONDLY"}), LAST_DAY), 0)

    def test_two_rules_on_one_event_add_up(self):
        event = vevent(date(2026, 10, 30), {"FREQ": "DAILY"})
        event.add("RRULE", {"FREQ": "HOURLY"})
        self.assertEqual(repeat_cost.series_cost(event, LAST_DAY), 1 + 24)


if __name__ == "__main__":
    unittest.main()
