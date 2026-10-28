"""Secret feed addresses kept in the desktop keyring rather than the config.

The config names a feed by an id; the address itself is stored in the
Secret Service (gnome-keyring on Omarchy) by sync/setup and read back here
through secret-tool. Only the id ever appears in a process argument.
"""

import subprocess

APPLICATION = "omarchy-calendar"
LOOKUP_SECONDS = 30


class KeyringMissing(Exception):
    """The keyring holds no address for a feed, or cannot be asked."""


def lookup_arguments(feed_id):
    return ["secret-tool", "lookup", "application", APPLICATION, "feed", feed_id]


def lookup(feed_id, run=subprocess.run):
    """The address stored for `feed_id`, or KeyringMissing."""
    try:
        completed = run(lookup_arguments(feed_id), capture_output=True, text=True, timeout=LOOKUP_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        raise KeyringMissing("the keyring could not be asked") from None
    address = completed.stdout.strip()
    if completed.returncode != 0 or not address:
        raise KeyringMissing("the keyring holds no address for this feed; run sync/setup --ics")
    return address
