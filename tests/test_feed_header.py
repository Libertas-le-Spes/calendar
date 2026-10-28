import unittest

from omarchy_calendar_sync.feed_header import HEADER_BYTES, feed_header


def body(*lines):
    return ("\r\n".join(("BEGIN:VCALENDAR",) + lines + ("END:VCALENDAR",)) + "\r\n").encode()


class TestFeedHeader(unittest.TestCase):
    def test_the_name_and_colour_before_the_first_event_are_read(self):
        found = feed_header(body("X-WR-CALNAME:Made-up team", "X-APPLE-CALENDAR-COLOR:#a1b2c3", "BEGIN:VEVENT", "END:VEVENT"))
        self.assertEqual(found, {"name": "Made-up team", "color": "#a1b2c3"})

    def test_a_name_inside_an_event_is_not_the_feeds(self):
        found = feed_header(body("BEGIN:VEVENT", "X-WR-CALNAME:Made-up inside", "END:VEVENT"))
        self.assertEqual(found["name"], "")

    def test_escaped_text_is_read_as_plain_text(self):
        self.assertEqual(feed_header(body("X-WR-CALNAME:Made-up\\, team\\; north"))["name"], "Made-up, team; north")

    def test_a_property_with_parameters_is_still_read(self):
        self.assertEqual(feed_header(body("X-WR-CALNAME;VALUE=TEXT:Made-up"))["name"], "Made-up")

    def test_only_the_start_of_the_feed_is_read(self):
        padded = b"BEGIN:VCALENDAR\r\n" + b"X-PAD:" + b"x" * HEADER_BYTES + b"\r\nX-WR-CALNAME:Made-up late\r\n"
        self.assertEqual(feed_header(padded)["name"], "")

    def test_a_long_name_folded_over_lines_is_read_whole(self):
        folded = b"BEGIN:VCALENDAR\r\nX-WR-CALNAME:Made-up Engineering Department Shared Team Cal\r\n endar for Planning\r\nEND:VCALENDAR\r\n"
        self.assertEqual(feed_header(folded)["name"], "Made-up Engineering Department Shared Team Calendar for Planning")

    def test_a_name_after_a_time_zone_block_is_still_the_feeds(self):
        found = feed_header(body("BEGIN:VTIMEZONE", "TZID:Made/Up", "END:VTIMEZONE", "X-WR-CALNAME:Made-up after zone", "X-APPLE-CALENDAR-COLOR:#123456", "BEGIN:VEVENT", "END:VEVENT"))
        self.assertEqual(found, {"name": "Made-up after zone", "color": "#123456"})

    def test_a_property_name_in_lower_case_is_read(self):
        self.assertEqual(feed_header(body("x-wr-calname:Made-up lower"))["name"], "Made-up lower")

    def test_an_escaped_backslash_before_an_n_stays_a_backslash(self):
        self.assertEqual(feed_header(body("X-WR-CALNAME:Made-up a\\\\nb"))["name"], "Made-up a\\nb")


if __name__ == "__main__":
    unittest.main()
