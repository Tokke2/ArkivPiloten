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
                  == "Uppdatera ArkivPiloten…")
    update.action()

    assert len(posted) == 1
    assert checked == []
    posted.pop()()
    assert checked == [True]


def test_tray_tooltip_spells_out_watcher_state_and_review_count(monkeypatch):
    class _Icon:
        title = ""
        visible = False

        def update_menu(self):
            pass

    monkeypatch.setattr(S, "make_icon_image", lambda *a, **k: object())
    app = SimpleNamespace(
        watcher=SimpleNamespace(running=True),
        queue=[object(), object()],
    )
    tray = S.TrayIcon(app)
    tray.icon = _Icon()

    tray.refresh()

    assert tray.icon.visible is True
    assert tray.icon.title == (
        "ArkivPiloten · Bevakning PÅ · 2 väntar på granskning")


def test_tray_start_waits_for_visible_native_icon(monkeypatch):
    import threading

    stopped = threading.Event()

    class _Icon:
        def __init__(self, *args):
            self.visible = False
            self.title = ""

        def run(self, setup=None):
            if setup:
                setup(self)
            stopped.wait(2)

        def stop(self):
            stopped.set()

        def update_menu(self):
            pass

    monkeypatch.setattr(S.sys, "platform", "win32")
    monkeypatch.setattr(S, "tray_available", lambda: True)
    monkeypatch.setattr(S, "make_icon_image", lambda *a, **k: object())
    monkeypatch.setitem(sys.modules, "pystray", SimpleNamespace(
        Icon=_Icon, MenuItem=_FakeItem, Menu=_FakeMenu))
    app = SimpleNamespace(
        watcher=None, queue=[], _post=lambda callback: None,
        show_window=lambda: None, _check_updates_from_tray=lambda: None,
        _sort_now=lambda: None, _toggle_watch=lambda: None,
        show_review=lambda: None, open_output=lambda: None, quit_app=lambda: None,
    )
    tray = S.TrayIcon(app)

    assert tray.start() is True
    assert tray.icon.visible is True
    assert tray._thread is not None and tray._thread.is_alive()

    tray.stop()


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


def test_tray_icon_shows_badge_menu_label_and_tooltip_when_update_available(monkeypatch):
    monkeypatch.setitem(sys.modules, "pystray", SimpleNamespace(
        MenuItem=_FakeItem, Menu=_FakeMenu))

    normal_icon = S.make_icon_image(64, update_available=False)
    badge_icon = S.make_icon_image(64, update_available=True)
    if normal_icon is not None and badge_icon is not None:
        assert normal_icon.tobytes() != badge_icon.tobytes()

    seen_badge_flags = []
    monkeypatch.setattr(
        S, "make_icon_image",
        lambda size, active=False, badge=0, update_available=False: (
            seen_badge_flags.append(update_available) or object()
        ),
    )

    class _Icon:
        title = ""
        visible = False
        menu = None

        def update_menu(self):
            pass

    app = SimpleNamespace(
        watcher=None,
        queue=[],
        _available_update_info={"remote": "9.9.9"},
        _pending_restart_update=None,
        _post=lambda cb: cb(),
        _check_updates_from_tray=lambda: None,
        show_window=lambda *_: None,
        _sort_now=lambda: None,
        _toggle_watch=lambda: None,
        open_output=lambda: None,
        show_review=lambda: None,
        quit_app=lambda: None,
    )
    tray = S.TrayIcon(app)
    tray.icon = _Icon()
    tray.refresh()

    assert seen_badge_flags[-1] is True
    assert "Uppdatering: 9.9.9" in tray.icon.title
    assert tray._update_label() == "↑ Uppdatera till 9.9.9…"

    app._available_update_info = None
    app._pending_restart_update = {"to": "9.9.9"}
    tray.refresh()
    assert "Starta om för att slutföra 9.9.9" in tray.icon.title
    assert tray._update_label() == "↻ Starta om för 9.9.9…"
