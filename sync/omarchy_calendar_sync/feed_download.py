"""Downloading one feed, refused once it is too large or too slow."""

import urllib.error
import urllib.request

from . import web
from .errors import FeedProblem, FeedTooLarge
from .limits import FEED_BYTES, FEED_SECONDS
from .time_budget import TimeBudgetSpent, time_budget

FETCH_TIMEOUT = 30
CHUNK_BYTES = 64 * 1024
USER_AGENT = "omarchy-calendar-sync"


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with time_budget(FEED_SECONDS):
            with web.open_public(request, FETCH_TIMEOUT) as response:
                return read_capped(response, FEED_BYTES)
    except TimeBudgetSpent:
        raise FeedProblem("the feed took longer than %d seconds to arrive" % FEED_SECONDS) from None
    except urllib.error.HTTPError as error:
        raise FeedProblem("the server answered HTTP %d" % error.code) from None


def read_capped(stream, limit):
    """The whole body, refused once it passes `limit` bytes.

    read1 hands back whatever has arrived, so a server sending a byte at a
    time cannot hold one call for the length of a whole chunk.
    """
    chunks = []
    size = 0
    while True:
        chunk = stream.read1(CHUNK_BYTES)
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if size > limit:
            raise FeedTooLarge("the feed is larger than %d bytes" % limit)
        chunks.append(chunk)
