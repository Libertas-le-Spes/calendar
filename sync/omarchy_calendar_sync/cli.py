"""Entry point. Orchestrates config, a backend, normalization, and the write."""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import config as config_module
from . import colors, contract, normalize, suggestions
from .eds import Eds
from .errors import CalendarUnreadable, SyncError
from .gws import Gws
from .ics import Ics
from .localzone import resolve_local_timezone
from .row_budget import RowBudget

EXIT_OK = 0
EXIT_SYNC_FAILED = 1
EXIT_BAD_CONFIG = 2


def write_atomic(path, text):
    """Write a serialized document so a reader never observes a partial file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def occurrence_key(gevent):
    """Identity of one occurrence, shared by its copies in several calendars.

    An event you can see from two calendars is returned once per calendar,
    and listing it twice is noise.

    iCalUID alone is NOT a safe key. Every instance of a recurring series
    carries the same one, verified against live data: a daily standup came
    back as five events with five distinct ids and a single shared iCalUID.
    Keying on it alone would collapse the whole series into one entry.

    The start instant is what separates instances of a series while still
    matching the same occurrence seen from two different calendars.

    Returns None when the event carries no iCalUID, which means never
    deduplicate it. Dropping a real event is worse than showing it twice.
    """
    uid = gevent.get("iCalUID")
    if not uid:
        return None

    start = gevent.get("start") or {}
    return (uid, start.get("dateTime") or start.get("date"))


def _drop_duplicates(gevents, seen, calendar):
    """Filter copies of events seen in an earlier calendar. Mutates `seen`.

    The primary calendar goes first and the rest follow by name. A later
    copy is left out when it says the same as the first one (title, end,
    link, location, description and reminders), or when the
    first came from the primary calendar. A copy that differs from one in
    any other calendar is kept, so no calendar can hide or replace an event
    that another calendar shows. Write access proves nothing here: anyone
    can share a calendar and grant it.
    """
    fresh = []
    for gevent in gevents:
        key = occurrence_key(gevent)
        if key is None:
            fresh.append(gevent)
            continue
        first = seen.get(key)
        if first is None:
            seen[key] = (_content(gevent), _is_own(calendar))
            fresh.append(gevent)
            continue
        if not _covered_by(first, gevent):
            fresh.append(gevent)
    return fresh


def _covered_by(first, gevent):
    first_content, first_is_own = first
    return first_is_own or first_content == _content(gevent)


def _content(gevent):
    """Everything about a copy the user would see or be reminded by."""
    return (
        _text_of(gevent, "summary"),
        _end_of(gevent),
        normalize.meeting_url(gevent),
        _text_of(gevent, "location"),
        _text_of(gevent, "description"),
        json.dumps(gevent.get("reminders"), sort_keys=True),
    )


def _text_of(gevent, key):
    value = gevent.get(key)
    if value is None:
        return ""
    return str(value)


def _end_of(gevent):
    end = gevent.get("end")
    if not isinstance(end, dict):
        return None
    if "dateTime" in end:
        return end["dateTime"]
    return end.get("date")


def _is_own(calendar):
    return calendar.get("primary") is True


def _give_usable_colors(calendars):
    for position, calendar in enumerate(calendars):
        calendar["color"] = colors.usable_color(calendar.get("color"), position)


def _sound_rows(rows, calendar):
    sound = []
    for row in rows:
        if not contract.event_problems(row):
            sound.append(row)
    dropped = len(rows) - len(sound)
    if dropped:
        print(f"dropping {dropped} rows from calendar {calendar['name']!r}: they break the contract", file=sys.stderr)
    return sound


def _events_or_skip(client, calendar, time_min, time_max):
    try:
        return client.events(calendar["id"], time_min, time_max)
    except CalendarUnreadable as error:
        print(f"skipping calendar {calendar['name']!r}: {error}", file=sys.stderr)
        return None


def run(client, cfg, now, out_path, local_tz):
    """Fetch, normalize, write. Returns a process exit code."""
    try:
        client.check()
        calendars = config_module.select_calendars(client.calendars(), cfg)
        # Your own copy of a shared event carries your title, colour and
        # answer. A colleague's copy can carry none of them (a calendar shared
        # as free/busy has no titles), so the primary calendar wins the
        # dedup. The sort is stable, so the rest keep their name order.
        calendars.sort(key=lambda calendar: not calendar.get("primary"))
        _give_usable_colors(calendars)
        time_min, time_max = config_module.window_bounds(cfg, now)
        window = config_module.local_days_in_window(cfg, now, local_tz)

        rows = []
        seen = {}
        fetched = []
        skipped = 0
        budget = RowBudget()
        for calendar in calendars:
            raw = _events_or_skip(client, calendar, time_min, time_max)
            if raw is None:
                skipped += 1
                continue
            seen_with_these = dict(seen)
            fresh = _drop_duplicates(raw, seen_with_these, calendar)
            calendar_rows = _sound_rows(normalize.normalize_all(fresh, calendar, local_tz, window), calendar)
            if not budget.admit(calendar_rows):
                print(f"skipping calendar {calendar['name']!r}: its events would make the events file too large", file=sys.stderr)
                skipped += 1
                continue
            seen = seen_with_these
            fetched.extend(fresh)
            rows.extend(calendar_rows)

        if calendars and skipped == len(calendars):
            raise SyncError("every calendar was skipped")

        source = client.SOURCE_NAME + "/" + ".".join(
            str(part) for part in client.version()
        )
    except SyncError as error:
        print(f"sync failed: {error}", file=sys.stderr)
        hint = client.auth_hint(cfg)
        if hint:
            print(hint, file=sys.stderr)
        return EXIT_SYNC_FAILED

    rows.sort(key=normalize.row_order)
    # The panel offers edits only for these. Only when the user turned
    # writing on and the backend can write; otherwise the key is absent.
    writable = []
    if cfg.get("write") and getattr(client, "can_write", False):
        writable = [
            {"id": c["id"], "name": c["name"], "color": c["color"]}
            for c in calendars
            if c.get("writable")
        ]
    # Only for the event form, so only when writing is on.
    guests = []
    if writable:
        guests = suggestions.guest_suggestions(fetched, [c["id"] for c in calendars])
    doc = contract.build_document(rows, now.isoformat(), source, writable, guests)

    text, problems = contract.checked(doc)
    if problems:
        for problem in problems:
            print(f"refusing to write invalid document: {problem}", file=sys.stderr)
        return EXIT_SYNC_FAILED

    write_atomic(out_path, text)
    print(f"wrote {len(rows)} rows from {len(calendars)} calendars to {out_path}")
    return EXIT_OK


def build_client(cfg, local_tz=None):
    """The calendar source named by the config."""
    backend = str(cfg.get("backend") or "gws").strip().lower()
    if backend == "gws":
        return Gws(cfg["profile"], binary=cfg["gwsPath"])
    if backend == "eds":
        return Eds(identity=cfg.get("identity", ""))
    if backend == "ics":
        return Ics(cfg.get("ics"), identity=cfg.get("identity", ""), local_tz=local_tz)
    raise config_module.ConfigError(
        "unknown backend %r; expected \"gws\", \"eds\" or \"ics\"" % backend
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="omarchy-calendar-sync",
        description="Sync your calendars into the Omarchy calendar widget file.",
    )
    parser.add_argument("--config", default=None, help="path to calendar-sync.json")
    parser.add_argument("--out", default=None, help="path to the contract file")
    args = parser.parse_args(argv)

    try:
        cfg = config_module.load(args.config)
    except config_module.ConfigError as error:
        print(f"config error: {error}", file=sys.stderr)
        return EXIT_BAD_CONFIG

    out_path = Path(args.out) if args.out else contract.CONTRACT_PATH
    now = datetime.now(timezone.utc)
    local_tz = resolve_local_timezone()

    try:
        client = build_client(cfg, local_tz)
    except config_module.ConfigError as error:
        print(f"config error: {error}", file=sys.stderr)
        return EXIT_BAD_CONFIG

    return run(client, cfg, now, out_path, local_tz)


if __name__ == "__main__":
    sys.exit(main())
