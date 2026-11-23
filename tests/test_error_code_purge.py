# -*- coding: utf-8 -*-
"""Rensa åtgärdade fel från loggen - och dölj dem i AI-rapporten.

Flödet: användaren fixar ett fel, markerar felkoden som åtgärdad och
rensar sedan bort dess poster ur felloggen. Kraven som låses här:

* En kod markerad ÅTGÄRDAD försvinner ur AI-rapporten även när samma
  feltext också står kvar i sessionsloggarna (samma fingeravtryck).
* Rensningen tar bort ÖPPEN-blocken ur felkoder.log men behåller
  ÅTGÄRDAD-kvittot - annars skulle rapporten tappa vetskapen om att
  felet är fixat och visa det igen.
* Matchande felposter försvinner också ur fel-samlat.log (inklusive
  indragna spårningsrader); orörda fel och främmande rader bevaras.
* Sessionsloggarna (app_*.log) rörs aldrig - de är revisionsspåret.
"""
from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pdfsorter as P
import pdfsorter_diag as D
import pdfsorter_system as S

ROOT = Path(__file__).resolve().parents[1]

MEDDELANDE = "Faktura-946.pdf  ✖ PSEOF: Unexpected EOF"
SPAR = 'File "D:\\Program\\ArkivPiloten\\pdfsorter.py", line 1, in las_pdf'


