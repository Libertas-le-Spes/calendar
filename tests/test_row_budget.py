import unittest
from unittest import mock

from omarchy_calendar_sync import contract, row_budget


def rows(count, title="Made-up"):
    found = []
    for number in range(count):
        found.append({"id": "made-up-%d" % number, "title": title})
    return found


class TestRowBudget(unittest.TestCase):
    def test_rows_up_to_the_row_ceiling_are_admitted(self):
        budget = row_budget.RowBudget()
        with mock.patch.object(contract, "MAX_EVENT_ROWS", 5):
            self.assertTrue(budget.admit(rows(3)))
            self.assertTrue(budget.admit(rows(2)))

    def test_rows_that_would_pass_the_row_ceiling_are_refused_and_not_counted(self):
        budget = row_budget.RowBudget()
        with mock.patch.object(contract, "MAX_EVENT_ROWS", 5):
            self.assertTrue(budget.admit(rows(3)))
            self.assertFalse(budget.admit(rows(3)))
            self.assertTrue(budget.admit(rows(2)))

    def test_rows_that_would_pass_the_size_ceiling_are_refused(self):
        budget = row_budget.RowBudget()
        with mock.patch.object(contract, "MAX_DOCUMENT_BYTES", row_budget.RESERVED_BYTES + 200):
            self.assertFalse(budget.admit(rows(1, title="x" * 300)))
            self.assertTrue(budget.admit(rows(1)))


class TestReserve(unittest.TestCase):
    def test_room_is_kept_for_the_rest_of_the_file(self):
        size = contract.written_size(rows(1))
        budget = row_budget.RowBudget()
        with mock.patch.object(contract, "MAX_DOCUMENT_BYTES", size + row_budget.RESERVED_BYTES - 1):
            self.assertFalse(budget.admit(rows(1)))


if __name__ == "__main__":
    unittest.main()
