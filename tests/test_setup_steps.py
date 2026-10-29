import contextlib
import io
import os
import subprocess
import re
import unittest
from pathlib import Path
from unittest import mock

from omarchy_calendar_sync import setup_steps
from omarchy_calendar_sync.feeds import feed_id

FIRST = "https://feeds.example.invalid/private-FIRSTMADEUP.ics"
SECOND = "https://feeds.example.invalid/private-SECONDMADEUP.ics"


def answering(returncode, stdout="", stderr=""):
    return mock.Mock(return_value=subprocess.CompletedProcess(["secret-tool"], returncode, stdout, stderr))


def quietly(function, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


class TestStoreInKeyring(unittest.TestCase):
    def test_each_address_is_stored_under_its_feed_id(self):
        run = answering(0)
        entries = setup_steps.store_in_keyring([FIRST, SECOND], run)
        self.assertEqual(entries, [{"secret": feed_id(FIRST)}, {"secret": feed_id(SECOND)}])
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][-2:], ["feed", feed_id(FIRST)])

    def test_the_address_goes_in_on_stdin_and_never_as_an_argument(self):
        run = answering(0)
        setup_steps.store_in_keyring([FIRST], run)
        self.assertEqual(run.call_args.kwargs["input"], FIRST)
        self.assertNotIn(FIRST, " ".join(run.call_args.args[0]))

    def test_a_keyring_that_refuses_an_address_gives_no_entries(self):
        self.assertIsNone(setup_steps.store_in_keyring([FIRST], answering(1)))

    def test_no_secret_tool_gives_no_entries(self):
        run = mock.Mock(side_effect=FileNotFoundError("secret-tool"))
        self.assertIsNone(setup_steps.store_in_keyring([FIRST], run))


class TestForgetUnused(unittest.TestCase):
    SEARCH_OUT = "[/1]\nlabel = Omarchy calendar feed\nsecret = made-up\n[/2]\nlabel = Omarchy calendar feed\n"
    SEARCH_ERR = "attribute.application = omarchy-calendar\nattribute.feed = ics-aaaaaaaaaaaa\nattribute.feed = ics-bbbbbbbbbbbb\n"

    def test_only_the_addresses_no_longer_named_are_cleared(self):
        run = answering(0, self.SEARCH_OUT, self.SEARCH_ERR)
        setup_steps.forget_unused({"ics-aaaaaaaaaaaa"}, run)
        cleared = run.call_args_list[1:]
        self.assertEqual(len(cleared), 1)
        self.assertEqual(cleared[0].args[0], ["secret-tool", "clear", "application", "omarchy-calendar", "feed", "ics-bbbbbbbbbbbb"])

    def test_keeping_nothing_clears_every_feed_address(self):
        run = answering(0, self.SEARCH_OUT, self.SEARCH_ERR)
        setup_steps.forget_unused(set(), run)
        self.assertEqual(run.call_count, 3)


class TestWriteGws(unittest.TestCase):
    def test_switching_to_google_drops_the_feeds_from_the_config_and_the_keyring(self):
        old = {"backend": "ics", "ics": [{"secret": "ics-aaaaaaaaaaaa"}], "identity": "made-up@example.invalid"}
        with mock.patch.object(setup_steps, "read_config", autospec=True, return_value=old), \
                mock.patch.object(setup_steps, "write_private", autospec=True) as written, \
                mock.patch.object(setup_steps, "forget_unused", autospec=True) as forgotten:
            quietly(setup_steps.write_gws, "made-up.json", "/usr/bin/gws", "/made/up/profile", "1")
        config = written.call_args.args[1]
        self.assertNotIn("ics", config)
        self.assertEqual((config["backend"], config["gwsPath"], config["profile"], config["write"]), ("gws", "/usr/bin/gws", "/made/up/profile", True))
        self.assertEqual(config["identity"], "made-up@example.invalid")
        forgotten.assert_called_once_with(set(), mock.ANY)


class TestWriteIcsCandidate(unittest.TestCase):
    def write(self, run, plain_allowed="no"):
        with mock.patch.object(setup_steps, "read_config", autospec=True, return_value={"write": True}), \
                mock.patch.object(setup_steps, "write_private", autospec=True) as written:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                setup_steps.write_ics_candidate("made-up.json", "made-up.candidate", "", plain_allowed, [FIRST, ""], run)
        return written, output.getvalue()

    def test_addresses_the_keyring_takes_are_named_by_id_in_the_candidate(self):
        written, _ = self.write(answering(0))
        self.assertEqual(written.call_args.args, ("made-up.candidate", {"write": False, "backend": "ics", "ics": [{"secret": feed_id(FIRST)}]}))

    def test_when_the_keyring_refuses_nothing_is_written_until_setup_asks(self):
        with self.assertRaises(SystemExit) as raised:
            self.write(answering(1))
        self.assertEqual(raised.exception.code, setup_steps.KEYRING_REFUSED)

    def test_once_allowed_the_addresses_go_into_the_private_file_and_setup_says_so(self):
        written, output = self.write(answering(1), plain_allowed="yes")
        self.assertEqual(written.call_args.args[1]["ics"], [{"url": FIRST}])
        self.assertIn("readable by you alone", output)


