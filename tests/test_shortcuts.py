# -*- coding: utf-8 -*-
"""Genvägar på skrivbordet/i appmenyn - utan att röra användarens filer."""
from __future__ import annotations

import pathlib
import shutil

import pytest

import pdfsorter_system as S


@pytest.fixture
def app(tmp_path, monkeypatch):
    home = tmp_path / "home"
    appdir = tmp_path / "app"
    (home / "Desktop").mkdir(parents=True)
    appdir.mkdir()
    main = appdir / "pdfsorter.py"
    main.write_text("# test\n", encoding="utf-8")
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdgdata"))
    monkeypatch.delenv("PDFSORTER_HOME", raising=False)
    S._ICON_FILE_OK = None
    S.configure(config_dir=lambda: appdir,
                now_iso=lambda: "2026-10-20T00:00:00",
                main_script=main, app_name="ArkivPiloten",
                app_version="1.1.0")
    return S, tmp_path, main


def test_linux_writes_menu_and_desktop(app, monkeypatch):
    S, tmp, _main = app
    monkeypatch.setattr(S.sys, "platform", "linux")

    ok, msg = S.create_desktop_shortcut()
    assert ok, msg
    menu = tmp / "xdgdata" / "applications" / "arkivpiloten.desktop"
    desk = tmp / "home" / "Desktop" / "arkivpiloten.desktop"
    assert menu.is_file() and desk.is_file()
    text = desk.read_text(encoding="utf-8")
    assert "Categories=Office;Utility;" in text
    assert "X-GNOME-Autostart" not in text
    assert "--tray" not in text
    assert "--tray" not in menu.read_text(encoding="utf-8")
    assert desk.stat().st_mode & 0o111, "skrivbordsgenvägen måste vara körbar"


def test_macos_command_file_quotes_special_paths(app, monkeypatch):
    S, tmp, _main = app
    monkeypatch.setattr(S.sys, "platform", "darwin")
    special = tmp / "A & B 'C'" / "pdfsorter.py"
    special.parent.mkdir()
    special.write_text("# test\n", encoding="utf-8")
    S.configure(config_dir=lambda: tmp / "app", now_iso=lambda: "x",
                main_script=special, app_name="ArkivPiloten",
                app_version="1.1.0")

    ok, msg = S.create_desktop_shortcut()
    assert ok, msg
    target = tmp / "home" / "Desktop" / "Starta ArkivPiloten.command"
    text = target.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\n")
    assert "cd '" in text and "A & B" in text
    assert target.stat().st_mode & 0o111


def test_windows_shortcut_uses_lnk_writer(app, monkeypatch):
    S, tmp, _main = app
    monkeypatch.setattr(S.sys, "platform", "win32")
    seen = {}

    def fake_lnk(target):
        seen["target"] = target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("lnk", encoding="utf-8")
        return True, str(target)

    monkeypatch.setattr(S, "_win_make_lnk", fake_lnk)
    ok, msg = S.create_desktop_shortcut()
    assert ok, msg
    assert seen["target"].name == "ArkivPiloten.lnk"
    assert seen["target"].parent == tmp / "home" / "Desktop"


def test_no_desktop_folder_reports_instead_of_creating(app, monkeypatch):
    S, tmp, _main = app
    monkeypatch.setattr(S.sys, "platform", "darwin")
    shutil.rmtree(tmp / "home" / "Desktop")
    ok, msg = S.create_desktop_shortcut()
    assert ok is False
    assert "skrivbordsmapp" in msg
