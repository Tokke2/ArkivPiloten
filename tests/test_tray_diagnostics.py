# -*- coding: utf-8 -*-
"""The support report distinguishes a running tray icon from availability."""
from __future__ import annotations

from types import SimpleNamespace

import pdfsorter as P


class _Thread:
    def is_alive(self):
        return True


def _running_app():
    return SimpleNamespace(
        tray=SimpleNamespace(
            icon=SimpleNamespace(visible=True),
            _thread=_Thread(),
            _detached=False,
        ),
        watcher=SimpleNamespace(running=True),
        queue=[object(), object()],
        settings={"tray_enabled": True},
    )


def test_runtime_report_shows_icon_visibility_loop_and_watcher(monkeypatch):
    monkeypatch.setattr(P, "tray_backend_name", lambda: "pystray._win32")
    text = P._tray_runtime_status(_running_app())

    assert "aktiverat=True" in text
    assert "ikon=skapad" in text and "synlig=ja" in text
    assert "loop=igång" in text and "backend=pystray._win32" in text
    assert "bevakning=PÅ" in text and "väntar=2" in text


def test_runtime_report_explains_that_no_tray_icon_was_created(monkeypatch):
    monkeypatch.setattr(P, "tray_backend_name", lambda: "")
    app = SimpleNamespace(tray=None, watcher=None, queue=[], settings={})

    text = P._tray_runtime_status(app)

    assert "ikon=ej skapad" in text
    assert "synlig=nej" in text
    assert "loop=saknas" in text
    assert "backend=okänd" in text


def test_ai_report_includes_live_tray_runtime(monkeypatch):
    monkeypatch.setattr(P, "_TAB_WHEEL_APP", _running_app())
    monkeypatch.setattr(P, "_module_versions", lambda: {"main": "1.4.14"})
    monkeypatch.setattr(P, "VERSIONS_BLANDADE", False)
    monkeypatch.setattr(P, "load_settings", lambda: {
        "input_dir": "", "output_dir": "", "exclude_dirs": [],
        "tray_enabled": True,
    })
    monkeypatch.setattr(P, "backend_status", lambda: {})
    monkeypatch.setattr(P, "autostart_enabled", lambda: False)
    monkeypatch.setattr(P, "tray_available", lambda: True)
    monkeypatch.setattr(P, "tray_backend_name", lambda: "pystray._win32")
    monkeypatch.setattr(P.Rules, "load", lambda: SimpleNamespace(categories=[]))

    lines = P._diag_extra()

    assert any(line.startswith("Systemfält (körning):")
               and "synlig=ja" in line for line in lines)
