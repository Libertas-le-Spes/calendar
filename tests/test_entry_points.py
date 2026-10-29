import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SYNC_DIR = Path(__file__).resolve().parents[1] / "sync"


class TestEntryPoints(unittest.TestCase):
    def test_compiled_modules_stay_out_of_the_plugin_folder(self):
        # The shell reloads the plugin on any change in its folder. A .pyc
        # written there by the first run after an update closed the panel and
        # killed a save halfway, after Google had the event.
        with tempfile.TemporaryDirectory() as tmp:
            plugin_sync = Path(tmp) / "plugin" / "sync"
            shutil.copytree(SYNC_DIR, plugin_sync, ignore=shutil.ignore_patterns("__pycache__"))
            cache = Path(tmp) / "cache"
            env = {**os.environ, "XDG_CACHE_HOME": str(cache), "HOME": tmp}
            env.pop("PYTHONDONTWRITEBYTECODE", None)
            env.pop("PYTHONPYCACHEPREFIX", None)

            subprocess.run([sys.executable, str(plugin_sync / "omarchy-calendar-event")],
                           input='{"action": "nope"}', env=env, capture_output=True, text=True, timeout=60)
            subprocess.run([sys.executable, str(plugin_sync / "omarchy-calendar-sync"), "--help"],
                           env=env, capture_output=True, text=True, timeout=60)

            self.assertEqual(list(plugin_sync.rglob("__pycache__")), [])
            self.assertTrue(any((cache / "omarchy-calendar").rglob("event_cli*.pyc")))
            self.assertTrue(any((cache / "omarchy-calendar").rglob("cli*.pyc")))

    def test_the_feed_worker_answers_from_an_installed_plugin_folder(self):
        feed = (
            "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:made-up@example.invalid\r\n"
            "DTSTART:20261009T090000Z\r\nDTEND:20261009T100000Z\r\nSUMMARY:Made-up\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        ).encode()
        request = {
            "body": base64.b64encode(feed).decode("ascii"),
            "start": "2026-10-01T00:00:00+00:00",
            "end": "2026-10-31T00:00:00+00:00",
            "zone": {"key": "UTC"},
            "identity": "",
            "google_id": "",
        }
        with tempfile.TemporaryDirectory() as tmp:
            plugin_sync = Path(tmp) / "plugin" / "sync"
            shutil.copytree(SYNC_DIR, plugin_sync, ignore=shutil.ignore_patterns("__pycache__"))
            env = {**os.environ, "HOME": tmp, "PYTHONPATH": "/made/up/elsewhere"}
            done = subprocess.run([sys.executable, "-I", "-B", str(plugin_sync / "omarchy-calendar-feed-worker")],
                                  input=json.dumps(request), env=env, capture_output=True, text=True, timeout=60)
            answer = json.loads(done.stdout)
            self.assertEqual([event["summary"] for event in answer["events"]], ["Made-up"])
            self.assertEqual(list(plugin_sync.rglob("__pycache__")), [])


if __name__ == "__main__":
    unittest.main()
