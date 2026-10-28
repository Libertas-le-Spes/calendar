"""How much the sync takes in from one calendar.

Everything in a calendar can be written by someone other than the user, so
each limit stops one kind of entry from costing the sync, or the bar that
reads its file, more than a real calendar ever needs.
"""

EVENTS_PER_CALENDAR = 2000
FEED_BYTES = 16 * 1024 * 1024
REPEAT_STEPS_PER_SERIES = 200_000
REPEAT_STEPS_PER_CALENDAR = 1_000_000
FEED_SECONDS = 60
DATES_BEFORE_EXPANSION = 20_000
WORKER_MEMORY_BYTES = 768 * 1024 * 1024
WORKER_SECONDS = 60
RUN_SECONDS = 240
