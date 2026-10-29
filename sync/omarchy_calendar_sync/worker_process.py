"""Running a feed's work in a separate, limited process.

The child gets the request on stdin and answers on stdout. However it
ends, a crash, a kill for memory or a timeout costs only that feed, and
its answer is read only up to a fixed size, so it cannot exhaust the sync.
"""

import json
import subprocess
import sys
import threading
from pathlib import Path

WORKER = str(Path(__file__).resolve().parent.parent / "omarchy-calendar-feed-worker")
CHUNK_BYTES = 64 * 1024
MAX_ANSWER_BYTES = 64 * 1024 * 1024


class WorkerFailed(Exception):
    """The child did not answer. The message is safe to log."""


def run_worker(request, seconds, start=subprocess.Popen):
    child = start(
        [sys.executable, "-I", "-B", WORKER],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    late = threading.Event()

    def stop_late():
        late.set()
        child.kill()

    timer = threading.Timer(seconds, stop_late)
    timer.start()
    try:
        text = _exchange(child, json.dumps(request).encode("utf-8"))
        child.wait()
    except BaseException:
        _stop(child)
        raise
    finally:
        timer.cancel()
    if late.is_set():
        raise WorkerFailed("reading the feed took longer than %d seconds" % seconds)
    if child.returncode != 0:
        raise WorkerFailed("reading the feed ran out of memory or stopped")
    return _answer(text)


def _exchange(child, request_bytes):
    try:
        child.stdin.write(request_bytes)
        child.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    chunks = []
    size = 0
    while True:
        chunk = child.stdout.read1(CHUNK_BYTES)
        if not chunk:
            return b"".join(chunks).decode("utf-8", "replace")
        size += len(chunk)
        if size > MAX_ANSWER_BYTES:
            raise WorkerFailed("reading the feed gave an answer larger than %d bytes" % MAX_ANSWER_BYTES)
        chunks.append(chunk)


def _stop(child):
    if child.poll() is None:
        child.kill()
    child.wait()


def _answer(text):
    try:
        answer = json.loads(text)
    except ValueError:
        raise WorkerFailed("reading the feed gave no answer") from None
    if not isinstance(answer, dict):
        raise WorkerFailed("reading the feed gave no answer")
    if "problem" in answer:
        return {"problem": str(answer["problem"])}
    if not _well_formed(answer):
        raise WorkerFailed("reading the feed gave no answer")
    return answer


def _well_formed(answer):
    events = answer.get("events")
    if not isinstance(events, list):
        return False
    for event in events:
        if not isinstance(event, dict):
            return False
    for count in ("left_out", "unconvertible"):
        value = answer.get(count)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return False
    return True
