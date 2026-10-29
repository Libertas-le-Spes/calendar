import subprocess
import unittest
from unittest import mock

from omarchy_calendar_sync import keyring


def completed(returncode, stdout):
    return subprocess.CompletedProcess(["secret-tool"], returncode, stdout, "")


class TestLookup(unittest.TestCase):
    def test_secret_tool_is_asked_for_the_feed_by_its_id_alone(self):
        run = mock.Mock(return_value=completed(0, "https://feeds.example.invalid/a.ics\n"))
        keyring.lookup("ics-0123456789ab", run=run)
        run.assert_called_once_with(
            ["secret-tool", "lookup", "application", "omarchy-calendar", "feed", "ics-0123456789ab"],
            capture_output=True, text=True, timeout=keyring.KEYRING_SECONDS,
        )

    def test_the_stored_address_is_returned_without_its_newline(self):
        run = mock.Mock(return_value=completed(0, "https://feeds.example.invalid/a.ics\n"))
        self.assertEqual(keyring.lookup("ics-0123456789ab", run=run), "https://feeds.example.invalid/a.ics")

    def test_nothing_stored_is_missing(self):
        run = mock.Mock(return_value=completed(1, ""))
        with self.assertRaises(keyring.KeyringMissing):
            keyring.lookup("ics-0123456789ab", run=run)

    def test_an_empty_answer_is_missing(self):
        run = mock.Mock(return_value=completed(0, "\n"))
        with self.assertRaises(keyring.KeyringMissing):
            keyring.lookup("ics-0123456789ab", run=run)

    def test_no_secret_tool_is_missing(self):
        run = mock.Mock(side_effect=FileNotFoundError("secret-tool"))
        with self.assertRaises(keyring.KeyringMissing):
            keyring.lookup("ics-0123456789ab", run=run)

    def test_a_keyring_that_does_not_answer_in_time_is_missing(self):
        run = mock.Mock(side_effect=subprocess.TimeoutExpired(["secret-tool"], keyring.KEYRING_SECONDS))
        with self.assertRaises(keyring.KeyringMissing):
            keyring.lookup("ics-0123456789ab", run=run)


if __name__ == "__main__":
    unittest.main()
