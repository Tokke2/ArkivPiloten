# -*- coding: utf-8 -*-
"""Manuell versionssökning från högerklicksmenyn i systemfältet."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pdfsorter as P
import pdfsorter_system as S


class _FakeItem:
    def __init__(self, text, action=None, **kwargs):
        self.text = text
        self.action = action
        self.kwargs = kwargs


class _FakeMenu:
    SEPARATOR = object()

    def __init__(self, *items):
        self.items = items


def test_tray_menu_has_manual_update_action_and_posts_it_to_ui(monkeypatch):
    monkeypatch.setitem(sys.modules, "pystray", SimpleNamespace(
        MenuItem=_FakeItem, Menu=_FakeMenu))
    posted = []
    checked = []
    app = SimpleNamespace(
        watcher=None,
        queue=[],
        _post=posted.append,
        _check_updates_from_tray=lambda: checked.append(True),
        show_window=lambda *_: None,
        _sort_now=lambda: None,
        _toggle_watch=lambda: None,
        open_output=lambda: None,
        show_review=lambda: None,
        quit_app=lambda: None,
    )

    menu = S.TrayIcon(app)._build_menu()
    update = next(item for item in menu.items
                  if getattr(item, "text", None)
                  == "Sök efter uppdateringar…")
    update.action()

    assert len(posted) == 1
    assert checked == []
    posted.pop()()
    assert checked == [True]


def test_tray_update_shows_window_then_starts_manual_check():
    calls = []
    app = SimpleNamespace(
        show_window=lambda reason: calls.append(("show", reason)),
        _check_updates_gui=lambda manual=False: calls.append(("check", manual)),
    )

    P.App._check_updates_from_tray(app)

    assert calls == [
        ("show", "uppdatering via systemfältet"),
        ("check", True),
    ]
