import configparser
import unittest
from pathlib import Path

UNIT = Path(__file__).parent.parent / "sync" / "systemd" / "omarchy-calendar-sync.service"

LIMITS = {
    "TimeoutStartSec": "5min",
    "MemoryMax": "1G",
    "MemorySwapMax": "0",
    "TasksMax": "64",
}

HARDENING = {
    "NoNewPrivileges": "yes",
    "LockPersonality": "yes",
    "RestrictRealtime": "yes",
    "RestrictSUIDSGID": "yes",
    "RestrictNamespaces": "yes",
    "RestrictAddressFamilies": "AF_UNIX AF_INET AF_INET6 AF_NETLINK",
    "SystemCallArchitectures": "native",
    "SystemCallFilter": "@system-service",
    "ProtectSystem": "full",
    "PrivateTmp": "yes",
}


def service_section():
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read_string(UNIT.read_text())
    return parser["Service"]


class TestSyncUnit(unittest.TestCase):
    def test_a_run_that_hangs_or_grows_is_cut_off(self):
        service = service_section()
        for key, value in LIMITS.items():
            with self.subTest(key=key):
                self.assertEqual(service.get(key), value)

    def test_the_sync_runs_sandboxed(self):
        service = service_section()
        for key, value in HARDENING.items():
            with self.subTest(key=key):
                self.assertEqual(service.get(key), value)


if __name__ == "__main__":
    unittest.main()
