from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pdfsorter as P
from pdfsorter_data import Rules


def _engine(tmp_path, asker=None):
    return P.SortEngine(
        Rules({"categories": []}, tmp_path / "rules.json"), {},
        locked_file_asker=asker)


def test_locked_file_cancelled_by_user_is_not_moved(monkeypatch, tmp_path):
    source = tmp_path / "locked.pdf"
    source.write_bytes(b"pdf")
    moves = []
    prompts = []
    monkeypatch.setattr(P, "is_file_locked", lambda _path: True)
    monkeypatch.setattr(P, "place_file", lambda *a, **k: moves.append(1))
    engine = _engine(tmp_path, lambda path: prompts.append(path) or False)

    ok, message, target = engine._place_file(
        source, tmp_path / "out", "Invoices", "move", "rename", False, "")

    assert not ok and target is None
    assert "lämnades kvar" in message
    assert prompts == [source]
    assert moves == []


def test_locked_file_retries_after_user_confirms_closed(monkeypatch, tmp_path):
    source = tmp_path / "locked.pdf"
    source.write_bytes(b"pdf")
    locked_states = iter((True, False))
    monkeypatch.setattr(P, "is_file_locked", lambda _path: next(locked_states))
    moved = []

    def place(*args, **kwargs):
        moved.append(1)
        return True, "moved", tmp_path / "out" / "locked.pdf"

    monkeypatch.setattr(P, "place_file", place)
    prompts = []
    engine = _engine(tmp_path, lambda path: prompts.append(path) or True)

    ok, message, target = engine._place_file(
        source, tmp_path / "out", "Invoices", "move", "rename", False, "")

    assert ok and message == "moved"
    assert target == tmp_path / "out" / "locked.pdf"
    assert prompts == [source]
    assert moved == [1]


def test_lock_race_prompts_and_retries_move(monkeypatch, tmp_path):
    source = tmp_path / "race.pdf"
    source.write_bytes(b"pdf")
    locked_states = iter((False, False))
    monkeypatch.setattr(P, "is_file_locked", lambda _path: next(locked_states))
    results = iter((
        (False, "Filen är låst av ett annat program", None),
        (True, "moved", tmp_path / "out" / "race.pdf"),
    ))
    calls = []

    def place(*args, **kwargs):
        calls.append(1)
        return next(results)

    monkeypatch.setattr(P, "place_file", place)
    prompts = []
    engine = _engine(tmp_path, lambda path: prompts.append(path) or True)

    ok, message, target = engine._place_file(
        source, tmp_path / "out", "Invoices", "move", "rename", False, "")

    assert ok and message == "moved"
    assert target == tmp_path / "out" / "race.pdf"
    assert prompts == [source]
    assert calls == [1, 1]


def test_locked_file_warning_asks_to_close_and_retry(monkeypatch, tmp_path):
    import pdfsorter as module

    app = object.__new__(P.App)
    app._closing = False
    app._main_thread = threading.current_thread()
    app._locked_dialog_lock = threading.Lock()
    app.root = SimpleNamespace(winfo_exists=lambda: True)
    shown = []
    app.messagebox = SimpleNamespace(
        askretrycancel=lambda title, message, parent: (
            shown.append((title, message, parent)) or True))
    monkeypatch.setattr(module, "session_log", lambda *a, **k: None)

    assert app._ask_locked_file(Path("invoice.pdf")) is True
    assert shown and "Stäng filen" in shown[0][1]
    assert "invoice.pdf" in shown[0][1]
