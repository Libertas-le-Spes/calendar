"""Feed addresses: the rule a safe one follows, how it is logged, and the
two kinds of feed the config can name.

A private feed's address is its password, so nothing here lets it reach a
log, and an address that breaks the rule is never fetched.
"""

import hashlib
import re
import urllib.parse

from . import keyring
from .errors import FeedProblem


def feed_url(value):
    """The fetchable URL for a configured feed. webcal:// is https://."""
    text = str(value or "").strip()
    if text.startswith("webcal://"):
        text = "https://" + text[len("webcal://"):]
    return text


def redact(url):
    """A URL safe to log: its scheme and host only.

    The path of a private feed is the credential, and an address may carry
    a user name and password before its host.
    """
    try:
        parts = urllib.parse.urlsplit(feed_url(url))
        host = parts.hostname
    except ValueError:
        return "(unreadable address)"
    if not host:
        return "(no host)"
    return "%s://%s/..." % (parts.scheme, host)


def scrubbed(text, url):
    """`text` with every secret part of `url` taken out, for printing."""
    address = feed_url(url)
    parts = urllib.parse.urlsplit(address)
    for secret in (address, parts.path, parts.query):
        if len(secret) > 1:
            text = text.replace(secret, "…")
    return text



def feed_id(url):
    """A stable calendar id that does not leak the secret URL into the file."""
    return "ics-" + hashlib.sha256(feed_url(url).encode()).hexdigest()[:12]


SECRET_HINT = (
    "use \"Secret address in iCal format\" under Settings > the calendar > "
    "Integrate calendar; it looks like .../ical/<id>/private-<code>/basic.ics"
)


def url_problem(value):
    """Why a URL is not a usable feed, or blank when it looks fine.

    Google shows the public address and the embed link right beside the
    secret one, and both are easy to copy by mistake.
    """
    url = feed_url(value)
    unsafe = unsafe_reason(url)
    if unsafe:
        return unsafe
    if "calendar.google.com" in url:
        if "/embed" in url:
            return "that is the embed link, a web page rather than a feed; " + SECRET_HINT
        if "/public/" in url:
            return ("that is the public address, which only works for a "
                    "calendar shared publicly; " + SECRET_HINT)
    return ""


_CONTROL_OR_SPACE = re.compile(r"[\x00-\x20\x7f\\]")


def unsafe_reason(url):
    """Why the sync would refuse to fetch `url`, or blank when it is safe to."""
    if not url.startswith("https://"):
        return "expected an https:// or webcal:// address"
    if _CONTROL_OR_SPACE.search(url):
        return "the address holds spaces, control characters or a backslash"
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname
    except ValueError:
        return "the address cannot be read"
    if not host:
        return "the address has no host"
    if parts.username is not None or parts.password is not None:
        return "the address carries a user name or password, which would end up in logs"
    return ""


class AddressFeed:
    """A feed whose address is written in the config."""

    def __init__(self, url, name, color):
        self.url = url
        self.name = name
        self.color = color

    def ident(self):
        return feed_id(self.url)

    def label(self):
        return redact(self.url)

    def address(self):
        return self.url


class KeyringFeed:
    """A feed whose address sync/setup stored in the keyring."""

    def __init__(self, secret_id, name, color, lookup):
        self.secret_id = secret_id
        self.name = name
        self.color = color
        self._lookup = lookup

    def ident(self):
        return self.secret_id

    def label(self):
        return "keyring feed " + self.secret_id

    def address(self):
        try:
            url = feed_url(self._lookup(self.secret_id))
        except keyring.KeyringMissing as missing:
            raise FeedProblem(str(missing)) from None
        unsafe = unsafe_reason(url)
        if unsafe:
            raise FeedProblem(unsafe)
        return url


def feed_entries(raw):
    """The `ics` config value as a list of entries, each a dict.

    The value may be one address, one object, or a list of either. This is
    the one place that knows those shapes.
    """
    if isinstance(raw, (str, dict)):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    entries = []
    for entry in raw:
        if isinstance(entry, str):
            entry = {"url": entry}
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def entry_text(entry, key):
    value = entry.get(key)
    if value is None:
        return ""
    return str(value).strip()


def parse_feeds(raw, lookup=keyring.lookup):
    """Read the `ics` config value into feeds.

    An entry holds either `url` or `secret` (a keyring id), and optionally
    `name` and `color`. Returns the feeds and, apart, the addresses refused
    as unsafe to fetch.
    """
    feeds = []
    refused = []
    for entry in feed_entries(raw):
        name = entry_text(entry, "name")
        color = entry_text(entry, "color")
        secret_id = entry_text(entry, "secret")
        if secret_id:
            feeds.append(KeyringFeed(secret_id, name, color, lookup))
            continue
        url = feed_url(entry_text(entry, "url"))
        if not url:
            continue
        if unsafe_reason(url):
            refused.append(url)
            continue
        feeds.append(AddressFeed(url, name, color))
    return feeds, refused
