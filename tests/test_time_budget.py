import time
import unittest

from omarchy_calendar_sync.time_budget import TimeBudgetSpent, time_budget


class TestTimeBudget(unittest.TestCase):
    def test_a_step_still_running_when_its_time_is_up_is_stopped(self):
        started = time.monotonic()
        with self.assertRaises(TimeBudgetSpent):
            with time_budget(0.1):
                while True:
                    pass
        self.assertLess(time.monotonic() - started, 5)

    def test_a_step_that_finishes_in_time_returns_normally(self):
        with time_budget(5):
            finished = True
        self.assertTrue(finished)

    def test_the_limit_is_cleared_after_the_step(self):
        with time_budget(0.1):
            pass
        time.sleep(0.2)


if __name__ == "__main__":
    unittest.main()
