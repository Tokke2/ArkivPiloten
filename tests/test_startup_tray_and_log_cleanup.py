# -*- coding: utf-8 -*-
"""Regression tests for startup, tray recovery, full log archiving, and auto-purging."""
from __future__ import annotations

import datetime as dt
import gzip
import importlib.machinery
import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pdfsorter as P
import pdfsorter_diag as D
import pdfsorter_system as S


ROOT = Path(__file__).resolve().parents[1]


def _make_dummy_tk():
    class DummyVar:
        def __init__(self, master=None, value=None, name=None):
            self._val = "" if value is None else value

        def get(self):
            return self._val

        def set(self, v):
            self._val = v

        def trace_add(self, *a, **kw):
            return "trace1"

        def trace_remove(self, *a, **kw):
            pass

    class DummyBoolVar(DummyVar):
        def __init__(self, master=None, value=None, name=None):
            super().__init__(master, False if value is None else bool(value), name)

    class DummyIntVar(DummyVar):
        def __init__(self, master=None, value=None, name=None):
            super().__init__(master, 0 if value is None else int(value), name)

    class DummyWidget:
        _seq = 0

        def __init__(self, master=None, *a, **kw):
            DummyWidget._seq += 1
            self._name = f".w{DummyWidget._seq}"
            self.master = master
            self._cfg = dict(kw)
            self._children = []
            self._items = {}
            self._seq_item = 0
            if master is not None and hasattr(master, "_children"):
                master._children.append(self)

        def __str__(self):
            return self._name

        def __getattr__(self, name):
            return lambda *a, **kw: None

        def focus_get(self):
            return self

        def state(self, *a):
            return "normal" if not a else ()

        def after(self, ms, fn=None, *a):
            return "after1"

        def after_idle(self, fn=None, *a):
            return "idle1"

        def configure(self, **kw):
            self._cfg.update(kw)

        config = configure

        def cget(self, key):
            if key == "wraplength":
                return self._cfg.get("wraplength", 0)
            return self._cfg.get(key, "")

        def __getitem__(self, key):
            return self.cget(key)

        def __setitem__(self, key, val):
            self.configure(**{key: val})

        def winfo_children(self):
            return list(self._children)

        def winfo_exists(self):
            return True

        def winfo_ismapped(self):
            return True

        def winfo_width(self):
            return 800

        def winfo_height(self):
            return 600

        def winfo_reqwidth(self):
            return 400

        def winfo_reqheight(self):
            return 300

        def winfo_screenwidth(self):
            return 1920

        def winfo_screenheight(self):
            return 1080

        def winfo_fpixels(self, *a):
            return 96.0

        def winfo_id(self):
            return 12345

        def winfo_parent(self):
            return str(self.master) if self.master else ""

        def winfo_class(self):
            return "Frame"

        def winfo_pointerxy(self):
            return (100, 100)

        def winfo_containing(self, *a):
            return self

        def nametowidget(self, name):
            return self

        def tk_call(self, *a):
            return ""

        call = tk_call

        def select(self, *a):
            return self._name

        def tabs(self):
            return [self._name]

        def index(self, *a):
            return 0

        def insert(self, parent, index="end", iid=None, **kw):
            self._seq_item += 1
            key = iid or f"I{self._seq_item}"
            self._items[key] = dict(kw)
            return key

        def delete(self, *a):
            self._items.clear()

        def get_children(self, *a):
            return list(self._items.keys())

        def selection(self):
            return ()

        def item(self, key, option=None, **kw):
            it = self._items.get(key, {})
            return it.get(option, "") if option else it

        def set(self, *a):
            return ""

        def bbox(self, *a):
            return (0, 0, 100, 100)

        def create_window(self, *a, **kw):
            return 1

        def current(self, *a):
            return 0

        def curselection(self):
            return ()

        def get(self, *a):
            return ""

    class DummyTk(DummyWidget):
        def __init__(self, *a, **kw):
            super().__init__(None, *a, **kw)
            self.tk = self

    class DummyStyle:
        def __init__(self, *a, **kw):
            pass

        def theme_use(self, *a):
            pass

        def theme_names(self):
            return ("clam",)

        def configure(self, *a, **kw):
            pass

        def map(self, *a, **kw):
            pass

        def layout(self, *a, **kw):
            return []

    tk_mod = types.ModuleType("tkinter")
    for name in ("Toplevel", "Frame", "Label", "Button", "Entry", "Text",
                 "Canvas", "Listbox", "Menu", "Scrollbar"):
        setattr(tk_mod, name, DummyWidget)
    tk_mod.Tk = DummyTk
    tk_mod.StringVar = DummyVar
    tk_mod.BooleanVar = DummyBoolVar
    tk_mod.IntVar = DummyIntVar
    tk_mod.DoubleVar = DummyVar
    tk_mod.TclError = RuntimeError
    tk_mod.PhotoImage = lambda *a, **kw: DummyWidget()
    tk_mod.NONE, tk_mod.WORD, tk_mod.END = "none", "word", "end"

    ttk_mod = types.ModuleType("tkinter.ttk")
    for name in ("Frame", "Label", "Button", "Checkbutton", "Radiobutton",
                 "Entry", "Combobox", "Spinbox", "Notebook", "Treeview",
                 "Scrollbar", "Separator", "Progressbar", "Panedwindow",
                 "Labelframe"):
        setattr(ttk_mod, name, DummyWidget)
    ttk_mod.Style = DummyStyle

    fd_mod = types.ModuleType("tkinter.filedialog")
    mb_mod = types.ModuleType("tkinter.messagebox")
    sd_mod = types.ModuleType("tkinter.simpledialog")
    for fn in ("showinfo", "showwarning", "showerror", "askyesno"):
        setattr(mb_mod, fn, lambda *a, **kw: False)
    tk_mod.ttk = ttk_mod
    tk_mod.filedialog = fd_mod
    tk_mod.messagebox = mb_mod
    tk_mod.simpledialog = sd_mod
    return tk_mod, ttk_mod, fd_mod, mb_mod, sd_mod


