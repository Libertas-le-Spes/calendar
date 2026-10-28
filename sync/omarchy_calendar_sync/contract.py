"""The file contract between the sync and the widget.

This module is the single source of truth for the shape of
~/.local/state/omarchy/calendar-events.json. Both the writer and the tests
import it, so the schema can never drift between them.
"""

import json
import re
from pathlib import Path

from .plaintext import DESCRIPTION_LIMIT

CONTRACT_VERSION = 1
CONTRACT_PATH = Path.home() / ".local" / "state" / "omarchy" / "calendar-events.json"

EVENT_FIELDS = (
    "id",
    "calendarId",
    "calendarName",
    "color",
    "dateKey",
    "start",
    "end",
    "allDay",
    "title",
    "location",
)

# Deliberately optional. The README promises that anything able to write this
# file works, so khal, vdirsyncer and hand-rolled scripts are consumers of this
# schema. Making a new field required would break every one of them on upgrade.
# Validated for type when present, never demanded.
OPTIONAL_EVENT_FIELDS = (
    "meetingUrl",
    "eventUrl",
    "eventType",
    "responseStatus",
    "description",
    "reminders",
)
_OPTIONAL_STRING_FIELDS = tuple(f for f in OPTIONAL_EVENT_FIELDS if f != "reminders")

MAX_EVENT_ROWS = 8000
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024

FIELD_LENGTHS = {
    "id": 1024,
    "calendarId": 1024,
    "calendarName": 200,
    "start": 64,
    "end": 64,
    "title": 500,
    "location": 500,
    "meetingUrl": 2048,
    "eventUrl": 2048,
    "eventType": 64,
    "responseStatus": 64,
    "description": DESCRIPTION_LIMIT,
}

MAX_GUEST_SUGGESTIONS = 200
SUGGESTION_LENGTHS = {"email": 254, "name": 100}

_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

# https only. Meeting links arrive from whoever sent the invitation, so the
# widget must never be handed a scheme it would be unwise to launch. Must
# match Model.safeUrl exactly: when the widget is stricter than the sync, a
# URL is written, then silently refused, and there is no button and no error.
_HTTPS_URL = re.compile(
    r"^https://[^\s\"'<>\\@/?#\x00-\x1f\x7f]+"
    r"(?:[/?#][^\s\"'<>\\\x00-\x1f\x7f]*)?$"
)


CALENDAR_COLORS = ("#4285f4", "#f6bf26", "#33b679", "#e67c73", "#8e24aa", "#f4511e", "#039be5", "#7986cb")


def usable_color(color, position):
    """`color` when it follows the contract, else a stand-in that keeps calendars apart."""
    if isinstance(color, str) and _COLOR.match(color):
        return color
    return CALENDAR_COLORS[position % len(CALENDAR_COLORS)]


def is_https_url(text):
    """True when `text` is a URL the widget will agree to launch."""
    return isinstance(text, str) and bool(_HTTPS_URL.match(text))


def build_document(events, synced_at, source, writable_calendars=None, guest_suggestions=None):
    """Assemble a contract document from already normalized event rows.

    writableCalendars is written only when the sync may write, so a file
    from a read-only setup or from another writer carries no such key.
    """
    doc = {
        "version": CONTRACT_VERSION,
        "syncedAt": synced_at,
        "source": source,
        "events": events,
    }
    if writable_calendars:
        doc["writableCalendars"] = writable_calendars
    if guest_suggestions:
        doc["guestSuggestions"] = guest_suggestions
    return doc


def validate(doc):
    """Return a list of human readable problems. An empty list means valid."""
    problems = []

    if not isinstance(doc, dict):
        return ["document is not an object"]

    if doc.get("version") != CONTRACT_VERSION:
        problems.append(
            f"version must be {CONTRACT_VERSION}, got {doc.get('version')!r}"
        )

    for key in ("syncedAt", "source"):
        if not isinstance(doc.get(key), str) or not doc.get(key):
            problems.append(f"{key} must be a non-empty string")

    events = doc.get("events")
    if not isinstance(events, list):
        problems.append("events must be a list")
        return problems
    if len(events) > MAX_EVENT_ROWS:
        problems.append(f"events holds {len(events)} rows, more than {MAX_EVENT_ROWS}")
        return problems

    if "writableCalendars" in doc:
        problems.extend(_validate_writable(doc["writableCalendars"]))
    if "guestSuggestions" in doc:
        problems.extend(_validate_suggestions(doc["guestSuggestions"]))

    for index, event in enumerate(events):
        problems.extend(_validate_event(index, event))

    return problems


