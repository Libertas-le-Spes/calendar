"""Downloading one feed, refused once it is too large or too slow."""

import time
import urllib.error
import urllib.request

from . import web
from .errors import FeedProblem, FeedTooLarge
from .limits import FEED_BYTES

FETCH_TIMEOUT = 30
FEED_SECONDS = 60
CHUNK_BYTES = 64 * 1024
USER_AGENT = "omarchy-calendar-sync"


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    deadline = time.monotonic() + FEED_SECONDS
    try:
        with web.open_public(request, FETCH_TIMEOUT) as response:
            return read_capped(response, FEED_BYTES, deadline)
    except urllib.error.HTTPError as error:
        raise FeedProblem("the server answered HTTP %d" % error.code) from None


def read_capped(stream, limit, deadline, clock=time.monotonic):
    """The whole body, refused once it passes `limit` bytes or the deadline."""
    chunks = []
    size = 0
    while True:
        if clock() > deadline:
            raise FeedProblem("the feed took longer than %d seconds to arrive" % FEED_SECONDS)
        chunk = stream.read(CHUNK_BYTES)
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if size > limit:
            raise FeedTooLarge("the feed is larger than %d bytes" % limit)
        chunks.append(chunk)
