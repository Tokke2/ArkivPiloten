"""Regression tests for safe, partial cancellation of a sorting batch."""
from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pdfsorter as P


def test_apply_does_not_move_a_file_if_cancelled_before_commit(tmp_path):
    source = tmp_path / "inbox" / "report.pdf"
    source.parent.mkdir()
    source.write_bytes(b"keep me")
    engine = P.SortEngine(rules=None, settings={})
    event = threading.Event()
    event.set()
    decision = SimpleNamespace(path=source)

    ok, message = engine.apply(decision, "Reports", [], cancel_event=event)

    assert not ok
    assert "Avbruten" in message
    assert source.read_bytes() == b"keep me"
    assert not engine.stats


def test_send_to_unmatched_does_not_move_a_file_if_cancelled(tmp_path):
    source = tmp_path / "inbox" / "report.pdf"
    source.parent.mkdir()
    source.write_bytes(b"keep me")
    engine = P.SortEngine(rules=None, settings={})
    event = threading.Event()
    event.set()
    decision = SimpleNamespace(path=source)

    ok, message = engine.send_to_unmatched(decision, cancel_event=event)

    assert not ok
    assert "Avbruten" in message
    assert source.read_bytes() == b"keep me"
    assert not engine.stats


def test_cancel_button_sets_event_and_reports_safe_stop():
    event = threading.Event()
    changes = []
    logs = []
    app = SimpleNamespace(
        _busy=True,
        _sort_cancel_event=event,
        btn_cancel_sort=SimpleNamespace(
            configure=lambda **kw: changes.append(("button", kw))),
        lbl_progress=SimpleNamespace(
            configure=lambda **kw: changes.append(("progress", kw))),
        _log=lambda *args: logs.append(args),
    )

    P.App._cancel_sorting(app)

    assert event.is_set()
    assert changes[0] == ("button", {"state": "disabled", "text": "Stoppar…"})
    assert changes[1][0] == "progress"
    assert any("övriga filer lämnas kvar" in entry[0] for entry in logs)


def test_startup_schedules_task_maintenance_but_not_package_install():
    source = (Path(P.__file__).read_text(encoding="utf-8"))
    assert "_autoinstallera_tillagg" not in source
    assert 'self.root.after(900, self._ensure_weekly_python_update_task)' in source
    start = source.index("    def _ensure_weekly_python_update_task")
    end = source.index("    # -- manuell tilläggskontroll", start)
    task_method = source[start:end]
    assert "subprocess.run(args, **kwargs)" in task_method
    assert "pip install" not in task_method.lower()