def event_problems(event):
    """Why one row breaks the contract, or an empty list when it is sound."""
    return _validate_event(0, event)


def serialize(doc):
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def size_problem(text):
    """Why a serialized document is too large for the widget, or blank."""
    size = len(text.encode("utf-8"))
    if size > MAX_DOCUMENT_BYTES:
        return f"the document is {size} bytes, more than {MAX_DOCUMENT_BYTES}"
    return ""


def _validate_suggestions(suggestions):
    if not isinstance(suggestions, list):
        return ["guestSuggestions must be a list"]
    if len(suggestions) > MAX_GUEST_SUGGESTIONS:
        return [f"guestSuggestions holds more than {MAX_GUEST_SUGGESTIONS} entries"]
    problems = []
    for index, item in enumerate(suggestions):
        where = f"guestSuggestions[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{where} is not an object")
            continue
        if not isinstance(item.get("email"), str) or not item.get("email"):
            problems.append(f"{where}.email must be a non-empty string")
        if "name" in item and not isinstance(item["name"], str):
            problems.append(f"{where}.name must be a string when present")
        problems.extend(_suggestion_length_problems(where, item))
    return problems


def _suggestion_length_problems(where, item):
    problems = []
    for field, limit in SUGGESTION_LENGTHS.items():
        value = item.get(field)
        if isinstance(value, str) and len(value) > limit:
            problems.append(f"{where}.{field} is longer than {limit} characters")
    return problems


def _validate_writable(writable):
    if not isinstance(writable, list):
        return ["writableCalendars must be a list"]
    problems = []
    for index, calendar in enumerate(writable):
        where = f"writableCalendars[{index}]"
        if not isinstance(calendar, dict):
            problems.append(f"{where} is not an object")
            continue
        for field in ("id", "name", "color"):
            value = calendar.get(field)
            if not isinstance(value, str) or not value:
                problems.append(f"{where}.{field} must be a non-empty string")
    return problems


def _validate_event(index, event):
    where = f"events[{index}]"
    if not isinstance(event, dict):
        return [f"{where} is not an object"]

    problems = []
    for field in EVENT_FIELDS:
        if field not in event:
            problems.append(f"{where}.{field} is missing")

    if not isinstance(event.get("allDay"), bool):
        problems.append(f"{where}.allDay must be a boolean")

    date_key = event.get("dateKey")
    if not isinstance(date_key, str) or not _DATE_KEY.match(date_key):
        problems.append(f"{where}.dateKey must look like YYYY-MM-DD")

    color = event.get("color")
    if not isinstance(color, str) or not _COLOR.match(color):
        problems.append(f"{where}.color must look like #rrggbb")

    for field in ("id", "calendarId", "calendarName", "start", "end", "title"):
        if field in event and not isinstance(event[field], str):
            problems.append(f"{where}.{field} must be a string")

    for field in _OPTIONAL_STRING_FIELDS:
        if field in event and not isinstance(event[field], str):
            problems.append(f"{where}.{field} must be a string when present")

    for field in ("meetingUrl", "eventUrl"):
        value = event.get(field)
        if isinstance(value, str) and value and not is_https_url(value):
            problems.append(f"{where}.{field} must be an https URL")

    if "reminders" in event and not _is_minutes_list(event["reminders"]):
        problems.append(f"{where}.reminders must be a list of non-negative integers when present")

    problems.extend(_length_problems(where, event))
    return problems


def _length_problems(where, event):
    problems = []
    for field, limit in FIELD_LENGTHS.items():
        value = event.get(field)
        if isinstance(value, str) and len(value) > limit:
            problems.append(f"{where}.{field} is longer than {limit} characters")
    return problems


def _is_minutes_list(value):
    # bool is an int subclass, and true is not a number of minutes.
    return isinstance(value, list) and all(
        isinstance(m, int) and not isinstance(m, bool) and m >= 0 for m in value
    )