class TestFinishIcs(unittest.TestCase):
    def test_addresses_the_new_config_does_not_name_are_forgotten(self):
        with mock.patch.object(setup_steps, "read_config", autospec=True, return_value={"ics": [{"secret": "ics-aaaaaaaaaaaa"}, {"url": FIRST}]}), \
                mock.patch.object(setup_steps, "forget_unused", autospec=True) as forgotten:
            setup_steps.finish_ics("made-up.json", "run")
        forgotten.assert_called_once_with({"ics-aaaaaaaaaaaa"}, "run")


class TestWritePrivate(unittest.TestCase):
    def test_the_config_is_created_private_and_then_moved_into_place(self):
        with mock.patch.object(setup_steps.os, "open", return_value=7) as opened, \
                mock.patch.object(setup_steps.os, "fchmod") as fchmod, \
                mock.patch.object(setup_steps.os, "fdopen", mock.mock_open()) as fdopen, \
                mock.patch.object(setup_steps.os, "unlink") as removed, \
                mock.patch.object(setup_steps.os, "replace") as replaced:
            setup_steps.write_private("made-up.json", {"backend": "gws"})
        removed.assert_called_once_with("made-up.json.partial")
        self.assertEqual(opened.call_args.args[0], "made-up.json.partial")
        self.assertEqual(opened.call_args.args[2], 0o600)
        flags = opened.call_args.args[1]
        self.assertTrue(flags & os.O_EXCL)
        self.assertTrue(flags & os.O_NOFOLLOW)
        fchmod.assert_called_once_with(7, 0o600)
        fdopen().write.assert_called_once_with('{\n  "backend": "gws"\n}\n')
        replaced.assert_called_once_with("made-up.json.partial", "made-up.json")


class TestMain(unittest.TestCase):
    def test_each_command_name_runs_its_step_with_the_rest_of_the_arguments(self):
        for name in setup_steps.COMMANDS:
            step = mock.Mock()
            with self.subTest(name=name), mock.patch.dict(setup_steps.COMMANDS, {name: step}):
                setup_steps.main([name, "first", "second"])
                step.assert_called_once_with("first", "second")


class TestWritePrivateFailure(unittest.TestCase):
    def test_a_write_that_fails_leaves_no_partial_file(self):
        with mock.patch.object(setup_steps.os, "open", return_value=7), \
                mock.patch.object(setup_steps.os, "fchmod", side_effect=OSError("made-up")), \
                mock.patch.object(setup_steps.os, "unlink") as removed:
            with self.assertRaises(OSError):
                setup_steps.write_private("made-up.json", {"backend": "gws"})
        self.assertEqual(removed.call_args_list, [mock.call("made-up.json.partial"), mock.call("made-up.json.partial")])


SETUP = Path(__file__).parent.parent / "sync" / "setup"


class TestSetupAsksBeforeAPlainAddress(unittest.TestCase):
    def test_the_first_attempt_never_allows_a_plain_address(self):
        first = re.search(r"(?m)^ *setup_step write-ics .*$", SETUP.read_text()).group(0)
        self.assertIn(" no 3<", first)

    def test_setup_listens_for_the_same_code_the_step_exits_with(self):
        self.assertIn('[ "$stored" = %d ]' % setup_steps.KEYRING_REFUSED, SETUP.read_text())

    def test_only_a_yes_writes_a_plain_address(self):
        answers = re.search(r'(?ms)case "\$answer" in\n(.*?)\n *esac', SETUP.read_text()).group(1)
        writing = re.findall(r"(?m)^ *(\S+)\) setup_step write-ics .* yes 3<", answers)
        self.assertEqual(writing, ["y|Y|yes|Yes"])

    def test_any_other_answer_changes_nothing(self):
        answers = re.search(r'(?ms)case "\$answer" in\n(.*?)\n *esac', SETUP.read_text()).group(1)
        default = re.search(r"(?m)^ *\*\) (.*)$", answers).group(1)
        self.assertIn("exit 1", default)
        self.assertNotIn("write-ics", default)


if __name__ == "__main__":
    unittest.main()