def _setup(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir(parents=True)
    monkeypatch.setattr(D._State, "seen", {}, raising=False)
    monkeypatch.setattr(S, "session_dir", lambda: logs)
    return logs


def _felkod(kod, status, detalj="sortering " + MEDDELANDE, ts="2026-11-20T10:00:00"):
    return f"\n===== {ts} =====\nFELKOD:{kod} [{status}] {detalj}\n"


def test_states_track_latest_status_and_keep_the_open_message():
    kod = D.fingerprint(MEDDELANDE, SPAR)
    text = (_felkod(kod, "ÖPPEN") + _felkod(kod, "ÖPPEN") +
            _felkod(kod, "ÅTGÄRDAD", "fixad i test"))
    states = D.parse_error_code_states(text)
    assert states[kod]["status"] == "ÅTGÄRDAD"
    assert states[kod]["antal"] == 3
    assert states[kod]["kategori"] == "sortering"
    assert states[kod]["meddelande"] == MEDDELANDE


def test_reopened_code_is_open_again():
    kod = D.fingerprint(MEDDELANDE, SPAR)
    text = (_felkod(kod, "ÖPPEN") + _felkod(kod, "ÅTGÄRDAD", "") +
            _felkod(kod, "ÖPPEN"))
    states = D.parse_error_code_states(text)
    assert states[kod]["status"] == "ÖPPEN"


def test_collect_hides_resolved_codes_from_every_source(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    kod = D.fingerprint(MEDDELANDE, SPAR)
    (logs / "felkoder.log").write_text(
        _felkod(kod, "ÖPPEN") + _felkod(kod, "ÅTGÄRDAD", "fixad"),
        encoding="utf-8")
    rad = (f"10:00:00.000  FEL   sortering  {MEDDELANDE}\n"
           f"                      {SPAR}\n")
    (logs / "app_test.log").write_text(rad, encoding="utf-8")
    (logs / "fel-samlat.log").write_text(rad, encoding="utf-8")

    data = D.collect(logs)

    assert data["dolda_atgardade"] == 1
    assert all(p.get("fp") != kod for p in data["fel"])


def test_collect_still_shows_open_codes(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    kod = D.fingerprint(MEDDELANDE, SPAR)
    (logs / "felkoder.log").write_text(_felkod(kod, "ÖPPEN"), encoding="utf-8")

    data = D.collect(logs)

    assert data["dolda_atgardade"] == 0
    assert [p["fp"] for p in data["fel"]] == [kod]


def test_report_mentions_hidden_resolved_errors(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    kod = D.fingerprint(MEDDELANDE, SPAR)
    (logs / "felkoder.log").write_text(
        _felkod(kod, "ÖPPEN") + _felkod(kod, "ÅTGÄRDAD", "fixad"),
        encoding="utf-8")
    (logs / "app_test.log").write_text(
        f"10:00:00.000  FEL   sortering  {MEDDELANDE}\n"
        f"                      {SPAR}\n",
        encoding="utf-8")

    text = D.build_ai_report(logs)

    assert "Dolda: 1 åtgärdat fel" in text
    assert "--- FEL " not in text


def _skriv_felkoder(logs):
    oppen = D.fingerprint("öppet fel", "")
    fast = D.fingerprint(MEDDELANDE, SPAR)
    (logs / "felkoder.log").write_text(
        _felkod(oppen, "ÖPPEN", "sortering öppet fel") +
        _felkod(fast, "ÖPPEN") + _felkod(fast, "ÖPPEN") +
        _felkod(fast, "ÅTGÄRDAD", "fixad") +
        "en främmande rad som måste bevaras\n",
        encoding="utf-8")
    return oppen, fast


def test_list_error_codes_shows_open_first(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    oppen, fast = _skriv_felkoder(logs)

    koder = S.list_error_codes()

    assert [p["kod"] for p in koder] == [oppen, fast]
    assert koder[0]["status"] == "ÖPPEN"
    assert koder[1]["status"] == "ÅTGÄRDAD"
    assert koder[1]["antal"] == 3
    assert koder[1]["meddelande"] == MEDDELANDE


def test_list_error_codes_without_log_is_empty(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert S.list_error_codes() == []


def test_purge_removes_open_blocks_but_keeps_the_receipt(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    oppen, fast = _skriv_felkoder(logs)

    resultat = S.purge_resolved_error_codes()

    assert resultat["koder"] == [fast]
    assert resultat["block"] == 2
    kvar = (logs / "felkoder.log").read_text(encoding="utf-8")
    assert f"FELKOD:{fast} [ÖPPEN]" not in kvar
    assert f"FELKOD:{fast} [ÅTGÄRDAD] fixad" in kvar
    assert f"FELKOD:{oppen} [ÖPPEN]" in kvar
    assert "en främmande rad som måste bevaras" in kvar
    # Kvittot räcker: koden är fortfarande åtgärdad efter rensningen.
    assert D.parse_error_code_states(kvar)[fast]["status"] == "ÅTGÄRDAD"


def test_purge_cleans_matching_samlat_entries(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    _skriv_felkoder(logs)
    (logs / "fel-samlat.log").write_text(
        f"10:00:00.000  FEL   sortering  {MEDDELANDE}\n"
        f"                      {SPAR}\n"
        "10:01:00.000  FEL   sortering  orört fel\n",
        encoding="utf-8")

    resultat = S.purge_resolved_error_codes()

    assert resultat["samlat"] == 1
    kvar = (logs / "fel-samlat.log").read_text(encoding="utf-8")
    assert MEDDELANDE not in kvar
    assert SPAR not in kvar
    assert "orört fel" in kvar


def test_purge_without_resolved_codes_changes_nothing(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    kod = D.fingerprint("öppet fel", "")
    fore = _felkod(kod, "ÖPPEN", "sortering öppet fel")
    (logs / "felkoder.log").write_text(fore, encoding="utf-8")

    resultat = S.purge_resolved_error_codes()

    assert resultat == {"koder": [], "block": 0, "samlat": 0}
    assert (logs / "felkoder.log").read_text(encoding="utf-8") == fore


def test_purge_without_logs_is_a_noop(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert S.purge_resolved_error_codes() == {
        "koder": [], "block": 0, "samlat": 0}


def test_cli_purge_reports_zero_on_fresh_home(tmp_path):
    import os
    env = dict(os.environ)
    env.update({
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "home" / ".config"),
        "PDFSORTER_HOME": str(tmp_path / "data"),
        "PYTHONPATH": str(ROOT),
        "PYTHONWARNINGS": "ignore",
    })
    (tmp_path / "home").mkdir()
    (tmp_path / "data").mkdir()
    r = subprocess.run(
        [sys.executable, str(ROOT / "pdfsorter.py"),
         "--rensa-atgardade-felkoder"],
        env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "0 åtgärdade felkod(er)" in r.stdout


# -- granskningsdialogen får inte krascha utan kategoriträff ----------------
def _dlg_without_entry():
    dlg = object.__new__(P.ReviewDialog)
    dlg.mode = SimpleNamespace(get=lambda: "new")
    return dlg


def test_category_answers_empty_when_new_entry_is_missing():
    assert P.ReviewDialog._category(_dlg_without_entry()) == ""


def test_sync_survives_when_new_entry_is_missing():
    P.ReviewDialog._sync(_dlg_without_entry())


def test_template_toggle_sync_runs_after_new_entry_exists():
    kalla = inspect.getsource(P.ReviewDialog.__init__)
    assert (kalla.index("self.new_entry = ") <
            kalla.index("self._sync_subfolder_template_toggle()"))


def test_help_menu_opens_the_error_code_dialog():
    poster = [p for m in P.meny_spec() if m["titel"] == "Hjälp"
              for p in m["poster"]]
    post = next(p for p in poster if p.get("id") == "rensa_felkoder")
    assert post["atgard"] == "_open_error_code_dialog"
    assert callable(getattr(P.App, "_open_error_code_dialog", None))


# -- automatisk rensning ---------------------------------------------------
def test_marking_a_code_purges_its_entries_automatically(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    oppen, fast = _skriv_felkoder(logs)
    (logs / "fel-samlat.log").write_text(
        f"10:00:00.000  FEL   sortering  {MEDDELANDE}\n"
        f"                      {SPAR}\n",
        encoding="utf-8")

    assert S.mark_error_code_resolved(fast, "fixad nu") is True

    kvar = (logs / "felkoder.log").read_text(encoding="utf-8")
    assert f"FELKOD:{fast} [ÖPPEN]" not in kvar
    assert f"FELKOD:{fast} [ÅTGÄRDAD]" in kvar
    assert f"FELKOD:{oppen} [ÖPPEN]" in kvar
    assert MEDDELANDE not in (logs / "fel-samlat.log").read_text(
        encoding="utf-8")


def test_marking_an_unknown_code_still_writes_its_receipt(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)

    assert S.mark_error_code_resolved("12345678", "finns ej") is True

    kvar = (logs / "felkoder.log").read_text(encoding="utf-8")
    assert "FELKOD:12345678 [ÅTGÄRDAD] finns ej" in kvar


def test_startup_purges_leftover_resolved_entries(tmp_path, monkeypatch):
    logs = _setup(tmp_path, monkeypatch)
    oppen, fast = _skriv_felkoder(logs)
    monkeypatch.setattr(S, "migrate_legacy_logs", lambda: None)
    monkeypatch.setattr(S, "archive_old_logs", lambda days=1: 0)
    try:
        assert S.start_session() is not None
    finally:
        S.close_session()

    kvar = (logs / "felkoder.log").read_text(encoding="utf-8")
    assert f"FELKOD:{fast} [ÖPPEN]" not in kvar
    assert f"FELKOD:{fast} [ÅTGÄRDAD] fixad" in kvar
    assert f"FELKOD:{oppen} [ÖPPEN]" in kvar
