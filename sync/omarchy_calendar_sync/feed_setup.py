"""The steps sync/setup takes with feed addresses and the config file.

Addresses arrive on file descriptor 3 and go into the keyring on stdin, so
none of them is ever a process argument. Every config is written private.
"""

import json
import os
import subprocess
from pathlib import Path

from .ics import feed_id
from .keyring import APPLICATION

LABEL = "Omarchy calendar feed"
KEYRING_SECONDS = 30


def store_in_keyring(urls, run=subprocess.run):
    """Config entries for `urls`, by keyring id, or None when the keyring refused one."""
    entries = []
    for url in urls:
        secret_id = feed_id(url)
        if not _stored(secret_id, url, run):
            return None
        entries.append({"secret": secret_id})
    return entries


def plain_entries(urls):
    entries = []
    for url in urls:
        entries.append({"url": url})
    return entries


def forget_unused(keep, run=subprocess.run):
    """Clear every feed address in the keyring whose id is not in `keep`."""
    for secret_id in _stored_ids(run):
        if secret_id not in keep:
            _run(run, ["secret-tool", "clear", "application", APPLICATION, "feed", secret_id])


def keyring_ids(config):
    ids = set()
    feeds = config.get("ics")
    if not isinstance(feeds, list):
        return ids
    for feed in feeds:
        if isinstance(feed, dict) and feed.get("secret"):
            ids.add(str(feed["secret"]))
    return ids


def read_config(path):
    try:
        config = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(config, dict):
        return {}
    return config


def write_private(path, config):
    """Replace `path` with `config`, readable and writable by the user alone."""
    partial = str(path) + ".partial"
    handle = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(handle, 0o600)
    with os.fdopen(handle, "w") as stream:
        stream.write(json.dumps(config, indent=2) + "\n")
    os.replace(partial, path)


def write_ics_candidate(config_path, candidate, identity, addresses=None, run=subprocess.run):
    """The config setup --ics tests before it replaces the current one."""
    urls = _given_addresses(addresses)
    entries = store_in_keyring(urls, run)
    if entries is None:
        print("  The keyring did not take the addresses, so they stay in the config file,")
        print("  readable by you alone.")
        entries = plain_entries(urls)
    else:
        print("  The addresses are in your keyring; the config names them by id.")
    config = read_config(config_path)
    config["backend"] = "ics"
    config["ics"] = entries
    config["write"] = False
    if identity:
        config["identity"] = identity
    write_private(candidate, config)


def finish_ics(config_path, run=subprocess.run):
    """After the tested config is in place, forget addresses it no longer names."""
    forget_unused(keyring_ids(read_config(config_path)), run)


def write_gws(config_path, gws_path, profile, write, run=subprocess.run):
    """Select the Google Cloud sync, dropping every feed address left from --ics."""
    config = read_config(config_path)
    config["backend"] = "gws"
    config["gwsPath"] = gws_path
    config["profile"] = profile
    config["write"] = write == "1"
    config.pop("ics", None)
    write_private(config_path, config)
    forget_unused(set(), run)
    print("  backend set to gws")
    print("  gwsPath set to", gws_path)
    print("  profile set to", profile)
    print("  write set to", config["write"])


COMMANDS = {
    "write-ics": write_ics_candidate,
    "finish-ics": finish_ics,
    "write-gws": write_gws,
}


def main(argv):
    command = COMMANDS[argv[0]]
    command(*argv[1:])


def _given_addresses(addresses):
    if addresses is None:
        with os.fdopen(3) as stream:
            addresses = stream.read().splitlines()
    urls = []
    for line in addresses:
        if line.strip():
            urls.append(line.strip())
    return urls


def _stored(secret_id, url, run):
    arguments = ["secret-tool", "store", "--label", LABEL, "application", APPLICATION, "feed", secret_id]
    return _run(run, arguments, url) == 0


def _stored_ids(run):
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


def _run(run, arguments, given=""):
    try:
        return run(arguments, input=given, capture_output=True, text=True, timeout=KEYRING_SECONDS).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1
