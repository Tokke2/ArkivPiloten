# -*- coding: utf-8 -*-
"""Minimering med öppen matchningsdialog + loggarkivering.

Buggen: minimerade man medan granskningsdialogen var öppen gick fönstret
inte att få fram igen, och loggen fylldes av

    _tkinter.TclError: cannot invoke "toplevel" command:
    application has been destroyed

Två orsaker, båda låsta här:
1. Huvudfönstret kunde withdrawas (systemfältet) medan en modal Toplevel
   med grab väntade - dialogen blev kvar utan förälder.
2. Kön fortsatte skapa dialoger efter att Tk rivits, eftersom
   winfo_exists() bara kontrollerades en gång, före loopen.

Dessutom: dagens logg får aldrig arkiveras, inte ens om tidsstämpeln
skulle vara skev (t.ex. efter en kopiering) eller sessionen stått stilla
länge.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pdfsorter as P
import pdfsorter_system as S


# -- fönsterbeteende -------------------------------------------------------
def test_minimize_with_open_dialog_stays_in_taskbar():
    """Även med minimize_to_tray påslaget: aldrig systemfältet."""
    settings = {"minimize_to_tray": True, "close_to_tray": True}
    assert P._minimize_action("iconic", settings, True, True) == "taskbar"
    # Utan dialog är beteendet oförändrat.
    assert P._minimize_action("iconic", settings, True, False) == "tray"


def test_modal_flag_does_not_affect_non_minimize():
    assert P._minimize_action("normal", {"minimize_to_tray": True},
                              True, True) == "none"
    assert P._minimize_action("withdrawn", {"minimize_to_tray": True},
                              True, True) == "none"


class _Win:
    def __init__(self, lever=True, kastar=False):
        self.lever = lever
        self.kastar = kastar
        self.deiconified = 0
        self.lifted = 0

    def winfo_exists(self):
        if self.kastar:
            raise RuntimeError("Tk är borta")
        return self.lever

    def deiconify(self):
        self.deiconified += 1

    def lift(self):
        self.lifted += 1

    def focus_force(self):
        pass


def _app():
    app = object.__new__(P.App)
    app._review_dialog = None
    app._closing = False
    app._h = lambda *a, **k: None
    return app


def test_review_is_open_reads_the_dialog_safely():
    app = _app()
    assert app._review_is_open() is False
    app._review_dialog = SimpleNamespace(win=_Win(lever=True))
    assert app._review_is_open() is True
    app._review_dialog = SimpleNamespace(win=_Win(lever=False))
    assert app._review_is_open() is False
    app._review_dialog = SimpleNamespace(win=_Win(kastar=True))
    assert app._review_is_open() is False


def test_hide_window_never_withdraws_with_an_open_dialog():
    app = _app()
    app._review_dialog = SimpleNamespace(win=_Win(lever=True))
    app.tray = object()
    app.settings = {"close_to_tray": True}
    grodor = {"withdraw": 0, "iconify": 0}
    app.root = SimpleNamespace(
        withdraw=lambda: grodor.__setitem__("withdraw",
                                            grodor["withdraw"] + 1),
        iconify=lambda: grodor.__setitem__("iconify",
                                          grodor["iconify"] + 1))
    app.hide_window("test")
    assert grodor == {"withdraw": 0, "iconify": 1}


def test_close_open_review_stops_the_queue_and_closes_the_dialog():
    app = _app()
    stängd = {"n": 0}

    class Dlg:
        def _skip(self):
            stängd["n"] += 1

    app._review_dialog = Dlg()
    app._close_open_review()
    assert stängd["n"] == 1
    assert app._closing is True
    assert app._review_dialog is None


# -- kön ska aldrig skapa dialoger i en död Tk -----------------------------
def test_process_queue_returns_when_closing(monkeypatch):
    app = _app()
    app.queue = [SimpleNamespace(path=Path("finns-inte.pdf"))]
    app.root = SimpleNamespace(winfo_exists=lambda: True)

    def no_dialog(*a, **k):
        raise AssertionError("ingen dialog får öppnas när appen stängs")

    monkeypatch.setattr(P, "ReviewDialog", no_dialog)
    app._closing = True
    app._process_queue()          # ska bara returnera


def test_process_queue_returns_when_root_is_destroyed(monkeypatch, tmp_path):
    fil = tmp_path / "dokument.pdf"
    fil.write_bytes(b"%PDF-1.4")
    app = _app()
    app.queue = [SimpleNamespace(path=fil)]
    app.root = SimpleNamespace(winfo_exists=lambda: False)
    app._queued_paths = set()

    def no_dialog(*a, **k):
        raise AssertionError("ingen dialog i en riven Tk")

    monkeypatch.setattr(P, "ReviewDialog", no_dialog)
    app._process_queue()


def test_process_queue_survives_tcl_error_from_dialog(monkeypatch, tmp_path,
                                                      capsys):
    fil = tmp_path / "dokument.pdf"
    fil.write_bytes(b"%PDF-1.4")
    app = _app()
    app.queue = [SimpleNamespace(path=fil,
                                 extraction=SimpleNamespace(combined=""),
                                 reason="test")]
    app.root = SimpleNamespace(winfo_exists=lambda: True)
    app._queued_paths = set()
    app.settings = {"keywords_per_file": 10}
    app.rules = SimpleNamespace(all_keyword_texts=lambda: set())
    app.theme = None

    class FakeTk:
        class TclError(Exception):
            pass

    app.tk = FakeTk
    monkeypatch.setattr(P, "suggest_keywords", lambda *a, **k: [])
    monkeypatch.setattr(P, "session_log", lambda *a, **k: None)

    def trasig_dialog(*a, **k):
        raise FakeTk.TclError("cannot invoke toplevel: destroyed")

    monkeypatch.setattr(P, "ReviewDialog", trasig_dialog)
    app._process_queue()                 # får inte kasta vidare
    assert app._review_dialog is None


# -- loggarkivering --------------------------------------------------------
def _loggfil(mapp: Path, namn: str, ålder_dagar: float) -> Path:
    mapp.mkdir(parents=True, exist_ok=True)
    fil = mapp / namn
    fil.write_text("rad\n", encoding="utf-8")
    t = time.time() - ålder_dagar * 86400
    os.utime(fil, (t, t))
    return fil


def test_today_is_never_archived_even_with_an_old_timestamp(monkeypatch,
                                                            tmp_path):
    import datetime as dt
    bas = tmp_path / "logs"
    månad = bas / "2026-10"
    idag = dt.datetime.now().strftime("%Y%m%d")
    färsk = _loggfil(månad, f"app_{idag}_120000_abc.log", 0)
    skew = _loggfil(månad, f"app_{idag}_090000_def.log", 9)  # gammal mtime
    monkeypatch.setattr(S, "session_dir", lambda: bas)
    monkeypatch.setattr(S, "_SESSION_PATH", None)
    assert S.archive_old_logs(3) == 0
    assert färsk.exists() and skew.exists()
    assert not (bas / "arkiv").exists()


def test_old_logs_are_archived_as_gzip(monkeypatch, tmp_path):
    bas = tmp_path / "logs"
    månad = bas / "2026-09"
    gammal = _loggfil(månad, "app_20260901_080000_abc.log", 30)
    monkeypatch.setattr(S, "session_dir", lambda: bas)
    monkeypatch.setattr(S, "_SESSION_PATH", None)
    assert S.archive_old_logs(3) == 1
    assert not gammal.exists()
    arkiv = list((bas / "arkiv").rglob("*.log.gz"))
    assert len(arkiv) == 1


def test_current_session_file_is_never_archived(monkeypatch, tmp_path):
    bas = tmp_path / "logs"
    månad = bas / "2026-09"
    gammal = _loggfil(månad, "app_20260901_070000_abc.log", 40)
    monkeypatch.setattr(S, "session_dir", lambda: bas)
    monkeypatch.setattr(S, "_SESSION_PATH", gammal)
    assert S.archive_old_logs(3) == 0
    assert gammal.exists()
