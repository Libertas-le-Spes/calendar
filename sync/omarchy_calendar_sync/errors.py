"""The error a backend raises when a sync cannot be completed.

Each backend subclasses this so the CLI can report a failure without knowing
which backend produced it.
"""

from .limits import EVENTS_PER_CALENDAR


class SyncError(Exception):
    """A calendar source could not be read."""


class CalendarUnreadable(SyncError):
    """One calendar could not be read, while the others still can."""


class TooManyEvents(CalendarUnreadable):
    """One calendar holds more events in the window than the sync takes."""

    def __init__(self):
        super().__init__("more than %d events in the sync window" % EVENTS_PER_CALENDAR)


class FeedProblem(Exception):
    """A feed could not be read. The message is safe to log."""


class FeedTooLarge(FeedProblem):
    """A feed is larger than any real calendar the sync reads."""
