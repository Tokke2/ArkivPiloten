# -*- coding: utf-8 -*-
"""AI-rapporten: alla fel på ett ställe, klart på noll sekunder.

Kraven som testas:

* **Alla fel** - även de som Tk fångar själv (``report_callback_exception``)
  och de som kommer från trådar. Tidigare försvann de när appen startades
  med ``pythonw``, eftersom Tk bara skriver till ``stderr``.
* **Ett fel = en rad** - samma fel som synts i minnet, i sessionsloggen och
  i ``errors.log`` ska slås ihop med antal, inte listas tre gånger.
* **Noll sekunder** - bara svansen av varje loggfil läses. En 5 MB-logg får
  inte innebära 5 MB läsning, och tiden ska inte växa med filstorleken.
* **Säkert att klistra in** - hemkatalog och användarnamn avidentifieras.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pdfsorter_diag as D


# -- isolering -------------------------------------------------------------
def _setup(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    (logs / "2026-10").mkdir(parents=True)
    monkeypatch.setattr(D._State, "logs_dir", logs, raising=False)
    monkeypatch.setattr(D._State, "ring", D.deque(maxlen=D.RING_SIZE),
                        raising=False)
    monkeypatch.setattr(D._State, "seen", {}, raising=False)
    monkeypatch.setattr(D._State, "last_dump", 0.0, raising=False)
    monkeypatch.setattr(D._State, "dump_path", None, raising=False)
    monkeypatch.setattr(D._State, "logger", None, raising=False)
    monkeypatch.setattr(D._State, "extra", None, raising=False)
    monkeypatch.setattr(D._State, "version", "9.9.9", raising=False)
    monkeypatch.setattr(D._State, "app_name", "ArkivPiloten", raising=False)
    return logs


SESSION = """09:31:12.100  INFO  start      App startad
09:31:20.000  FEL   granska    TclError: cannot invoke "toplevel" command: application has been destroyed
                        File "D:\\Program\\ArkivPiloten\\pdfsorter.py", line 5383, in _process_queue
                        File "D:\\Program\\ArkivPiloten\\pdfsorter.py", line 2443, in __init__
09:31:20.100  FEL   granska    TclError: cannot invoke "toplevel" command: application has been destroyed
                        File "D:\\Program\\ArkivPiloten\\pdfsorter.py", line 5390, in _process_queue
09:31:21.000  VARN  fönster    Fönstret minimeras - systemfält saknas
"""

ERRORS = """
===== 2026-10-21T09:31:20+02:00 (session abc) =====
Traceback (most recent call last):
  File "D:/Program/ArkivPiloten/pdfsorter.py", line 5383, in _process_queue
    dlg = ReviewDialog(...)
