"""One expanded iCalendar occurrence as a Google event resource."""

import base64
from datetime import date, datetime, timedelta

from .resources import build_event

_GOOGLE_UID_SUFFIX = "@google.com"


def google_event_url(uid, calendar_id):
    """Google Calendar's page for an event, or blank when it cannot be built.

    The feed carries no link, but Google's own link is the event id and the
    calendar id, space separated, in unpadded base64url. The id is the UID
    minus "@google.com"; an event imported from elsewhere keeps a foreign UID
    and an id the feed never reveals. A recurring event's UID names the
    series, so every occurrence opens the series.
    """
    if not calendar_id or not uid.endswith(_GOOGLE_UID_SUFFIX):
        return ""
    event_id = uid.removesuffix(_GOOGLE_UID_SUFFIX)
    eid = base64.urlsafe_b64encode(("%s %s" % (event_id, calendar_id)).encode())
    return "https://calendar.google.com/calendar/event?eid=" + eid.decode().rstrip("=")


def to_node(value, local_tz):
    """A date or datetime from icalendar as a Google start/end node.

    A floating time (no TZID, no Z) means "local time wherever you are" in
    iCalendar, so it is pinned to the local zone rather than refused.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=local_tz)
        return {"dateTime": value.isoformat()}
    if isinstance(value, date):
        return {"date": value.isoformat()}
    return None


def _text(component, name):
    value = component.get(name)
    if value is None:
        return ""
    return str(value)


def _own_partstat(component, identity):
    """The PARTSTAT of the attendee matching `identity`, or blank."""
    if not identity:
        return ""
    wanted = "mailto:%s" % identity.strip().lower()
    attendees = component.get("ATTENDEE")
    if attendees is None:
        return ""
    if not isinstance(attendees, list):
        attendees = [attendees]
    for attendee in attendees:
        if str(attendee).strip().lower() == wanted:
            return str(getattr(attendee, "params", {}).get("PARTSTAT", ""))
    return ""


def _popup_reminders(component):
    """Minutes before the start of the VALARMs that show or sound something.

    Alarms tied to the end or to an absolute time are left out: the contract
    counts back from the start. EMAIL alarms are not the widget's to raise.
    """
    minutes = set()
    for alarm in component.walk("VALARM"):
        if str(alarm.get("ACTION") or "").upper() not in ("DISPLAY", "AUDIO"):
            continue
        trigger = alarm.get("TRIGGER")
        related = getattr(trigger, "params", {}).get("RELATED", "START")
        if str(related).upper() != "START":
            continue
        offset = getattr(trigger, "dt", None)
        if isinstance(offset, timedelta) and offset <= timedelta(0):
            minutes.add(int(-offset.total_seconds()) // 60)
    return sorted(minutes)


def occurrence_to_event(component, local_tz, identity="", calendar_id=""):
    """One expanded VEVENT occurrence as a Google event resource.

    `calendar_id` is the Google calendar the feed belongs to, blank for a
    feed from anywhere else.
    """
    start = component.get("DTSTART")
    if start is None:
        return None
    start_value = start.dt

    end_value = None
    if component.get("DTEND") is not None:
        end_value = component["DTEND"].dt
    elif component.get("DURATION") is not None:
        end_value = start_value + component["DURATION"].dt
    elif isinstance(start_value, datetime):
        end_value = start_value
    else:
        end_value = start_value + timedelta(days=1)

    start_node = to_node(start_value, local_tz)
    end_node = to_node(end_value, local_tz)
    if start_node is None:
        return None

    uid = _text(component, "UID")
    return build_event(
        uid=uid,
        start_node=start_node,
        end_node=end_node,
        summary=_text(component, "SUMMARY"),
        location=_text(component, "LOCATION"),
        description=_text(component, "DESCRIPTION"),
        status=_status(component),
        conference_url=_text(component, "X-GOOGLE-CONFERENCE"),
        partstat=_own_partstat(component, identity),
        reminders=_popup_reminders(component),
        html_link=google_event_url(uid, calendar_id),
    )


def _status(component):
    if _text(component, "STATUS").upper() == "CANCELLED":
        return "cancelled"
    return ""
