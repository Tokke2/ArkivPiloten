# -*- coding: utf-8 -*-
"""Versionsvakten: tyst sökning två gånger per dygn och tyst omstart.

Önskemålet (2026-10-26): "autosök efter ny version (tyst) 2 ggr per dygn"
och "tyst omstart vid uppdatering av version".

Det som gör att två gånger per dygn verkligen blir två gånger per dygn är
att tiden sparas i inställningarna: en app som startas ofta får inte fråga
GitHub varje gång. Därför testas schemat, sparningen och omstarten utan
Tk - allt utom själva fönstret går att granska här.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pdfsorter as P
import pdfsorter_data as D

NU = datetime(2026, 10, 26, 12, 0, 0)


def _tid(timmar: float = 0, minuter: float = 0) -> str:
    return (NU - timedelta(hours=timmar, minutes=minuter)).isoformat(
        timespec="seconds")


# -- inställningarna ------------------------------------------------------
def test_defaults_are_two_checks_per_day_and_silent_restart():
    assert D.DEFAULT_SETTINGS["update_checks_per_day"] == 2
    assert D.DEFAULT_SETTINGS["silent_restart"] is True
    for nyckel in ("last_update_check", "last_update_check_ok",
                   "last_update_seen"):
        assert nyckel in D.DEFAULT_SETTINGS


def test_checks_per_day_is_clamped():
    assert P.uppdateringar_per_dygn({}) == 2
    assert P.uppdateringar_per_dygn({"update_checks_per_day": 4}) == 4
    assert P.uppdateringar_per_dygn({"update_checks_per_day": 0}) == 1
    assert P.uppdateringar_per_dygn({"update_checks_per_day": 10000}) == 96
    assert P.uppdateringar_per_dygn({"update_checks_per_day": "3"}) == 3
    # Skräp i JSON-filen får inte stoppa vakten.
    assert P.uppdateringar_per_dygn({"update_checks_per_day": "nej"}) == 2


def test_two_checks_per_day_means_twelve_hours():
    assert P.uppdaterings_intervall(2) == 43200.0
    assert P.uppdaterings_intervall(4) == 21600.0
    assert P.uppdaterings_intervall(0) == 86400.0     # aldrig snabbare än 1/dygn


# -- när är det dags? -----------------------------------------------------
def test_never_checked_means_due_now(monkeypatch):
    assert P.uppdaterings_dags("", nu=NU) is True
    assert P.uppdaterings_dags("inte-en-tid", nu=NU) is True


def test_eleven_hours_is_too_early_and_thirteen_is_due():
    assert P.uppdaterings_dags(_tid(11), nu=NU) is False
    assert P.uppdaterings_dags(_tid(13), nu=NU) is True
    assert P.uppdaterings_dags(_tid(0, 1), per_dygn=1, nu=NU) is False


def test_failed_search_is_retried_within_half_an_hour():
    assert P.uppdaterings_dags(_tid(0, 20), forra_lyckades=False,
                               nu=NU) is False
    assert P.uppdaterings_dags(_tid(0, 40), forra_lyckades=False,
                               nu=NU) is True


def test_next_check_text_and_last_check_text():
    assert P.uppdaterings_nasta_text("", nu=NU) == "nu"
    assert P.uppdaterings_nasta_text(_tid(1), nu=NU) == "om 11 t"
    assert "min" in P.uppdaterings_nasta_text(_tid(11, 30), nu=NU)
    assert P.tid_kort("", nu=NU) == "aldrig"
    assert P.tid_kort(_tid(0, 5), nu=NU).startswith("i dag ")
    assert P.tid_kort(_tid(30), nu=NU).startswith("i går ")


# -- vad ska ett svar leda till? -----------------------------------------
def _info(**kw):
    bas = {"ok": True, "available": True, "remote": "9.9.9",
           "sha256_url": "https://example.test/SHA256SUMS.txt"}
    bas.update(kw)
    return bas


def test_plan_handles_every_kind_of_answer():
    tysta = {"auto_update": True, "silent_restart": True}
    assert P.uppdateringsplan({"ok": False}, False, tysta)["steg"] == "fel"
    assert P.uppdateringsplan({"ok": True, "available": False},
                              False, tysta)["steg"] == "aktuell"
    assert P.uppdateringsplan(_info(sha256_url=""),
                              False, tysta)["steg"] == "osaker"
    assert P.uppdateringsplan(_info(), False, tysta)["steg"] == "installera"


def test_manual_search_never_installs_silently():
    plan = P.uppdateringsplan(_info(), True, {"auto_update": True})
    assert plan["steg"] == "fraga"
    assert plan["tyst"] is False


def test_autoupdate_off_means_a_notice_not_a_dialog():
    plan = P.uppdateringsplan(_info(), False, {"auto_update": False})
    assert plan["steg"] == "erbjudande" and plan["tyst"] is True
    # ...men den som själv trycker på Sök får frågan.
    assert P.uppdateringsplan(_info(), True,
                              {"auto_update": False})["steg"] == "fraga"


def test_restart_is_silent_unless_turned_off():
    assert P.uppdateringsplan(
        _info(), False, {"auto_update": True, "silent_restart": True}
    )["omstart"] == "tyst"
    assert P.uppdateringsplan(
        _info(), False, {"auto_update": True, "silent_restart": False}
    )["omstart"] == "fraga"
    # Inget installeras -> ingen omstart alls.
    assert P.uppdateringsplan(
        {"ok": False}, False, {"silent_restart": True})["omstart"] == "ingen"


# -- omstarts-kommandot ---------------------------------------------------
def test_restart_command_starts_the_app_again(tmp_path):
    (tmp_path / "pdfsorter.py").write_text("", encoding="utf-8")
    cmd = P.omstart_kommando(tmp_path, "/usr/bin/python3", "linux")
    assert cmd == ["/usr/bin/python3", str(tmp_path / "pdfsorter.py")]


def test_restart_command_can_stay_hidden_and_resume_watching(tmp_path):
    cmd = P.omstart_kommando(tmp_path, "/usr/bin/python3", "linux",
                             dold=True, bevaka_igen=True)
    assert cmd[2:] == ["--tray", "--resume-watch"]


def test_windows_restart_prefers_pythonw_and_pyw(tmp_path):
    (tmp_path / "pdfsorter.py").write_text("", encoding="utf-8")
    (tmp_path / "pdfsorter.pyw").write_text("", encoding="utf-8")
    cmd = P.omstart_kommando(tmp_path, "C:/Python/python.exe", "win32")
    assert cmd[1].endswith("pdfsorter.pyw")
    # pythonw.exe finns inte i testet -> python.exe används, men scriptet är rätt
    assert cmd[0].endswith("python.exe")


# -- appens egna beslut (utan Tk) ----------------------------------------
class _App:
    """Undantag: bara metoderna som inte rör Tk, med appens fält."""

    _kan_starta_om = P.App._kan_starta_om
    _uppdatering_status_text = P.App._uppdatering_status_text

    def __init__(self, **kw):
        self._quitting = False
        self._busy = False
        self.queue = []
        self._review_dialog = None
        self.settings = {}
        self.__dict__.update(kw)

    def _review_is_open(self):
        return self._review_dialog is not None


def test_restart_is_refused_while_work_is_in_flight():
    assert _App()._kan_starta_om() == (True, "")
    assert _App(_busy=True)._kan_starta_om()[0] is False
    assert _App(_review_dialog=object())._kan_starta_om()[0] is False
    assert _App(queue=[1, 2])._kan_starta_om()[0] is False
    assert _App(_quitting=True)._kan_starta_om()[0] is False
    assert "sortering" in _App(_busy=True)._kan_starta_om()[1]


def test_status_line_tells_when_the_next_search_happens():
    app = _App(settings={"check_updates": True,
                         "update_checks_per_day": 2,
                         "last_update_check": ""})
    text = app._uppdatering_status_text()
    assert "2 ggr/dygn" in text and "aldrig" in text and "nästa nu" in text
    app.settings["check_updates"] = False
    assert "avstängd" in app._uppdatering_status_text()
    app.settings.update({"check_updates": True,
                         "last_update_check_ok": False,
                         "last_update_check": "inte-en-tid"})
    assert "misslyckades" in app._uppdatering_status_text()


# -- sparningen överlever en omstart -------------------------------------
def test_the_check_time_survives_a_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp_path / "data"))
    D._CONFIG_DIR_CACHE.clear()
    monkeypatch.setattr(D, "_JSON_DIR_CACHE", None, raising=False)
    monkeypatch.setattr(D, "_JSON_FLYTTAD", False, raising=False)

    app = _App(settings=dict(D.DEFAULT_SETTINGS))
    app._h = lambda *a, **k: None
    app._refresh_update_status = lambda: None
    P.App._notera_uppdateringsforsok(app, {"ok": True, "remote": "9.9.9"})

    sparade = D.load_settings()
    assert sparade["last_update_check"]           # tiden finns kvar
    assert sparade["last_update_check_ok"] is True
    assert sparade["last_update_seen"] == "9.9.9"
    # ...och en omstart direkt efteråt frågar inte GitHub igen.
    assert P.uppdaterings_dags(sparade["last_update_check"],
                               nu=datetime.now()) is False


# -- att appen verkligen kopplar in vakten (AST, utan Tk) -----------------
import ast  # noqa: E402

_ROT = __import__("pathlib").Path(__file__).resolve().parents[1]


def _metod(namn: str) -> ast.FunctionDef:
    träd = ast.parse((_ROT / "pdfsorter.py").read_text(encoding="utf-8"))
    for nod in ast.walk(träd):
        if isinstance(nod, ast.ClassDef) and nod.name == "App":
            for barn in nod.body:
                if isinstance(barn, ast.FunctionDef) and barn.name == namn:
                    return barn
    raise AssertionError(f"App.{namn} finns inte")


def _kall(träd: ast.AST) -> set:
    """Namn på allt som anropas i en funktion (utan docstring)."""
    kropp = getattr(träd, "body", [])
    if (kropp and isinstance(kropp[0], ast.Expr)
            and isinstance(kropp[0].value, ast.Constant)):
        träd = ast.Module(body=kropp[1:] or [ast.Pass()], type_ignores=[])
    namn = set()
    for nod in ast.walk(träd):
        if isinstance(nod, ast.Call):
            f = nod.func
            if isinstance(f, ast.Attribute):
                namn.add(f.attr)
            elif isinstance(f, ast.Name):
                namn.add(f.id)
    return namn


def test_the_app_starts_the_watchdog_instead_of_checking_at_every_start():
    __init__ = _metod("__init__")
    kall = _kall(__init__)
    assert "_starta_uppdateringsvakt" in kall
    assert "_check_updates_gui" not in kall, \
        "starten ska gå via vakten - annars blir det en sökning per start"


def test_the_watchdog_checks_the_clock_before_searching():
    tick = _kall(_metod("_uppdateringsvakt_tick"))
    assert "_uppdatering_dags" in tick       # frågar klockan först
    assert "_check_updates_gui" in tick
    assert "after" in tick                   # lägger nästa väckning


def test_the_restart_releases_the_instance_lock_before_starting():
    """Utan detta nekar den nya processen och ber den döende visa fönstret."""
    f = _metod("_restart_app")
    kalla = ast.unparse(f)
    assert "instanslås" in kalla and "release" in kalla
    assert kalla.index("release") < kalla.index("Popen")
    assert "_spara_fore_omstart" in kalla
    assert "--tray" not in kalla             # flaggorna byggs i omstart_kommando


def test_settings_tab_has_its_own_update_card():
    f = _metod("_build_sort_tab")
    kalla = ast.unparse(f)
    assert 'T.card(g, \'Uppdateringar\')' in kalla or \
        'T.card(g, "Uppdateringar")' in kalla
    assert "var_tystomstart" in kalla and "Sök nu" in kalla


def test_saving_the_tab_keeps_the_silent_restart_setting():
    kalla = ast.unparse(_metod("_collect_settings"))
    assert "silent_restart" in kalla and "var_tystomstart" in kalla


def test_cli_can_resume_watching_after_a_restart():
    rot = (_ROT / "pdfsorter.py").read_text(encoding="utf-8")
    assert '"--resume-watch"' in rot
    assert "resume_watch=args.resume_watch" in rot
    assert "instanslås=lås" in rot


def test_help_tells_about_the_silent_updates():
    import pdfsorter_system as S
    text = S.help_as_text()
    assert "UPPDATERINGAR SKÖTER SIG SJÄLV" in text
    assert "två gånger per dygn" in text


# -- hela flödet med attrapper: tyst sökning -> tyst omstart --------------
class _InlineThread:
    """Kör tråden direkt: uppdateringsflödet blir genomsynligt i testet."""

    def __init__(self, target=None, daemon=False, name="", **_kw):
        self._target = target

    def start(self):
        self._target()


class _FakeMessagebox:
    def __init__(self, svar=True):
        self.svar = svar
        self.fragor, self.varningar, self.klart = [], [], []

    def askyesno(self, titel, text, **kwargs):
        self.fragor.append(text)
        return self.svar

    def showwarning(self, titel, text, **kwargs):
        self.varningar.append(text)

    def showinfo(self, titel, text, **kwargs):
        self.klart.append(text)


class _FakeRoot:
    def __init__(self):
        self.efter = []          # (ms, kördes direkt)
        self.riven = False

    def after(self, ms, fn=None, *a):
        self.efter.append(ms)
        if callable(fn):
            fn(*a)
        return f"id{len(self.efter)}"

    def destroy(self):
        self.riven = True


class _Sken:
    """Appen utan Tk: riktiga metoder, attrapper för fönster och dialoger."""

    _update_prompt = P.App._update_prompt
    _notera_uppdateringsforsok = P.App._notera_uppdateringsforsok
    _refresh_update_status = P.App._refresh_update_status
    _uppdatering_status_text = P.App._uppdatering_status_text
    _uppdateringsvakt_tick = P.App._uppdateringsvakt_tick
    _check_updates_gui = P.App._check_updates_gui
    _uppdatering_dags = P.App._uppdatering_dags
    _uppdatering_nasta = P.App._uppdatering_nasta
    _starta_uppdateringsvakt = P.App._starta_uppdateringsvakt
    _kan_starta_om = P.App._kan_starta_om
    _planera_omstart = P.App._planera_omstart
    _omstart_nar_ledig = P.App._omstart_nar_ledig
    _restart_app = P.App._restart_app

    def __init__(self, **kw):
        self.settings = dict(D.DEFAULT_SETTINGS)
        self.aviseringar = []
        self.settings.update({"update_checks_per_day": 2,
                              "last_update_check": "",
                              "last_update_check_ok": True})
        self.messagebox = _FakeMessagebox()
        self.root = _FakeRoot()
        self.handelser = []       # (nivå, text) ur sessionsloggen
        self.gui = []
        self.omstarter = []
        self._busy = False
        self.queue = []
        self._review_dialog = None
        self._quitting = False
        self._omstart_vantar = False
        self._uppdateringsvakt = False
        self.instanslås = None
        self.watcher = None
        self.visible = True
        self.lbl_uppdatering = None
        self.__dict__.update(kw)

    # -- attrapper --------------------------------------------------------
    def _h(self, kategori, msg, level="info"):
        self.handelser.append((level, msg))

    def _log(self, msg, level="info"):
        self.gui.append((level, msg))

    def _notify(self, msg):
        self.aviseringar.append(msg)

    def _review_is_open(self):
        return self._review_dialog is not None

    def _spara_fore_omstart(self):
        self.sparat = True

    def _close_open_review(self):
        self.stangd_dialog = True

    tray = None


def _info_med_ny_version(**kw):
    bas = {"ok": True, "available": True, "remote": "9.9.9",
           "sha256_url": "https://example.test/SHA256SUMS.txt",
           "release_url": "https://example.test/release"}
    bas.update(kw)
    return bas


def _tyst_uppdatering(monkeypatch, app, resultat=(True, "Installerat")):
    monkeypatch.setattr(P.threading, "Thread", _InlineThread)
    monkeypatch.setattr(P, "perform_update", lambda *a, **k: resultat)
    monkeypatch.setattr(P, "update_python_packages", lambda *a, **k: (True, ""))
    monkeypatch.setattr(P, "session_log", lambda *a, **k: None)
    app._planera_omstart = lambda tyst=True: app.omstarter.append(tyst)
    return app


def test_silent_update_installs_and_restarts_without_any_dialog(
        tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp_path / "data"))
    app = _tyst_uppdatering(monkeypatch, _Sken())
    app._update_prompt(_info_med_ny_version(), manual=False)
    assert app.messagebox.fragor == []          # ingen fråga
    assert app.messagebox.varningar == []
    assert app.omstarter == [True]              # tyst omstart
    assert app.settings["last_update_check"]    # tiden sparad
    assert any("Tyst uppdatering" in t for _n, t in app.handelser)


def test_failed_silent_update_is_logged_not_shown(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp_path / "data"))
    app = _tyst_uppdatering(monkeypatch, _Sken(),
                            resultat=(False, "nätet svek"))
    app._update_prompt(_info_med_ny_version(), manual=False)
    assert app.messagebox.varningar == []       # ingen ruta mitt i natten
    assert app.omstarter == []
    assert any("nätet svek" in t for _n, t in app.gui + app.handelser)


def test_manual_install_asks_and_then_restarts(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp_path / "data"))
    app = _tyst_uppdatering(monkeypatch, _Sken())
    app.settings["silent_restart"] = False
    app._update_prompt(_info_med_ny_version(), manual=True)
    assert len(app.messagebox.fragor) == 2      # 1) installera? 2) starta om?
    assert "Starta om" in app.messagebox.fragor[1]
    assert app.omstarter == [False]


def test_silent_check_without_new_version_only_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp_path / "data"))
    app = _Sken()
    app._update_prompt({"ok": True, "available": False, "remote": "1.4.13"},
                       manual=False)
    assert app.messagebox.klart == [] and app.messagebox.fragor == []
    assert any("Ingen nyare version" in t for _n, t in app.handelser)


def test_watchdog_skips_a_check_that_is_not_due(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp_path / "data"))
    app = _Sken()
    app.settings["last_update_check"] = _tid(2)     # sökte för två timmar sen
    # Klockan styrs inte av den historiska testkonstanten NU i den här
    # integrationen; fixera beslutet så testet inte blir tidsberoende.
    monkeypatch.setattr(app, "_uppdatering_dags", lambda: False)

    def _nej(*a, **k):
        raise AssertionError("GitHub ska inte kontaktas före tolv timmar")
    monkeypatch.setattr(P, "check_for_update", _nej)
    app._check_updates_gui(manual=False)
    assert any("hoppad" in t for _n, t in app.handelser)


def test_watchdog_searches_and_records_the_time(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp_path / "data"))
    app = _Sken()
    anrop = []

    def _sok(*a, **k):
        anrop.append(1)
        return {"ok": True, "available": False, "remote": "1.4.13"}
    monkeypatch.setattr(P, "check_for_update", _sok)
    monkeypatch.setattr(P.threading, "Thread", _InlineThread)
    monkeypatch.setattr(P, "session_log", lambda *a, **k: None)

    app._uppdateringsvakt_tick()
    assert anrop == [1]
    assert app.settings["last_update_check"]
    assert app.root.efter and app.root.efter[-1] == P.UPPDATERING_VAKT_SEKUNDER * 1000
    # Nästa väckning gör inget - det är inte dags än.
    app._uppdateringsvakt_tick()
    assert anrop == [1]


def test_a_busy_app_restarts_when_it_becomes_idle(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp_path / "data"))
    app = _Sken()
    app._restart_app = lambda tyst=False: app.omstarter.append(tyst) or True
    app._busy = True
    app._planera_omstart(tyst=True)
    assert app._omstart_vantar is True
    assert app.omstarter == []                  # inget avbrott i sorteringen
    assert app.root.efter[-1] == 60000          # nytt försök om en minut
    app._busy = False
    app._omstart_nar_ledig()
    assert app.omstarter == [True] and app._omstart_vantar is False


def test_restart_releases_the_lock_then_starts_the_new_process(
        tmp_path, monkeypatch):
    händelser = []

    class _Lås:
        def release(self):
            händelser.append("release")

        def acquire(self):
            händelser.append("acquire")
            return True

    class _Popen:
        def __init__(self, cmd, **kw):
            händelser.append(("popen", cmd, kw))

    monkeypatch.setattr(P.subprocess, "Popen", _Popen)
    monkeypatch.setattr(P, "session_log", lambda *a, **k: None)
    monkeypatch.setattr(P, "close_session", lambda: None)
    app = _Sken(instanslås=_Lås())
    app._spara_fore_omstart = lambda: None

    assert app._restart_app(tyst=True) is True
    assert händelser[0] == "release"             # låset först
    namn = [h[0] if isinstance(h, tuple) else h for h in händelser]
    assert namn == ["release", "popen"]
    cmd = händelser[1][1]
    assert cmd[0] and cmd[1].endswith("pdfsorter.py")
    assert app.root.riven is True


def test_restart_that_fails_keeps_the_window_and_the_lock(tmp_path, monkeypatch):
    händelser = []

    class _Lås:
        def release(self):
            händelser.append("release")

        def acquire(self):
            händelser.append("acquire")
            return True

    def _fel(cmd, **kw):
        raise OSError("går inte att starta")

    monkeypatch.setattr(P.subprocess, "Popen", _fel)
    monkeypatch.setattr(P, "session_log", lambda *a, **k: None)
    monkeypatch.setattr(P, "close_session", lambda: None)
    app = _Sken(instanslås=_Lås())
    app._spara_fore_omstart = lambda: None

    assert app._restart_app(tyst=True) is False
    assert händelser == ["release", "acquire"]   # låset tillbaka
    assert app.root.riven is False               # fönstret är kvar
    assert any(n == "warn" for n, _t in app.handelser)


def test_new_version_is_a_notice_when_autoupdate_is_off(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp_path / "data"))
    app = _Sken()
    app.settings["auto_update"] = False

    def _nej(*a, **k):
        raise AssertionError("autouppdatering är av - inget ska installeras")
    monkeypatch.setattr(P, "perform_update", _nej)
    monkeypatch.setattr(P, "session_log", lambda *a, **k: None)

    app._update_prompt(_info_med_ny_version(), manual=False)
    assert app.messagebox.fragor == [] and app.messagebox.varningar == []
    assert app.aviseringar and "9.9.9" in app.aviseringar[0]
    assert any("Ny version 9.9.9" in t for _n, t in app.handelser)
