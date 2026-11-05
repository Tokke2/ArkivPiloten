"""Screen geometry is clamped, including the minimum size, on small displays."""
from __future__ import annotations

import re

import pdfsorter as P


class _Window:
    def __init__(self, width: int, height: int):
        self.screen = (width, height)
        self.minimum = None
        self.request = None

    def winfo_screenwidth(self):
        return self.screen[0]

    def winfo_screenheight(self):
        return self.screen[1]

    def minsize(self, width: int, height: int):
        self.minimum = (width, height)

    def geometry(self, value: str):
        self.request = value


def test_large_requested_window_and_minimum_are_clamped_to_small_screen():
    window = _Window(800, 600)

    P._fit_geometry(window, 1280, 880, 1060, 720)

    match = re.fullmatch(r"(\d+)x(\d+)\+(\d+)\+(\d+)", window.request)
    assert match
    width, height, x, y = map(int, match.groups())
    assert width <= 800 and height <= 600
    assert x >= 0 and y >= 0
    assert window.minimum[0] <= width
    assert window.minimum[1] <= height


def test_geometry_keeps_requested_size_when_display_is_large():
    window = _Window(1920, 1080)

    P._fit_geometry(window, 1280, 880, 1060, 720)

    assert window.request == "1280x880+320+100"
    assert window.minimum == (1060, 720)
