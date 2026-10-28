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


def cost(start, rule):
    return repeat_cost.series_cost(vevent(start, rule), LAST_DAY)


class TestSubDailyRules(unittest.TestCase):
    def test_a_series_every_second_costs_every_second_of_every_day(self):
        self.assertEqual(cost(datetime(2026, 10, 21, tzinfo=timezone.utc), {"FREQ": "SECONDLY"}), 10 * 86400)

    def test_an_interval_spreads_a_sub_daily_series_out(self):
        self.assertEqual(cost(datetime(2026, 10, 30, tzinfo=timezone.utc), {"FREQ": "HOURLY", "INTERVAL": 2}), 12)

    def test_minutes_listed_on_a_series_every_minute_narrow_it_rather_than_multiply(self):
        self.assertEqual(cost(datetime(2026, 10, 30, tzinfo=timezone.utc), {"FREQ": "MINUTELY", "BYMINUTE": [0, 30]}), 1440)

    def test_an_unknown_frequency_is_costed_as_every_second(self):
        self.assertEqual(cost(datetime(2026, 10, 30, tzinfo=timezone.utc), {"FREQ": "MADEUPLY"}), 86400)


class TestDailyAndLongerRules(unittest.TestCase):
    def test_a_daily_series_costs_one_step_per_day_up_to_the_last_day(self):
        self.assertEqual(cost(date(2026, 10, 21), {"FREQ": "DAILY"}), 10)

    def test_a_yearly_birthday_from_1970_costs_one_step_per_year(self):
        self.assertEqual(cost(date(1970, 5, 12), {"FREQ": "YEARLY"}), 57)

    def test_a_birthday_that_names_its_month_and_day_stays_cheap(self):
        rule = {"FREQ": "YEARLY", "BYMONTH": [5], "BYMONTHDAY": [12]}
        self.assertEqual(cost(date(1970, 5, 12), rule), 57 * 12)

    def test_a_weekly_series_costs_its_weeks_times_its_listed_days(self):
        rule = {"FREQ": "WEEKLY", "BYDAY": ["MO", "TU", "WE", "TH", "FR"]}
        self.assertEqual(cost(date(2026, 10, 3), rule), 4 * 5)

    def test_listed_days_never_cost_more_than_every_day_of_the_period(self):
        rule = {"FREQ": "YEARLY", "BYYEARDAY": list(range(1, 367)), "BYMONTHDAY": list(range(1, 32))}
        self.assertEqual(cost(date(2026, 1, 1), rule), 366)

    def test_hours_minutes_and_seconds_listed_on_a_daily_series_multiply_its_cost(self):
        rule = {"FREQ": "DAILY", "BYHOUR": [9, 17], "BYMINUTE": [0, 30], "BYSECOND": [0, 1, 2]}
        self.assertEqual(cost(date(2026, 10, 30), rule), 12)


class TestWhatTheRuleSaysAboutItsEnd(unittest.TestCase):
    def test_a_count_does_not_lower_the_cost_since_it_limits_the_dates_kept_not_tried(self):
        rule = {"FREQ": "HOURLY", "COUNT": 1, "BYMONTH": [2], "BYMONTHDAY": [30]}
        self.assertEqual(cost(datetime(2026, 10, 21, tzinfo=timezone.utc), rule), 10 * 24)

    def test_the_walk_stops_at_until(self):
        rule = {"FREQ": "DAILY", "UNTIL": date(2026, 10, 25)}
        self.assertEqual(cost(date(2026, 10, 21), rule), 5)

    def test_an_until_after_the_last_day_stops_at_the_last_day(self):
        rule = {"FREQ": "DAILY", "UNTIL": date(2030, 1, 1)}
        self.assertEqual(cost(date(2026, 10, 21), rule), 10)


class TestDatesInTheWindow(unittest.TestCase):
    WINDOW = (date(2026, 10, 1), date(2026, 10, 31))

    def dates(self, start, rule=None):
        return repeat_cost.window_dates(vevent(start, rule), *self.WINDOW)

    def test_a_plain_event_lands_once(self):
        self.assertEqual(self.dates(date(2026, 10, 9)), 1)

    def test_a_daily_series_from_years_ago_lands_once_a_day_of_the_window(self):
        self.assertEqual(self.dates(date(2015, 1, 1), {"FREQ": "DAILY"}), 31)

    def test_a_series_that_ended_before_the_window_lands_nowhere(self):
        self.assertEqual(self.dates(date(2015, 1, 1), {"FREQ": "DAILY", "UNTIL": date(2016, 1, 1)}), 0)


class TestWhichEventsArePlain(unittest.TestCase):
    def test_an_event_that_neither_repeats_nor_moves_an_occurrence_is_plain(self):
        self.assertTrue(repeat_cost.is_single(vevent(date(2026, 10, 9))))

    def test_a_repeating_event_is_not_plain(self):
        self.assertFalse(repeat_cost.is_single(vevent(date(2026, 10, 9), {"FREQ": "DAILY"})))

    def test_a_plain_event_ending_inside_the_window_touches_it(self):
        event = vevent(date(2026, 9, 1))
        event.add("DTEND", date(2026, 10, 2))
        self.assertTrue(repeat_cost.touches(event, date(2026, 10, 1), date(2026, 10, 31)))

    def test_a_plain_event_before_the_window_does_not_touch_it(self):
        self.assertFalse(repeat_cost.touches(vevent(date(2026, 9, 1)), date(2026, 10, 1), date(2026, 10, 31)))


class TestTheWholeEvent(unittest.TestCase):
    def test_an_event_that_does_not_repeat_costs_nothing_to_expand(self):
        self.assertEqual(repeat_cost.series_cost(vevent(date(2026, 10, 1)), LAST_DAY), 0)

    def test_each_extra_date_costs_one_step(self):
        extra = [date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4)]
        self.assertEqual(repeat_cost.series_cost(vevent(date(2026, 10, 1), rdates=extra), LAST_DAY), 3)

    def test_an_event_with_no_start_cannot_be_costed(self):
        with self.assertRaises(ValueError):
            repeat_cost.series_cost(vevent(None, {"FREQ": "SECONDLY"}), LAST_DAY)

    def test_an_interval_of_zero_cannot_be_costed(self):
        with self.assertRaises(ValueError):
            cost(date(2026, 10, 1), {"FREQ": "DAILY", "INTERVAL": 0})

    def test_two_rules_on_one_event_add_up(self):
        event = vevent(date(2026, 10, 30), {"FREQ": "DAILY"})
        event.add("RRULE", {"FREQ": "HOURLY"})
        self.assertEqual(repeat_cost.series_cost(event, LAST_DAY), 1 + 24)


if __name__ == "__main__":
    unittest.main()
