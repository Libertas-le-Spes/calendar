"""A feed's own name and colour, read from the lines before its first event.

Reading them takes no parser, so the sync never parses a feed outside the
limited process that expands it.
"""

import re

HEADER_BYTES = 64 * 1024

_PROPERTY = re.compile(rb"^(X-WR-CALNAME|X-APPLE-CALENDAR-COLOR)(?:;[^:\r\n]*)?:([^\r\n]*)\r?$", re.MULTILINE)
_FIRST_COMPONENT = re.compile(rb"^BEGIN:(?!VCALENDAR)", re.MULTILINE)


def feed_header(body):
    """{"name", "color"} from the start of `body`, blank where missing."""
    head = _before_first_component(body[:HEADER_BYTES])
    found = {"name": "", "color": ""}
    for match in _PROPERTY.finditer(head):
        found[_KEYS[match.group(1)]] = _text_value(match.group(2))
    return found


_KEYS = {b"X-WR-CALNAME": "name", b"X-APPLE-CALENDAR-COLOR": "color"}


def _before_first_component(head):
    match = _FIRST_COMPONENT.search(head)
    if match is None:
        return head
    return head[: match.start()]


def _text_value(raw):
    text = raw.decode("utf-8", "replace").strip()
    for escaped, plain in _ESCAPES:
        text = text.replace(escaped, plain)
    return text


_ESCAPES = (("\\,", ","), ("\\;", ";"), ("\\n", " "), ("\\\\", "\\"))
