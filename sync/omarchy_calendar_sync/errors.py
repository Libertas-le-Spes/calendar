"""The error a backend raises when a sync cannot be completed.

Each backend subclasses this so the CLI can report a failure without knowing
which backend produced it.
"""


class SyncError(Exception):
    """A calendar source could not be read."""


class CalendarUnreadable(SyncError):
    """One calendar could not be read, while the others still can."""


class TooManyEvents(CalendarUnreadable):
    """One calendar holds more events in the window than the sync takes."""
