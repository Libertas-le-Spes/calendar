import io
import json
import sys
import unittest
from unittest import mock

from omarchy_calendar_sync import worker_process


class KeptOpen(io.BytesIO):
    def close(self):
        pass


class FakeChild:
    def __init__(self, answer=b"", returncode=0, hangs=False):
        self.stdin = KeptOpen()
        self.stdout = io.BytesIO(answer)
        self.returncode = None
        self.finishes_with = returncode
        self.hangs = hangs
        self.killed = False

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self):
        if self.returncode is None:
            self.returncode = self.finishes_with
        return self.returncode


def starting(child):
    return mock.Mock(return_value=child)


ANSWER = json.dumps({"events": [{"summary": "Made-up"}], "left_out": 0, "unconvertible": 0}).encode()


class TestRunWorker(unittest.TestCase):
    def test_the_worker_runs_isolated_with_the_request_on_stdin(self):
        child = FakeChild(ANSWER)
        start = starting(child)
        worker_process.run_worker({"mode": "made-up"}, 42, start=start)
        self.assertEqual(start.call_args.args[0], [sys.executable, "-I", "-B", worker_process.WORKER])
        self.assertEqual(child.stdin.getvalue(), json.dumps({"mode": "made-up"}).encode())

    def test_the_answer_is_returned(self):
        answer = worker_process.run_worker({}, 5, start=starting(FakeChild(ANSWER)))
        self.assertEqual(answer["events"], [{"summary": "Made-up"}])

    def test_a_child_that_answers_and_exits_is_waited_for_not_killed(self):
        child = FakeChild(ANSWER)
        worker_process.run_worker({}, 5, start=starting(child))
        self.assertEqual((child.killed, child.returncode), (False, 0))

    def test_an_answer_larger_than_the_cap_fails_and_the_child_is_stopped(self):
        child = FakeChild(b"x" * 11)
        with mock.patch.object(worker_process, "MAX_ANSWER_BYTES", 10), mock.patch.object(worker_process, "CHUNK_BYTES", 4):
            with self.assertRaises(worker_process.WorkerFailed) as raised:
                worker_process.run_worker({}, 5, start=starting(child))
        self.assertIn("larger than 10 bytes", str(raised.exception))
        self.assertTrue(child.killed)

    def test_a_worker_still_running_at_its_time_limit_is_stopped_and_fails(self):
        child = FakeChild(ANSWER)

        def fire_at_once(seconds, action):
            timer = mock.Mock()
            timer.start.side_effect = action
            return timer

        with mock.patch.object(worker_process.threading, "Timer", side_effect=fire_at_once):
            with self.assertRaises(worker_process.WorkerFailed) as raised:
                worker_process.run_worker({}, 5, start=starting(child))
        self.assertIn("longer than 5 seconds", str(raised.exception))
        self.assertTrue(child.killed)

    def test_a_worker_that_is_killed_fails_even_after_printing_an_answer(self):
        with self.assertRaises(worker_process.WorkerFailed):
            worker_process.run_worker({}, 5, start=starting(FakeChild(ANSWER, returncode=-9)))

    def test_an_answer_that_is_not_an_object_of_events_fails(self):
        for text in (b"not json", b"[1, 2]", b'{"events": "x", "left_out": 0, "unconvertible": 0}',
                     b'{"events": [1], "left_out": 0, "unconvertible": 0}', b'{"events": [], "left_out": "2", "unconvertible": 0}',
                     b'{"events": [], "left_out": true, "unconvertible": 0}', b'{"events": [], "left_out": 0}'):
            with self.subTest(text=text):
                with self.assertRaises(worker_process.WorkerFailed):
                    worker_process.run_worker({}, 5, start=starting(FakeChild(text)))

    def test_a_problem_is_passed_on_as_text(self):
        answer = worker_process.run_worker({}, 5, start=starting(FakeChild(b'{"problem": "made-up"}')))
        self.assertEqual(answer, {"problem": "made-up"})


if __name__ == "__main__":
    unittest.main()
