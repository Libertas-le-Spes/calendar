"""User configuration for the sync.

Absent config is a valid state: every key has a default, so a first run works
with no file at all.
"""

import copy
import json
import os
import stat
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from .feeds import entry_text, feed_entries

CONFIG_PATH = Path.home() / ".config" / "omarchy" / "calendar-sync.json"
OTHERS_WRITE = stat.S_IWGRP | stat.S_IWOTH
OTHERS_READ = stat.S_IRGRP | stat.S_IROTH
MAX_WINDOW_DAYS = 366

DEFAULTS = {
    # "gws" reads Google directly and needs a Google Cloud project;
    # "eds" reads Evolution Data Server and needs none; "ics" reads iCal
    # feeds such as Google's secret address and needs nothing. See the README.
    "backend": "gws",
    # Opt-in. sync/setup --write sets it, together with the calendar.events
    # scope. Off, the sync publishes no writable calendars and the panel
    # shows no way to change an event.
    "write": False,
    # ics only: feed URLs, each a string or {"url", "name", "color"}.
    "ics": [],
    # eds and ics: the address whose invitation answers count as "yours".
    # Blank means responseStatus is left unset rather than guessed.
    "identity": "",
    "profile": str(Path.home() / ".config" / "gws-omarchy-calendar"),
    # Resolved to an absolute path by sync/setup. A systemd user service
    # does not inherit an interactive shell PATH, so relying on the bare
    # name works from a terminal and fails from the timer.
    "gwsPath": "gws",
    "calendars": {"include": [], "exclude": []},
    "window": {"pastDays": 7, "futureDays": 60},
}


class ConfigError(Exception):
    """Raised when the config file exists but cannot be used."""


def load(path=None):
    """Load config, filling in defaults for anything absent."""
    path = Path(path) if path is not None else CONFIG_PATH

    if not path.exists():
        return _merge(copy.deepcopy(DEFAULTS), {})

    try:
        raw = json.loads(path.read_text())
        file_status = path.stat()
        folder_status = path.parent.stat()
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from error

    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a JSON object")

    problem = permission_problem(file_status, folder_status, holds_plain_feed_addresses(raw), os.getuid())
    if problem:
        raise ConfigError(f"{path} {problem}; run: chmod 600 {path}")

    merged = _merge(copy.deepcopy(DEFAULTS), raw)

    _validate_calendars(merged.get("calendars"))

    window = merged.get("window")
    if isinstance(window, dict):
        window["pastDays"] = _coerce_days(window.get("pastDays"), "window.pastDays")
        window["futureDays"] = _coerce_days(
            window.get("futureDays"), "window.futureDays"
        )

    return merged


def permission_problem(file_status, folder_status, holds_secrets, user_id):
    """Why the config cannot be trusted as it is stored, or blank.

    It names a program the timer runs, so nobody else may own or change it,
    or replace it through its folder; and while it holds a feed address,
    which is a password, nobody else may read it either.
    """
    if file_status.st_uid != user_id:
        return "belongs to another user"
    if file_status.st_mode & OTHERS_WRITE:
        return "can be changed by other users"
    if folder_status.st_mode & OTHERS_WRITE:
        return "is in a folder other users can change"
    if holds_secrets and file_status.st_mode & OTHERS_READ:
        return "holds feed addresses that other users can read"
    return ""


def holds_plain_feed_addresses(raw):
    for entry in feed_entries(raw.get("ics")):
        if entry_text(entry, "url"):
            return True
    return False


def _merge(defaults, override):
    """One level of nesting is all this config has, so this stays simple."""
    merged = {}
    for key, fallback in defaults.items():
        value = override.get(key, fallback)
        if value is None:
            # An explicit null for a nested key means "not set", not "empty".
            value = fallback
        if isinstance(fallback, dict) and isinstance(value, dict):
            merged[key] = {**fallback, **value}
        else:
            merged[key] = value
    return merged


def _validate_calendars(calendars):
    """Reject a non-list include or exclude instead of silently misreading it."""
    if not isinstance(calendars, dict):
        return
    for key in ("include", "exclude"):
        value = calendars.get(key)
        if value is not None and not isinstance(value, list):
            raise ConfigError(f"calendars.{key} must be a list")


def _coerce_days(value, key):
    """Turn a window day count into an int, or fail loudly naming the key."""
    days = _as_whole_number(value, key)
    if days < 0:
        raise ConfigError(f"{key} must not be negative")
    return min(days, MAX_WINDOW_DAYS)


def _as_whole_number(value, key):
    if isinstance(value, bool):
        raise ConfigError(f"{key} must be a number")
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            raise ConfigError(f"{key} must be a number") from None
    raise ConfigError(f"{key} must be a number")


def select_calendars(calendars, config):
    """Apply the include and exclude lists. Exclude always wins."""
    rules = config.get("calendars") or {}
    include = set(rules.get("include") or [])
    exclude = set(rules.get("exclude") or [])

    selected = []
    for calendar in calendars:
        keys = {calendar["id"], calendar["name"]}
        if keys & exclude:
            continue
        if include and not (keys & include):
            continue
        selected.append(calendar)
    return selected


class DayWindow(NamedTuple):
    first: date
    last: date


def local_days_in_window(config, now, local_tz):
    time_min, time_max = window_bounds(config, now)
    first = datetime.fromisoformat(time_min).astimezone(local_tz).date()
    last = datetime.fromisoformat(time_max).astimezone(local_tz).date()
    return DayWindow(first, last)


def window_bounds(config, now):
    """Return RFC3339 timeMin and timeMax for the events query."""
    window = config.get("window") or {}
    past = int(window.get("pastDays", DEFAULTS["window"]["pastDays"]))
    future = int(window.get("futureDays", DEFAULTS["window"]["futureDays"]))
    return (
        (now - timedelta(days=past)).isoformat(),
        (now + timedelta(days=future)).isoformat(),
    )
