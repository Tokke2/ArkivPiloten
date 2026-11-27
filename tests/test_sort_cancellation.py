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


def test_compact_action_layout_keeps_progress_off_the_error_counters():
    source = Path(P.__file__).read_text(encoding="utf-8")
    start = source.index("        def layout_actions(_event=None):")
    end = source.index("        actcard.bind(\"<Configure>\", layout_actions", start)
    layout = source[start:end]

    assert 'stats.grid_configure(row=2, column=0, columnspan=3' in layout
    assert 'self.progress.grid_configure(row=3, column=0, columnspan=3' in layout
    assert 'self.lbl_progress.grid_configure(row=4, column=0' in layout
    assert 'stats.grid_configure(row=1, column=0, columnspan=4' in layout
    assert 'self.progress.grid_configure(row=2, column=0, columnspan=2' in layout
    assert 'self.lbl_progress.grid_configure(row=2, column=2' in layout


def test_startup_schedules_task_maintenance_but_not_package_install():
    source = (Path(P.__file__).read_text(encoding="utf-8"))
    assert "_autoinstallera_tillagg" not in source
    assert 'self.root.after(900, self._ensure_weekly_python_update_task)' in source
    start = source.index("    def _ensure_weekly_python_update_task")
    end = source.index("    # -- manuell tilläggskontroll", start)
    task_method = source[start:end]
    assert "subprocess.run(args, **kwargs)" in task_method
    assert "pip install" not in task_method.lower()


def test_settings_cards_have_no_overlapping_grid_cells():
    import ast
    from collections import defaultdict

    tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
    build_tab = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_build_sort_tab"
    )
    var_parent = {}
    for sub in ast.walk(build_tab):
        if (isinstance(sub, ast.Assign) and len(sub.targets) == 1
                and isinstance(sub.targets[0], ast.Name)
                and isinstance(sub.value, ast.Call) and sub.value.args):
            var_parent[sub.targets[0].id] = ast.unparse(sub.value.args[0])
    seen = defaultdict(list)
    for sub in ast.walk(build_tab):
        if (isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "grid"):
            kw = {k.arg: k.value for k in sub.keywords if k.arg}
            if ("row" in kw and isinstance(kw["row"], ast.Constant)
                    and isinstance(kw["row"].value, int)):
                col_node = kw.get("column")
                if col_node is not None and not (
                        isinstance(col_node, ast.Constant)
                        and isinstance(col_node.value, int)):
                    continue
                row = kw["row"].value
                col = col_node.value if col_node is not None else 0
                cspan = (kw["columnspan"].value if "columnspan" in kw
                         and isinstance(kw["columnspan"], ast.Constant)
                         and isinstance(kw["columnspan"].value, int) else 1)
                rspan = (kw["rowspan"].value if "rowspan" in kw
                         and isinstance(kw["rowspan"], ast.Constant)
                         and isinstance(kw["rowspan"].value, int) else 1)
                val = sub.func.value
                if isinstance(val, ast.Call) and val.args:
                    parent = ast.unparse(val.args[0])
                elif isinstance(val, ast.Name) and val.id in var_parent:
                    parent = var_parent[val.id]
                else:
                    continue
                for dr in range(rspan):
                    for c in range(col, col + cspan):
                        seen[(parent, row + dr, c)].append(sub.lineno)
    overlaps = {cell: lines for cell, lines in seen.items() if len(lines) > 1}
    assert overlaps == {}
