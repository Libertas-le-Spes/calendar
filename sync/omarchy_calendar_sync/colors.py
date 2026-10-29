"""The colour each calendar is drawn in.

A calendar's own colour is kept when it follows the file contract. One with
no colour, or one the contract would refuse, takes the next of Google's
calendar colours, so two such calendars still look different on the grid.
"""

from .contract import is_color

CALENDAR_COLORS = ("#4285f4", "#f6bf26", "#33b679", "#e67c73", "#8e24aa", "#f4511e", "#039be5", "#7986cb")


def usable_color(color, position):
    if is_color(color):
        return color
    return CALENDAR_COLORS[position % len(CALENDAR_COLORS)]
