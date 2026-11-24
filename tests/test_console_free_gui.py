"""Windows-GUI-starten ska inte lämna ett python.exe-konsolfönster."""
from __future__ import annotations

import pdfsorter as P


def _prepare_windows(monkeypatch, tmp_path, *, with_pythonw=True):
    exe = tmp_path / "python.exe"
    exe.touch()
    pythonw = tmp_path / "pythonw.exe"
    if with_pythonw:
        pythonw.touch()
    monkeypatch.setattr(P.sys, "platform", "win32")
    monkeypatch.setattr(P.sys, "executable", str(exe))
    monkeypatch.delenv(P._GUI_CONSOLE_HANDOFF_ENV, raising=False)
    return exe, pythonw


def test_regular_gui_start_hands_off_to_pythonw(monkeypatch, tmp_path):
    _exe, pythonw = _prepare_windows(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(P.subprocess, "Popen",
                        lambda command, **kwargs: calls.append((command, kwargs)))

    assert P._start_gui_without_console([])
    command, kwargs = calls[0]
    assert command[0] == str(pythonw)
    assert command[1].endswith("pdfsorter.py")
    assert P._GUI_CONSOLE_HANDOFF_ENV in kwargs["env"]
    assert "creationflags" not in kwargs


def test_tray_gui_start_keeps_arguments_and_cli_does_not_handoff(
        monkeypatch, tmp_path):
    _prepare_windows(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(P.subprocess, "Popen",
                        lambda command, **kwargs: calls.append(command))

    assert P._start_gui_without_console(["--tray", "--resume-watch"])
    assert calls[0][-2:] == ["--tray", "--resume-watch"]
    assert not P._start_gui_without_console(["--check"])
    assert len(calls) == 1


def test_python_without_pythonw_uses_create_no_window(monkeypatch, tmp_path):
    exe, _pythonw = _prepare_windows(monkeypatch, tmp_path,
                                     with_pythonw=False)
    monkeypatch.setattr(P.subprocess, "CREATE_NO_WINDOW", 0x08000000,
                        raising=False)
    calls = []
    monkeypatch.setattr(P.subprocess, "Popen",
                        lambda command, **kwargs: calls.append((command, kwargs)))

    assert P._start_gui_without_console([])
    command, kwargs = calls[0]
    assert command[0] == str(exe)
    assert kwargs["creationflags"] == P.subprocess.CREATE_NO_WINDOW


def test_pythonw_and_handoff_marker_prevent_restart_loop(monkeypatch, tmp_path):
    _exe, pythonw = _prepare_windows(monkeypatch, tmp_path)
    monkeypatch.setattr(P.sys, "executable", str(pythonw))
    calls = []
    monkeypatch.setattr(P.subprocess, "Popen",
                        lambda command, **kwargs: calls.append(command))
    assert not P._start_gui_without_console([])

    monkeypatch.setattr(P.sys, "executable", str(tmp_path / "python.exe"))
    monkeypatch.setenv(P._GUI_CONSOLE_HANDOFF_ENV, "1")
    assert not P._start_gui_without_console([])
    assert calls == []


def test_failed_handoff_falls_back_to_current_gui_process(monkeypatch, tmp_path):
    _prepare_windows(monkeypatch, tmp_path)

    def fail(*_args, **_kwargs):
        raise OSError("spawn blocked")

    monkeypatch.setattr(P.subprocess, "Popen", fail)
    assert not P._start_gui_without_console([])


def test_main_performs_handoff_before_gui_initialization(monkeypatch):
    seen = []
    monkeypatch.setattr(P, "_start_gui_without_console",
                        lambda args: seen.append(args) or True)
    monkeypatch.setattr(P, "set_app_user_model_id",
                        lambda: (_ for _ in ()).throw(
                            AssertionError("handoff ska ske först")))

    assert P.main([]) == 0
    assert seen == [[]]