_tkinter.TclError: cannot invoke "toplevel" command: application has been destroyed
"""


# -- fingeravtryck ---------------------------------------------------------
def test_same_error_gets_the_same_fingerprint_despite_noise():
    a = D.fingerprint('ValueError: bad page 3 of 12',
                      'File "x/pdfsorter_read.py", line 900, in read_pdf')
    b = D.fingerprint('ValueError: bad page 7 of 90',
                      'File "y/pdfsorter_read.py", line 1234, in read_pdf')
    assert a == b


def test_module_prefix_is_ignored_in_the_fingerprint():
    a = D.fingerprint("TclError: application has been destroyed", "")
    b = D.fingerprint("_tkinter.TclError: application has been destroyed", "")
    c = D.fingerprint(
        "pdfminer.pdfparser.PDFSyntaxError: No /Root object!", "")
    d_ = D.fingerprint("PDFSyntaxError: No /Root object!", "")
    assert a == b
    assert c == d_


def test_different_errors_are_kept_apart():
    a = D.fingerprint("ValueError: bad page", "")
    b = D.fingerprint("OSError: filen finns inte", "")
    assert a != b


# -- inläsning -------------------------------------------------------------
def test_parse_session_log_reads_levels_and_full_traceback():
    poster = D.parse_session_log(SESSION)
    assert [p["nivå"] for p in poster] == ["FEL", "FEL", "VARN"]
    assert poster[0]["område"] == "granska"
    assert "line 5383" in poster[0]["spårning"]
    assert poster[0]["ram"] == "pdfsorter.py:_process_queue"
    assert poster[2]["meddelande"] == "Fönstret minimeras - systemfält saknas"


def test_parse_error_blocks():
    poster = D.parse_error_blocks(ERRORS)
    assert len(poster) == 1
    assert poster[0]["meddelande"].startswith("_tkinter.TclError")
    assert poster[0]["ram"] == "pdfsorter.py:_process_queue"


def test_tail_text_never_reads_the_whole_file(tmp_path):
    stor = tmp_path / "app_stor.log"
    with open(stor, "w", encoding="utf-8") as fh:
        for i in range(200_000):          # ~5 MB
            fh.write(f"09:00:00.000  INFO  start      rad {i}\n")
        fh.write("09:59:59.000  FEL   motor      Sista felet\n")
    text = D.tail_text(stor, max_bytes=20_000)
    assert len(text.encode("utf-8")) <= 20_000
    assert "Sista felet" in text
    assert "rad 0\n" not in text           # början är borta - bara svansen


def test_tail_text_on_missing_file_is_empty(tmp_path):
    assert D.tail_text(tmp_path / "finns-inte.log") == ""


# -- hel eller delvis läsning ----------------------------------------------
def test_small_logs_are_read_in_full(tmp_path):
    fil = tmp_path / "liten.log"
    fil.write_text("09:00:00.000  FEL   motor      Första felet\n"
                   "09:59:59.000  FEL   motor      Sista felet\n",
                   encoding="utf-8")
    läst = D.read_log(fil)
    assert läst["trunkerad"] is False
    assert "Första felet" in läst["text"]


def test_large_logs_are_truncated_and_say_so(tmp_path, monkeypatch):
    fil = tmp_path / "stor.log"
    with open(fil, "w", encoding="utf-8") as fh:
        fh.write("09:00:00.000  FEL   motor      Första felet\n")
        for i in range(200_000):
            fh.write(f"09:10:00.000  INFO  start      rad {i}\n")
    monkeypatch.setattr(D, "FULL_READ_MAX", 10_000)
    läst = D.read_log(fil, tail_bytes=5_000)
    assert läst["trunkerad"] is True
    assert läst["läst"] <= 6_000
    assert "Första felet" not in läst["text"]


def test_deep_reading_finds_an_error_in_the_middle(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    fil = logs / "2026-10" / "app_20261021_000000_abc.log"
    with open(fil, "w", encoding="utf-8") as fh:
        fh.write("09:00:00.000  INFO  start      början\n")
        for i in range(100_000):
            fh.write(f"09:10:00.000  INFO  start      rad {i}\n")
        fh.write("09:20:00.000  FEL   granska    "
                 "TclError: application has been destroyed\n")
        for i in range(100_000):
            fh.write(f"09:30:00.000  INFO  start      rad {i}\n")
    monkeypatch.setattr(D, "FULL_READ_MAX", 50_000)
    ytlig = D.build_ai_report(logs)
    assert "application has been destroyed" not in ytlig
    assert "lästes bara delvis" in ytlig
    assert "--djup" in ytlig
    djup = D.build_ai_report(logs, djup=True)
    assert "application has been destroyed" in djup
    assert "lästes bara delvis" not in djup


def test_report_is_honest_when_nothing_was_found_in_a_partial_read(
        tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    fil = logs / "2026-10" / "app_20261021_000000_abc.log"
    fil.write_text("x" * 400_000 + "\n", encoding="utf-8")
    monkeypatch.setattr(D, "FULL_READ_MAX", 10_000)
    text = D.build_ai_report(logs, max_bytes=5_000)
    assert "INGA FEL ELLER VARNINGAR HITTADES" in text
    assert "lästes bara delvis" in text
    assert "Alla loggfiler lästes i sin helhet" not in text


def test_update_file_lists_never_drift():
    """Zip:en, autouppdateringen och engångsuppgraderaren ska röra samma filer."""
    import importlib.util

    import pdfsorter_system as S
    verktyg = Path(__file__).resolve().parents[1] / "tools" / "install_latest.py"
    spec = importlib.util.spec_from_file_location("_il", verktyg)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    assert set(modul.FILES) == set(S.UPDATE_FILES)
    assert "pdfsorter_diag.py" in S.UPDATE_FILES


# -- hopslagning -----------------------------------------------------------
def test_the_same_error_from_memory_log_and_errors_log_is_one_row(
        tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    (logs / "2026-10" / "app_20261021_093112_abc.log").write_text(
        SESSION, encoding="utf-8")
    (logs / "2026-10" / "errors.log").write_text(ERRORS, encoding="utf-8")
    D.note("granska", 'TclError: cannot invoke "toplevel" command: '
                       'application has been destroyed',
           tb_text='File "D:/Program/ArkivPiloten/pdfsorter.py", line 1, '
                   'in _process_queue')

    data = D.collect(logs)
    tcl = [p for p in data["fel"]
           if "application has been destroyed" in p["meddelande"]]
    assert len(tcl) == 1, tcl
    # 2 rader i sessionsloggen + 1 i errors.log + 1 i minnet
    assert tcl[0]["antal"] == 4
    assert set(tcl[0]["källor"]) >= {
        "app_20261021_093112_abc.log", "errors.log", "minne"}


def test_warnings_are_separated_from_errors(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    (logs / "2026-10" / "app_20261021_093112_abc.log").write_text(
        SESSION, encoding="utf-8")
    data = D.collect(logs)
    assert len(data["varningar"]) == 1
    assert data["varningar"][0]["meddelande"].startswith("Fönstret minimeras")


# -- Tk-kroken -------------------------------------------------------------
class _FakeRoot:
    def __init__(self):
        self.gammal_anropad = 0

    def report_callback_exception(self, *a):
        self.gammal_anropad += 1


def test_tk_callback_exception_is_captured(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    root = _FakeRoot()
    D.install_tk_hooks(root)
    assert callable(root.report_callback_exception)

    try:
        raise RuntimeError('cannot invoke "toplevel" command')
    except RuntimeError:
        typ, värde, tb = sys.exc_info()
    root.report_callback_exception(typ, värde, tb)

    poster = list(D._State.ring)
    assert poster and poster[-1]["område"] == "tk-callback"
    assert "cannot invoke" in poster[-1]["meddelande"]
    # Tk:s eget beteende behålls (stderr där det finns).
    assert root.gammal_anropad == 1
    rapport = D.build_ai_report(logs)
    assert "tk-callback" in rapport


def test_tk_hook_never_raises_even_when_logging_fails(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    def spräng(*a, **k):
        raise OSError("disken full")

    monkeypatch.setattr(D, "note", spräng)
    root = _FakeRoot()
    D.install_tk_hooks(root)
    root.report_callback_exception(RuntimeError, RuntimeError("x"), None)


# -- rapporten -------------------------------------------------------------
def test_report_shows_every_error_with_counts_and_no_duplicates(
        tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    (logs / "2026-10" / "app_20261021_093112_abc.log").write_text(
        SESSION, encoding="utf-8")
    (logs / "2026-10" / "errors.log").write_text(ERRORS, encoding="utf-8")
    text = D.build_ai_report(logs)

    assert "AI-RAPPORT" in text
    assert "FEL: 1 unik, 3 förekomster" in text
    assert "VARNINGAR: 1 unik" in text
    assert "×3" in text
    assert text.count("application has been destroyed") < 8
    assert "SENASTE HÄNDELSER" in text
    assert "LÄSTA LOGGFILER" in text


def test_report_says_clearly_when_there_is_nothing(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    (logs / "2026-10" / "app_20261021_093112_abc.log").write_text(
        "09:31:12.100  INFO  start      App startad\n", encoding="utf-8")
    text = D.build_ai_report(logs)
    assert "INGA FEL ELLER VARNINGAR HITTADES" in text


def test_report_is_fast_and_bounded_on_a_large_log(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    fil = logs / "2026-10" / "app_20261021_000000_abc.log"
    with open(fil, "w", encoding="utf-8") as fh:
        for i in range(200_000):
            fh.write(f"09:00:00.000  INFO  start      rad {i}\n")
        fh.write("09:59:59.000  FEL   motor      Riktigt fel\n")
    data = D.collect(logs, max_bytes=50_000)
    assert data["byte"] <= 60_000
    assert data["sekunder"] < 1.0
    text = D.build_ai_report(logs, max_bytes=50_000)
    assert "Riktigt fel" in text


def test_report_redacts_home_and_username(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    hem = str(Path.home())
    användare = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    fil = logs / "2026-10" / "app_20261021_000000_abc.log"
    fil.write_text(
        f'09:31:20.000  FEL   motor      Kan inte öppna {hem}/hemligt.pdf\n',
        encoding="utf-8")
    text = D.build_ai_report(logs)
    assert hem not in text
    if användare and len(användare) > 2:
        assert användare not in text


def test_ai_report_includes_extra_status_lines(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    text = D.build_ai_report(logs, extra=["Autostart: på", "Regler: 3 kategorier"])
    assert "Autostart: på" in text
    assert "Regler: 3 kategorier" in text


# -- filen som alltid finns ------------------------------------------------
def test_dump_report_writes_a_file_atomically(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    mål = D.dump_report(logs)
    assert mål is not None and mål.exists()
    assert "AI-RAPPORT" in mål.read_text(encoding="utf-8")
    assert not mål.with_suffix(".tmp").exists()
    assert D.latest_report_path() == mål


def test_summary_line_for_the_status_bar(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    assert D.sammanfattning(logs) == "Inga fel loggade"
    (logs / "2026-10" / "app_20261021_093112_abc.log").write_text(
        SESSION, encoding="utf-8")
    rad = D.sammanfattning(logs)
    assert "1 fel" in rad and "1 varning" in rad


# -- appens egna krokar ----------------------------------------------------
def test_system_excepthook_feeds_the_report(tmp_path, monkeypatch):
    """Systemets excepthook ska också landa i AI-rapporten (utan dubblett)."""
    import pdfsorter_system as S
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(S, "session_log", lambda *a, **k: None)
    monkeypatch.setattr(S, "_write_errors_log", lambda *a, **k: None)
    monkeypatch.setattr(S, "_OLD_EXCEPTHOOK", None, raising=False)
    S.install_excepthooks()
    try:
        raise ValueError("fel i huvudtråden")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    poster = [p for p in D._State.ring if "huvudtråden" in p["meddelande"]]
    assert len(poster) == 1
    assert poster[0]["nivå"] == "FEL"
    assert "ValueError" in poster[0]["spårning"]
