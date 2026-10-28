import json
import subprocess
import sys
import unittest
from unittest import mock

from omarchy_calendar_sync import worker_process


def finished(returncode, stdout):
    return subprocess.CompletedProcess(["worker"], returncode, stdout, "")


class TestRunWorker(unittest.TestCase):
    def test_the_worker_runs_isolated_with_the_request_on_stdin_and_a_time_limit(self):
        run = mock.Mock(return_value=finished(0, '{"events": []}'))
        worker_process.run_worker({"mode": "made-up"}, 42, run=run)
        run.assert_called_once_with(
            [sys.executable, "-I", "-B", worker_process.WORKER],
            input=json.dumps({"mode": "made-up"}), capture_output=True, text=True, timeout=42,
        )

    def test_the_answer_is_returned(self):
        run = mock.Mock(return_value=finished(0, '{"events": ["made-up"]}'))
        self.assertEqual(worker_process.run_worker({}, 5, run=run), {"events": ["made-up"]})

    def test_a_worker_that_runs_out_of_time_fails(self):
        run = mock.Mock(side_effect=subprocess.TimeoutExpired(["worker"], 5))
        with self.assertRaises(worker_process.WorkerFailed):
            worker_process.run_worker({}, 5, run=run)

    def test_a_worker_that_is_killed_fails_even_after_printing_an_answer(self):
        with self.assertRaises(worker_process.WorkerFailed):
            worker_process.run_worker({}, 5, run=mock.Mock(return_value=finished(-9, '{"events": []}')))

    def test_a_worker_that_answers_nonsense_fails(self):
        for text in ("not json", "[1, 2]"):
            with self.subTest(text=text):
                with self.assertRaises(worker_process.WorkerFailed):
                    worker_process.run_worker({}, 5, run=mock.Mock(return_value=finished(0, text)))


if __name__ == "__main__":
    unittest.main()
