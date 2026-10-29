"""A feed's own name and colour, read from the lines before its first entry.

Reading them takes no parser, so the sync never parses a feed outside the
limited process that expands it. Folded lines are joined, property names
match in any case, and a time zone block before the first entry is passed
over.
"""

import re

HEADER_BYTES = 64 * 1024

_FOLD = re.compile(rb"\r?\n[ \t]")
_FIRST_ENTRY = re.compile(rb"^BEGIN:(VEVENT|VTODO|VJOURNAL)\b", re.MULTILINE | re.IGNORECASE)
_PROPERTY = re.compile(rb"^(X-WR-CALNAME|X-APPLE-CALENDAR-COLOR)(?:;[^:\r\n]*)?:([^\r\n]*)\r?$", re.MULTILINE | re.IGNORECASE)
_KEYS = {b"X-WR-CALNAME": "name", b"X-APPLE-CALENDAR-COLOR": "color"}
_HELD_BACKSLASH = "\x00"
_ESCAPES = (("\\\\", _HELD_BACKSLASH), ("\\,", ","), ("\\;", ";"), ("\\n", " "), ("\\N", " "), (_HELD_BACKSLASH, "\\"))


def feed_header(body):
    """{"name", "color"} from the start of `body`, blank where missing."""
    head = _before_first_entry(_unfolded(_start_of(body)))
    found = {"name": "", "color": ""}
    for match in _PROPERTY.finditer(head):
        found[_KEYS[match.group(1).upper()]] = _text_value(match.group(2))
    return found


def _start_of(body):
    return body[:HEADER_BYTES]


def _unfolded(head):
    return _FOLD.sub(b"", head)


def _before_first_entry(head):
    match = _FIRST_ENTRY.search(head)
    if match is None:
        return head
    return head[: match.start()]


def _text_value(raw):
    text = raw.decode("utf-8", "replace").strip()
    for escaped, plain in _ESCAPES:
        text = text.replace(escaped, plain)
    return text
