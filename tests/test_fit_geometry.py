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


class _MaximizableWindow(_Window):
    def __init__(self, width: int, height: int, support_zoomed: bool):
        super().__init__(width, height)
        self.support_zoomed = support_zoomed
        self.state_request = None
        self.current_state = "normal"
        self.idle_callback = None

    def state(self, value=None):
        if value is None:
            return self.current_state
        if not self.support_zoomed:
            raise RuntimeError("window manager does not support zoomed state")
        self.state_request = value
        self.current_state = value

    def after_idle(self, callback):
        self.idle_callback = callback

    def attributes(self, *_args):
        raise RuntimeError("zoomed attribute unavailable")


def test_maximize_requests_zoomed_window_state():
    window = _MaximizableWindow(1920, 1080, support_zoomed=True)

    assert P._maximize_window(window)
    assert window.state_request == "zoomed"
    assert window.request is None


def test_maximize_falls_back_to_screen_aligned_geometry():
    window = _MaximizableWindow(1920, 1080, support_zoomed=False)

    assert P._maximize_window(window)
    assert window.request == "1920x1080+0+0"


def test_map_event_retries_maximize_after_window_manager_maps_window():
    window = _MaximizableWindow(1920, 1080, support_zoomed=True)

    P._maximize_after_map(window)

    assert window.state_request is None
    assert window.idle_callback is not None
    window.idle_callback()
    assert window.state_request == "zoomed"


def test_map_event_leaves_minimized_window_and_child_events_alone():
    window = _MaximizableWindow(1920, 1080, support_zoomed=True)
    window.current_state = "iconic"
    P._maximize_after_map(window)
    assert window.idle_callback is None

    window.current_state = "normal"
    child_event = type("Event", (), {"widget": object()})()
    P._maximize_after_map(window, child_event)
    assert window.idle_callback is None
