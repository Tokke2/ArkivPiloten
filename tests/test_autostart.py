# -*- coding: utf-8 -*-
"""Autostart på alla tre operativsystem, utan att röra riktiga inställningar.

Testerna byter sys.platform och använder tillfälliga HOME/APPDATA/XDG-mappar.
Windows-registret simuleras med en liten modul; macOS launchctl mockas.
"""
from __future__ import annotations

import configparser
import pathlib
import plistlib
import sys
import types

import pytest

import pdfsorter_system as S


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Konfigurera systemmodulen mot en tillfällig appmapp."""
    home = tmp_path / "home"
    appdir = tmp_path / "app"
    home.mkdir()
    appdir.mkdir()
    main = appdir / "pdfsorter.py"
    main.write_text("# test\n", encoding="utf-8")
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("PDFSORTER_HOME", raising=False)
    S._ICON_FILE_OK = None
    S.configure(config_dir=lambda: appdir,
                now_iso=lambda: "2026-10-20T00:00:00",
                main_script=main,
                app_name="ArkivPiloten",
                app_version="1.1.0")
    return S, tmp_path, main


def _parse_desktop(path: pathlib.Path) -> configparser.RawConfigParser:
    parser = configparser.ConfigParser(interpolation=None,
                                       delimiters=("=",), strict=False)
    parser.optionxform = str
    parser.read_string(path.read_text(encoding="utf-8"))
    return parser


# -- Linux -----------------------------------------------------------------
def test_linux_roundtrip(app, monkeypatch):
    S, tmp, _main = app
    monkeypatch.setattr(S.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp / "xdg"))
    monkeypatch.setenv("DISPLAY", ":99")

    ok, msg = S.set_autostart(True)
    assert ok, msg
    desktop = tmp / "xdg" / "autostart" / "arkivpiloten.desktop"
    assert desktop.is_file()
    parser = _parse_desktop(desktop)
    entry = parser["Desktop Entry"]
    assert entry["Type"] == "Application"
    assert entry["Name"] == "ArkivPiloten"
    assert entry["Terminal"] == "false"
    assert "--tray" in entry["Exec"]
    assert S.autostart_enabled()
    assert S.classify_autostart() == "correct"
    assert S.autostart_up_to_date()
    assert S.autostart_status()["source"] == "xdg"

    ok, msg = S.set_autostart(False)
    assert ok, msg
    assert not desktop.exists()
    assert not S.autostart_enabled()
    assert S.classify_autostart() == "missing"


def test_linux_escapes_percent_in_exec(app, monkeypatch):
    """En sökväg med % får inte bli en ogiltig Exec-fältkod."""
    S, tmp, _main = app
    monkeypatch.setattr(S.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp / "xdg"))
    main2 = tmp / "100% klar" / "pdfsorter.py"
    main2.parent.mkdir()
    main2.write_text("# test\n", encoding="utf-8")
    S.configure(config_dir=lambda: tmp / "app", now_iso=lambda: "x",
                main_script=main2, app_name="ArkivPiloten",
                app_version="1.1.0")

    ok, msg = S.set_autostart(True)
    assert ok, msg
    desktop = tmp / "xdg" / "autostart" / "arkivpiloten.desktop"
    exec_line = _parse_desktop(desktop)["Desktop Entry"]["Exec"]
    assert "100%% klar" in exec_line
    assert "100% klar" not in exec_line
    assert S.classify_autostart() == "correct"


def test_linux_propagates_pdfporter_home(app, monkeypatch):
    S, tmp, _main = app
    monkeypatch.setattr(S.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp / "xdg"))
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp / "data mapp"))
    ok, msg = S.set_autostart(True)
    assert ok, msg
    text = (tmp / "xdg" / "autostart" / "arkivpiloten.desktop").read_text(
        encoding="utf-8")
    assert "Environment=PDFSORTER_HOME=" in text
    assert str(tmp / "data mapp") in text
    assert S.classify_autostart() == "correct"


def test_linux_cleans_legacy_entry(app, monkeypatch):
    S, tmp, _main = app
    monkeypatch.setattr(S.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp / "xdg"))
    legacy = tmp / "xdg" / "autostart" / "pdfsorter.desktop"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("[Desktop Entry]\nType=Application\n", encoding="utf-8")
    assert S.classify_autostart() == "stale_path"
    ok, msg = S.set_autostart(True)
    assert ok, msg
    assert not legacy.exists()
    assert S.classify_autostart() == "correct"


def test_startup_never_deletes_a_working_entry(app, monkeypatch):
    """Startskedet ska ÄRVA en fungerande OS-post, inte radera den."""
    S, tmp, _main = app
    monkeypatch.setattr(S.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp / "xdg"))
    assert S.set_autostart(True)[0]

    vill, arvd = S.effective_autostart({"autostart": False})
    assert (vill, arvd) == (True, True)
    assert S.sync_autostart(vill)[0]
    assert S.autostart_enabled(), "en fungerande autostart raderades vid start"

    assert S.effective_autostart({"autostart": True}) == (True, False)
    S.set_autostart(False)
    assert S.effective_autostart({"autostart": False}) == (False, False)


# -- Windows ---------------------------------------------------------------
@pytest.fixture
def fake_winreg(monkeypatch):
    mod = types.ModuleType("winreg")
    mod.HKEY_CURRENT_USER = 1
    mod.KEY_ALL_ACCESS = 0xF003F
    mod.KEY_READ = 0x20019
    mod.KEY_SET_VALUE = 0x0002
    mod.REG_SZ = 1
    state = {"values": {}, "deny_open": False, "deny_set": False,
             "deny_delete": False}

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def OpenKey(root, path, reserved=0, access=0):
        if state["deny_open"]:
            raise PermissionError("denied by policy")
        return Key()

    def CreateKeyEx(*args, **kwargs):
        return Key()

    def QueryValueEx(key, name):
        if name not in state["values"]:
            raise FileNotFoundError(name)
        return state["values"][name], 1

    def SetValueEx(key, name, reserved, typ, value):
        if state["deny_set"]:
            raise PermissionError("denied")
        state["values"][name] = value

    def DeleteValue(key, name):
        if state["deny_delete"]:
            raise PermissionError("denied")
        if name not in state["values"]:
            raise FileNotFoundError(name)
        del state["values"][name]

    def EnumValue(key, index):
        items = list(state["values"].items())
        if index >= len(items):
            raise OSError()
        return items[index][0], items[index][1], 1

    mod.OpenKey = OpenKey
    mod.CreateKeyEx = CreateKeyEx
    mod.QueryValueEx = QueryValueEx
    mod.SetValueEx = SetValueEx
    mod.DeleteValue = DeleteValue
    mod.EnumValue = EnumValue
    monkeypatch.setitem(sys.modules, "winreg", mod)
    return mod, state


def _win(app, monkeypatch, fake_winreg):
    S, tmp, _main = app
    monkeypatch.setattr(S.sys, "platform", "win32")
    _, state = fake_winreg

    def fake_lnk(target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("lnk", encoding="utf-8")
        return True, str(target)

    monkeypatch.setattr(S, "_win_make_lnk", fake_lnk)
    return S, tmp, state


def test_windows_startup_fallback_is_recognised(app, monkeypatch, fake_winreg):
    """Registernekande (policy/AV) får inte se ut som 'saknas'."""
    S, tmp, state = _win(app, monkeypatch, fake_winreg)
    state["deny_open"] = True
    state["deny_set"] = True

    ok, msg = S.set_autostart(True)
    assert ok, msg
    lnk = tmp / "appdata" / "Microsoft" / "Windows" / "Start Menu" / \
        "Programs" / "Startup" / "ArkivPiloten.lnk"
    assert lnk.is_file()
    assert S.autostart_enabled()
    assert S.classify_autostart() == "startup_folder"
    assert S.autostart_up_to_date()
    assert S.autostart_status()["source"] == "startup_folder"
    assert "(posten verifierad)" in msg
    assert S.sync_autostart(True) == (True, "synk")


def test_windows_registry_removes_duplicate_startup_lnk(
        app, monkeypatch, fake_winreg):
    S, tmp, state = _win(app, monkeypatch, fake_winreg)
    lnk = S._win_startup_lnk()
    lnk.parent.mkdir(parents=True)
    lnk.write_text("old", encoding="utf-8")
    assert S.classify_autostart() == "startup_folder"

    ok, msg = S.set_autostart(True)
    assert ok, msg
    assert S.classify_autostart() == "correct"
    assert not lnk.exists()
    assert state["values"]["ArkivPiloten"].endswith("--tray")


def test_windows_autostart_skips_pyw_file_association(app, monkeypatch):
    S, tmp, main = app
    monkeypatch.setattr(S.sys, "platform", "win32")
    python = tmp / "Python" / "python.exe"
    python.parent.mkdir()
    python.write_text("", encoding="utf-8")
    pythonw = python.with_name("pythonw.exe")
    pythonw.write_text("", encoding="utf-8")
    monkeypatch.setattr(S.sys, "executable", str(python))

    argv, workdir = S._launch_argv()
    assert argv[0] == str(pythonw)
    assert argv[1] == str(main)
    assert argv[1].endswith("pdfsorter.py")
    assert not argv[1].endswith(".pyw")
    assert argv[2] == "--tray"
    assert workdir == str(main.parent)


def test_windows_failed_disable_is_not_reported_as_success(
        app, monkeypatch, fake_winreg):
    """Att säga 'av' medan posten är kvar är ett consent-problem."""
    S, tmp, state = _win(app, monkeypatch, fake_winreg)
    state["values"]["ArkivPiloten"] = (
        '"C:\\Python\\pythonw.exe" "C:\\App\\pdfsorter.py" --tray')
    state["deny_delete"] = True

    ok, msg = S.set_autostart(False)
    assert ok is False
    assert "finns kvar" in msg
    assert S.autostart_enabled()


def test_windows_stale_console_and_args_classes(
        app, monkeypatch, fake_winreg):
    S, _tmp, state = _win(app, monkeypatch, fake_winreg)
    state["values"]["ArkivPiloten"] = (
        f'"C:\\Python\\python.exe" "{S._main_script}" --tray')
    assert S.classify_autostart() == "stale_console"
    state["values"]["ArkivPiloten"] = (
        f'"C:\\Python\\pythonw.exe" "{S._main_script}"')
    assert S.classify_autostart() == "stale_args"
    state["values"]["ArkivPiloten"] = (
        '"C:\\Python\\pythonw.exe" "C:\\Old\\pdfsorter.py" --tray')
    assert S.classify_autostart() == "stale_path"


# -- macOS -----------------------------------------------------------------
def _fake_launchctl(monkeypatch):
    calls = []
    loaded = {"value": False}

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        if argv[0] != "launchctl":
            return types.SimpleNamespace(returncode=1, stdout="", stderr="")
        sub = argv[1] if len(argv) > 1 else ""
        if sub == "print":
            ok = loaded["value"]
            return types.SimpleNamespace(
                returncode=0 if ok else 1, stdout="ok" if ok else "",
                stderr="" if ok else "not found")
        if sub in ("bootstrap", "load"):
            loaded["value"] = True
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        if sub in ("bootout", "unload"):
            loaded["value"] = False
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        return types.SimpleNamespace(returncode=1, stdout="", stderr="?")

    monkeypatch.setattr(S.subprocess, "run", fake_run)
    return calls, loaded


def test_macos_plist_is_escaped_and_loadable(app, monkeypatch):
    S, tmp, _main = app
    monkeypatch.setattr(S.sys, "platform", "darwin")
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp / "data mapp"))
    main2 = tmp / "A & B <C>" / "pdfsorter.py"
    main2.parent.mkdir(parents=True)
    main2.write_text("# test\n", encoding="utf-8")
    S.configure(config_dir=lambda: tmp / "app", now_iso=lambda: "x",
                main_script=main2, app_name="ArkivPiloten",
                app_version="1.1.0")
    calls, loaded = _fake_launchctl(monkeypatch)

    ok, msg = S.set_autostart(True)
    assert ok, msg
    plist = tmp / "home" / "Library" / "LaunchAgents" / \
        "com.arkivpiloten.autostart.plist"
    data = plistlib.loads(plist.read_bytes())
    assert data["Label"] == "com.arkivpiloten.autostart"
    assert data["ProgramArguments"][1] == str(main2)
    assert data["WorkingDirectory"] == str(main2.parent)
    assert data["EnvironmentVariables"]["PDFSORTER_HOME"] == str(tmp / "data mapp")
    assert data["RunAtLoad"] is True
    assert any("bootstrap" in " ".join(c) for c in calls)
    assert S.classify_autostart() == "correct"
    assert S.autostart_status()["source"] == "launchagent"

    ok, msg = S.set_autostart(False)
    assert ok, msg
    assert not plist.exists()
    assert any("bootout" in " ".join(c) for c in calls)
    assert not loaded["value"]


def test_macos_invalid_old_plist_is_repaired(app, monkeypatch):
    S, tmp, _main = app
    monkeypatch.setattr(S.sys, "platform", "darwin")
    calls, _loaded = _fake_launchctl(monkeypatch)
    plist = tmp / "home" / "Library" / "LaunchAgents" / \
        "com.arkivpiloten.autostart.plist"
    plist.parent.mkdir(parents=True)
    plist.write_text("<plist><dict><key>Label</key><string>x</string>",
                      encoding="utf-8")
    assert S.classify_autostart() == "different"
    ok, msg = S.set_autostart(True)
    assert ok, msg
    assert S.classify_autostart() == "correct"
    assert plistlib.loads(plist.read_bytes())["Label"] == "com.arkivpiloten.autostart"


# -- dold start ------------------------------------------------------------
def test_tray_hidden_start_is_refused_on_gnome_xorg(app, monkeypatch):
    S, _tmp, _main = app
    monkeypatch.setattr(S.sys, "platform", "linux")
    monkeypatch.setattr(S, "tray_available", lambda: True)
    monkeypatch.setattr(S, "tray_backend_name", lambda: "pystray._xorg")
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    safe, reason = S.tray_hidden_start_safe()
    assert safe is False
    assert "GNOME" in reason
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert S.tray_hidden_start_safe()[0] is True
    monkeypatch.delenv("DISPLAY")
    assert S.tray_hidden_start_safe()[0] is False
