"""Secret feed addresses kept in the desktop keyring rather than the config.

The config names a feed by an id; the address itself is stored in the
Secret Service (gnome-keyring on Omarchy) through secret-tool. Only the id
ever appears in a process argument: the address goes in on stdin.
"""

import subprocess

APPLICATION = "omarchy-calendar"
LABEL = "Omarchy calendar feed"
KEYRING_SECONDS = 30


class KeyringMissing(Exception):
    """The keyring holds no address for a feed, or cannot be asked."""


def lookup_arguments(feed_id):
    return ["secret-tool", "lookup", "application", APPLICATION, "feed", feed_id]


def lookup(feed_id, run=subprocess.run):
    """The address stored for `feed_id`, or KeyringMissing."""
    try:
        completed = run(lookup_arguments(feed_id), capture_output=True, text=True, timeout=KEYRING_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        raise KeyringMissing("the keyring could not be asked") from None
    address = completed.stdout.strip()
    if completed.returncode != 0 or not address:
        raise KeyringMissing("the keyring holds no address for this feed; run sync/setup --ics")
    return address


def store(feed_id, address, run=subprocess.run):
    """True when the keyring took `address` under `feed_id`."""
    arguments = ["secret-tool", "store", "--label", LABEL, "application", APPLICATION, "feed", feed_id]
    return _answer(run, arguments, address) == 0


def clear(feed_id, run=subprocess.run):
    _answer(run, ["secret-tool", "clear", "application", APPLICATION, "feed", feed_id])


def stored_ids(run=subprocess.run):
    """The ids of every feed address in the keyring.

    secret-tool prints the attributes on stderr and the rest on stdout.
    """
    arguments = ["secret-tool", "search", "--all", "application", APPLICATION]
    try:
        completed = run(arguments, capture_output=True, text=True, timeout=KEYRING_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return []
    ids = []
    for line in (completed.stdout + completed.stderr).splitlines():
        name, _, value = line.partition(" = ")
        if name.strip() == "attribute.feed":
            ids.append(value.strip())
    return ids


def _answer(run, arguments, given=""):
    try:
        return run(arguments, input=given, capture_output=True, text=True, timeout=KEYRING_SECONDS).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1
