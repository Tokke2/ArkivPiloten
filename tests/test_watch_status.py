# -*- coding: utf-8 -*-
"""The dashboard shows live watcher activity timestamps."""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pdfsorter as P


class _Label:
    def __init__(self):
        self.text = ""

    def configure(self, *, text):
        self.text = text


def _app():
    label = _Label()
    app = SimpleNamespace(
        _watch_status_lock=threading.Lock(),
        _watch_last_found=None,
        _watch_last_sorted=None,
        lbl_watch_activity=label,
        _post=lambda callback: callback(),
    )
    app._watch_activity_text = lambda: P.App._watch_activity_text(app)
    app._refresh_watch_activity = lambda: P.App._refresh_watch_activity(app)
    return app, label


def test_dashboard_starts_with_no_watcher_activity():
    app, label = _app()

    P.App._refresh_watch_activity(app)

    assert label.text == "Senast hittad: aldrig · autosorterad: aldrig"


def test_detected_and_sorted_events_refresh_their_own_timestamps():
    app, label = _app()

    P.App._note_watch_activity(app, found=True)
    assert label.text.startswith("Senast hittad: i dag ")
    assert label.text.endswith("autosorterad: aldrig")

    P.App._note_watch_activity(app, sorted_file=True)
    assert label.text.startswith("Senast hittad: i dag ")
    assert " · autosorterad: i dag " in label.text
