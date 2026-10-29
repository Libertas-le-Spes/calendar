"""What the sync sends a feed's worker: the local time zone, described so a
separate process can rebuild it."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def describe_zone(tz):
    key = getattr(tz, "key", None)
    if key:
        return {"key": key}
    return {"offset_seconds": int(datetime.now(tz).utcoffset().total_seconds())}


def zone_from(described):
    if "key" in described:
        return ZoneInfo(described["key"])
    return timezone(timedelta(seconds=described["offset_seconds"]))
