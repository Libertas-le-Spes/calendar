"""A wall-clock limit on one step of the sync.

The limit is the process's interval timer, so it interrupts a library
caught in a long loop and a socket read waiting on a slow server alike.
It works in the main thread only, which is where the sync runs; anywhere
else the step refuses to start rather than run without a limit.
"""

import contextlib
import signal


class TimeBudgetSpent(Exception):
    """The step ran past its time limit."""


def _spent(_signal_number, _frame):
    raise TimeBudgetSpent()


@contextlib.contextmanager
def time_budget(seconds):
    previous = signal.signal(signal.SIGALRM, _spent)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
