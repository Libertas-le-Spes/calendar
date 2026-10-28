"""Running a feed's work in a separate, limited process.

The child gets the request on stdin and answers on stdout. However it
ends, a crash, a kill for memory or a timeout costs only that feed.
"""

import json
import subprocess
import sys
from pathlib import Path

WORKER = str(Path(__file__).resolve().parent.parent / "omarchy-calendar-feed-worker")


class WorkerFailed(Exception):
    """The child did not answer. The message is safe to log."""


def run_worker(request, seconds, run=subprocess.run):
    try:
        done = run(
            [sys.executable, "-I", "-B", WORKER],
            input=json.dumps(request), capture_output=True, text=True, timeout=seconds,
        )
    except subprocess.TimeoutExpired:
        raise WorkerFailed("reading the feed took longer than %d seconds" % seconds) from None
    if done.returncode != 0:
        raise WorkerFailed("reading the feed ran out of memory or stopped")
    return _answer(done.stdout)


def _answer(text):
    try:
        answer = json.loads(text)
    except ValueError:
        raise WorkerFailed("reading the feed gave no answer") from None
    if not isinstance(answer, dict):
        raise WorkerFailed("reading the feed gave no answer")
    return answer
