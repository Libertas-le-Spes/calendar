import signal
import time
import unittest

from omarchy_calendar_sync.time_budget import TimeBudgetSpent, time_budget


def spin_until(moment):
    while time.monotonic() < moment:
        pass


def record_alarm(_signal_number, _frame):
    pass


class TestTimeBudget(unittest.TestCase):
    def test_a_step_still_running_when_its_time_is_up_is_stopped(self):
        started = time.monotonic()
        with self.assertRaises(TimeBudgetSpent):
            with time_budget(0.1):
                spin_until(started + 5)
        self.assertLess(time.monotonic() - started, 5)

    def test_the_timer_and_the_previous_handler_are_restored_after_a_step(self):
        previous = signal.signal(signal.SIGALRM, record_alarm)
        try:
            with time_budget(5):
                pass
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
            self.assertIs(signal.getsignal(signal.SIGALRM), record_alarm)
        finally:
            signal.signal(signal.SIGALRM, previous)

    def test_a_budget_cannot_start_inside_another(self):
        with time_budget(5):
            with self.assertRaises(RuntimeError):
                with time_budget(1):
                    pass

    def test_the_spent_signal_is_not_an_ordinary_exception(self):
        self.assertFalse(issubclass(TimeBudgetSpent, Exception))


if __name__ == "__main__":
    unittest.main()