def test_bind_responsive_wrap_accepts_both_call_conventions():
    container = SimpleNamespace(
        _bound=[],
        winfo_width=lambda: 700,
        bind=lambda ev, fn, add=None: container._bound.append(fn),
        after_idle=lambda fn: fn(),
    )
    label = SimpleNamespace(
        master=container,
        _cfg={"wraplength": 0},
        cget=lambda k: label._cfg[k],
        configure=lambda **kw: label._cfg.update(kw),
    )

    P._bind_responsive_wrap(container, label, reserve=200, minimum=180, maximum=900)
    assert label._cfg["wraplength"] == 500

    label._cfg["wraplength"] = 0
    P._bind_responsive_wrap(label, pad=100, min_w=120, max_w=900)
    assert label._cfg["wraplength"] == 600


def test_headless_app_init_and_dialogs_build_without_errors(tmp_path, monkeypatch):
    import pdfsorter_data as DD

    tk_mod, ttk_mod, fd_mod, mb_mod, sd_mod = _make_dummy_tk()
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(DD, "_CONFIG_DIR_CACHE", {}, raising=False)
    monkeypatch.setattr(DD, "_JSON_DIR_CACHE", None, raising=False)
    monkeypatch.setattr(DD, "_JSON_FLYTTAD", False, raising=False)
    monkeypatch.setitem(sys.modules, "tkinter", tk_mod)
    monkeypatch.setitem(sys.modules, "tkinter.ttk", ttk_mod)
    monkeypatch.setitem(sys.modules, "tkinter.filedialog", fd_mod)
    monkeypatch.setitem(sys.modules, "tkinter.messagebox", mb_mod)
    monkeypatch.setitem(sys.modules, "tkinter.simpledialog", sd_mod)
    monkeypatch.setitem(
        sys.modules, "PIL.ImageTk",
        types.SimpleNamespace(PhotoImage=lambda *a, **kw: object()),
    )
    monkeypatch.setattr(P, "sync_autostart", lambda _v: (True, "ok"))
    monkeypatch.setattr(P, "autostart_enabled", lambda: False)
    monkeypatch.setattr(P, "effective_autostart", lambda _s: (False, False))
    monkeypatch.setattr(P, "TrayIcon", None)

    app = P.App(start_hidden=True)
    try:
        app._on_tab_changed()
        app._set_theme(True)
        app._apply_dpi_change(144.0)
        app._collect_settings()
        app._open_error_code_dialog()
        app._visa_stod()
        app._open_archive_search()
        app._open_archive_audit()
        app._open_empty_archive_cleanup()
        app._tillaggserbjudande(force=True)
        app._show_shortcuts()
        app._pump()
    finally:
        app._quitting = True
        app._on_close()
        P._TAB_WHEEL_APP = None


def test_tray_health_watchdog_restarts_or_shows_window_when_tray_dies():
    shown = []
    app = object.__new__(P.App)
    app._quitting = False
    app.visible = False
    app.settings = {"tray_enabled": True}
    app._tray_restart_attempts = 0
    app._h = lambda *a, **kw: None
    app._sync_tray = lambda: None
    app.show_window = lambda reason="": shown.append(reason)

    stopped = []
    dead_tray = SimpleNamespace(
        is_alive=lambda: False,
        stop=lambda: stopped.append(True),
    )
    app.tray = dead_tray

    class FailingTray:
        def __init__(self, _app):
            pass

        def start(self):
            return False

    orig_tray = P.TrayIcon
    try:
        P.TrayIcon = FailingTray
        app._tray_restart_attempts = 2
        P.App._check_tray_health(app)
    finally:
        P.TrayIcon = orig_tray

    assert stopped == [True]
    assert app.tray is None
    assert shown == ["systemfältsikonen slutade svara"]


