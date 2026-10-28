"""How much of the events file each calendar may take.

Calendars are added in order, the primary one first. A calendar whose rows
would take the file past its row or size ceiling is left out as a whole, so
one flooded calendar never stops the others from being written.
"""

import json

from . import contract

RESERVED_BYTES = 1024 * 1024


class RowBudget:
    def __init__(self):
        self.rows = 0
        self.bytes = 0

    def admit(self, rows):
        """True, and the rows counted, when they still fit in the file."""
        size = _written_size(rows)
        if self.rows + len(rows) > contract.MAX_EVENT_ROWS:
            return False
        if self.bytes + size > contract.MAX_DOCUMENT_BYTES - RESERVED_BYTES:
            return False
        self.rows += len(rows)
        self.bytes += size
        return True


def _written_size(rows):
    return len(json.dumps(rows, ensure_ascii=False, indent=4).encode("utf-8"))
