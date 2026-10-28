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


if __name__ == "__main__":
    unittest.main()