def test_tray_is_alive_tracks_thread_liveness():
    tray = S.TrayIcon(SimpleNamespace(watcher=None, queue=[]))
    assert tray.is_alive() is False

    tray.icon = SimpleNamespace(visible=True)
    tray._thread = SimpleNamespace(is_alive=lambda: True)
    assert tray.is_alive() is True

    tray._thread = SimpleNamespace(is_alive=lambda: False)
    assert tray.is_alive() is False


def test_crash_report_cleans_unstarted_tk_root_and_shows_dialog(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    monkeypatch.setattr(S, "session_dir", lambda: logs)
    monkeypatch.setattr(S, "_SESSION_FH", None)
    destroyed = []
    shown = []

    class HalfRoot:
        _arkivpiloten_running = False

        def winfo_exists(self):
            return True

        def destroy(self):
            destroyed.append("half")

    class DialogRoot:
        def withdraw(self):
            pass

        def iconbitmap(self, *a, **kw):
            pass

        def after(self, *a):
            pass

        def destroy(self):
            destroyed.append("dialog")

    tk_mod = types.ModuleType("tkinter")
    tk_mod._default_root = HalfRoot()
    tk_mod.Tk = lambda: DialogRoot()
    mb_mod = types.ModuleType("tkinter.messagebox")
    mb_mod.showerror = lambda title, text: shown.append((title, text))
    tk_mod.messagebox = mb_mod
    monkeypatch.setitem(sys.modules, "tkinter", tk_mod)
    monkeypatch.setitem(sys.modules, "tkinter.messagebox", mb_mod)
    monkeypatch.setattr(S, "brand_window", lambda *a: None)
    monkeypatch.setattr(S, "set_app_user_model_id", lambda: None)

    S.crash_report(RuntimeError("boom at startup"))

    assert destroyed == ["half", "dialog"]
    assert len(shown) == 1
    assert "boom at startup" in shown[0][1]
    assert "boom at startup" in (logs / "fel-samlat.log").read_text(encoding="utf-8")


def test_archive_old_logs_keeps_only_todays_logs_and_permanent_error_logs(tmp_path, monkeypatch):
    bas = tmp_path / "logs"
    today = dt.date.today()
    yesterday = today - dt.timedelta(days=1)
    old_day = today - dt.timedelta(days=35)

    def write_aged(path: Path, text: str, day: dt.date) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        ts = dt.datetime.combine(day, dt.time(10, 0)).timestamp()
        os.utime(path, (ts, ts))
        return path

    today_app = write_aged(
        bas / today.strftime("%Y-%m") / f"app_{today:%Y%m%d}_120000_live.log",
        "today", today)
    old_app = write_aged(
        bas / old_day.strftime("%Y-%m") / f"app_{old_day:%Y%m%d}_090000_old.log",
        "old session", old_day)
    old_err = write_aged(
        bas / old_day.strftime("%Y-%m") / "errors.log",
        "old error", old_day)
    old_install = write_aged(bas / "install.log", "old install", yesterday)
    old_crash = write_aged(bas / "krasch.log", "old crash", yesterday)
    old_empty = write_aged(bas / "startare.log", "", yesterday)
    old_legacy = write_aged(bas / "äldre" / "errors.log", "legacy", old_day)
    fel_samlat = write_aged(bas / "fel-samlat.log", "open error", old_day)
    felkoder = write_aged(bas / "felkoder.log", "open code", old_day)
    build_state = write_aged(bas / ".build_state.json", "{}", old_day)

    monkeypatch.setattr(S, "session_dir", lambda: bas)
    monkeypatch.setattr(S, "_SESSION_PATH", None)

    moved = S.archive_old_logs(1)

    assert moved == 5
    assert today_app.exists()
    assert fel_samlat.exists()
    assert felkoder.exists()
    assert build_state.exists()
    assert not old_app.exists()
    assert not old_err.exists()
    assert not old_install.exists()
    assert not old_crash.exists()
    assert not old_empty.exists()
    assert not old_legacy.exists()
    assert not (bas / "äldre").exists()
    if old_day.strftime("%Y-%m") != today.strftime("%Y-%m"):
        assert not (bas / old_day.strftime("%Y-%m")).exists()

    archived = list((bas / "arkiv").rglob("*.gz"))
    assert len(archived) == 5
    archived_names = {p.name for p in archived}
    assert any(n.startswith("install_") for n in archived_names)
    assert any(n.startswith("krasch_") for n in archived_names)
    with gzip.open(next(p for p in archived if p.name.startswith("install_")), "rt", encoding="utf-8") as fh:
        assert fh.read() == "old install"


def test_purge_samlat_cleans_resolved_errors_even_without_open_blocks(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir(parents=True)
    monkeypatch.setattr(D._State, "seen", {}, raising=False)
    monkeypatch.setattr(S, "session_dir", lambda: logs)
    monkeypatch.setattr(S, "_SESSION_FH", None)

    msg1 = "TypeError: widget boom"
    tb1 = 'File "pdfsorter.py", line 10184, in _build_sort_tab'
    code1 = D.fingerprint(msg1, tb1)

    S.session_log("krasch", f"{msg1}\n{tb1}", level="err")
    S.session_log("motor", "ValueError: still unfixed", level="err")

    # Simulate an older version having already dropped the [ÖPPEN] block while
    # leaving only the [ÅTGÄRDAD] receipt in felkoder.log and the error in fel-samlat.log.
    (logs / "felkoder.log").write_text(
        f"\n===== 2026-11-24T10:00:00 =====\nFELKOD:{code1} [ÅTGÄRDAD] fixed\n",
        encoding="utf-8",
    )

    res = S.purge_resolved_error_codes()
    assert res["samlat"] == 1
    rem = (logs / "fel-samlat.log").read_text(encoding="utf-8")
    assert msg1 not in rem
    assert "ValueError: still unfixed" in rem


def test_auto_resolve_on_build_change_clears_pre_update_errors(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir(parents=True)
    monkeypatch.setattr(D._State, "seen", {}, raising=False)
    monkeypatch.setattr(S, "session_dir", lambda: logs)
    monkeypatch.setattr(S, "_SESSION_FH", None)
    monkeypatch.setattr(S, "migrate_legacy_logs", lambda: None)
    monkeypatch.setattr(S, "archive_old_logs", lambda days=1: 0)

    (logs / ".build_state.json").write_text(
        json.dumps({"signature": "oldbuild0001"}), encoding="utf-8")
    S.session_log("ui", "TypeError: old layout bug", level="err")
    assert "old layout bug" in (logs / "fel-samlat.log").read_text(encoding="utf-8")

    monkeypatch.setattr(S, "_current_build_signature", lambda: "newbuild0002")
    try:
        assert S.start_session() is not None
    finally:
        S.close_session()

    assert "old layout bug" not in (logs / "fel-samlat.log").read_text(encoding="utf-8")
    kvar = (logs / "felkoder.log").read_text(encoding="utf-8")
    assert "[ÖPPEN]" not in kvar
    assert "[ÅTGÄRDAD] Automatiskt: nytt appbygge" in kvar
    assert json.loads((logs / ".build_state.json").read_text(encoding="utf-8"))["signature"] == "newbuild0002"


def test_pyw_matches_launcher_constant_and_lazy_stderr_avoids_empty_file(tmp_path):
    assert (ROOT / "pdfsorter.pyw").read_text(encoding="utf-8") == S.LAUNCHER_PYW

    loader = importlib.machinery.SourceFileLoader("pyw_test", str(ROOT / "pdfsorter.pyw"))
    spec = importlib.util.spec_from_loader("pyw_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)

    log_file = tmp_path / "logs" / "startare.log"
    lazy = mod._LazyLogFile(log_file)
    lazy.flush()
    lazy.close()
    assert not log_file.exists()

    lazy.write("startup warning\n")
    lazy.close()
    assert log_file.read_text(encoding="utf-8") == "startup warning\n"


def test_windows_batch_rechecks_packages_when_python_changes():
    batch = (ROOT / "ArkivPiloten - Installera senaste Python och starta.bat"
             ).read_text(encoding="utf-8")
    assert 'if /i not "!SAVED_PY!"=="%PYEXE%" del /f /q "%PKGSTATE%"' in batch
    assert '> "%PKGSTATE%" echo %PYEXE%' in batch


def test_archive_old_logs_skips_locked_and_vanished_files_without_warnings(tmp_path, monkeypatch):
    bas = tmp_path / "logs"
    old_day = dt.date.today() - dt.timedelta(days=5)
    locked = bas / "install.log"
    locked.parent.mkdir(parents=True, exist_ok=True)
    locked.write_text("locked content", encoding="utf-8")
    ts = dt.datetime.combine(old_day, dt.time(9, 0)).timestamp()
    os.utime(locked, (ts, ts))

    warnings = []
    monkeypatch.setattr(S, "session_dir", lambda: bas)
    monkeypatch.setattr(S, "_SESSION_PATH", None)
    monkeypatch.setattr(S, "session_log",
                        lambda cat, msg, level="info": warnings.append((cat, msg, level)))

    def raise_perm(_fil, _dest, _name):
        raise PermissionError("in use")

    monkeypatch.setattr(S, "_gzip_archive_file", raise_perm)
    assert S.archive_old_logs(1) == 0
    assert locked.exists()
    assert warnings == []

