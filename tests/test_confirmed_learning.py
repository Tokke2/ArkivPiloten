from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pdfsorter as P
import pdfsorter_data as D


def test_learning_setting_is_fixed_on(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp_path / "data"))
    D._CONFIG_DIR_CACHE.clear()
    D.save_settings({**D.DEFAULT_SETTINGS, "learned_matching": False})
    assert D.load_settings()["learned_matching"] is True


def test_legacy_model_is_rebuilt_from_confirmed_history_only(tmp_path, monkeypatch):
    settings = {"learned_confirmed_only_v1": False}
    events = [
        {"category": "Automatic", "tokens": ["automatic"],
         "features": ["body:automatic"], "decided_by": "auto"},
        {"category": "Confirmed", "tokens": ["confirmed"],
         "features": ["header:confirmed"], "decided_by": "user"},
    ]
    saved = []
    monkeypatch.setattr(P, "_LEARNED", None)
    monkeypatch.setattr(P, "learned_model_path", lambda: tmp_path / "model.json")
    monkeypatch.setattr(P, "load_settings", lambda: settings)
    monkeypatch.setattr(P, "load_history", lambda: events)
    monkeypatch.setattr(P, "save_settings", lambda value: saved.append(dict(value)))

    model = P._learned()
    assert set(model.cats) == {"Confirmed"}
    assert settings["learned_confirmed_only_v1"] is True
    assert saved[-1]["learned_confirmed_only_v1"] is True


def test_live_model_trains_only_from_explicit_user_choices(tmp_path, monkeypatch):
    trained = []

    class RecordingMatcher:
        def train(self, category, tokens, **kwargs):
            trained.append(category)

    monkeypatch.setattr(P, "_learned", lambda: RecordingMatcher())
    monkeypatch.setattr(P, "append_history", lambda event: None)

    for source, decided_by in (("automatic.pdf", "auto"),
                               ("rescan.pdf", "rescan"),
                               ("confirmed.pdf", "user")):
        path = tmp_path / source
        path.write_text("Confirmed Acme invoice", encoding="utf-8")
        rules = D.Rules({"categories": [{"name": "Acme", "folder": "Acme"}]},
                        tmp_path / f"{source}.rules.json")
        engine = P.SortEngine(rules, {
            "output_dir": str(tmp_path / "out"), "action": "move",
            "dry_run": False, "year_subfolder": False,
            "date_enabled": False, "tag_pdf_metadata": False,
        })
        extraction = P.Extraction(path=path, text="Confirmed Acme invoice")
        decision = P.Decision(
            path, extraction, [P.CategoryScore("Acme", 1.0)], "ask")
        ok, _ = engine.apply(decision, "Acme", [], decided_by=decided_by)
        if decided_by == "user":
            assert ok
        else:
            assert not ok
            assert path.exists()

    assert trained == ["Acme"]
