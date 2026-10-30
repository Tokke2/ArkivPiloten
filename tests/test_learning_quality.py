from __future__ import annotations

from datetime import date
from pathlib import Path

import pdfsorter as P
from pdfsorter_data import Rules


def _rules(tmp_path):
    return Rules({"categories": []}, tmp_path / "rules.json")


def test_zone_features_and_rejected_feedback_are_specific(tmp_path):
    extraction = P.Extraction(
        path=tmp_path / "report.pdf",
        text="Acme Services AB\nOrg nr 556000-0000\n\nFakturaadress: Northwind\n\nBetala senast fredag\nAcme support",
        filename_text="Acme_invoice",
    )
    features = P.learn_features(extraction)
    assert "header:acme" in features
    assert "recipient:northwind" in features
    assert "filename:acme" in features

    score = P.CategoryScore(
        "Acme", 2.0, matched=["Acme", "Northwind"],
        zones={"Acme": "header", "Northwind": "recipient"})
    rejected = P.rejected_learning_features(score)
    assert "acme" in rejected
    assert "header:acme" in rejected
    assert "recipient:northwind" in rejected
    assert "body:friday" not in rejected


def test_model_trains_targeted_corrections_and_calibration(tmp_path):
    matcher = P.LearnedMatcher(tmp_path / "model.json")
    matcher.train("Correct", ["header:acme", "body:invoice"],
                  incorrect_for="Wrong", rejected_tokens=["acme", "header:acme"])
    assert matcher.cats["Correct"]["calibration"]["correct"] == 1
    assert matcher.cats["Wrong"]["calibration"]["incorrect"] == 1
    assert matcher.cats["Wrong"]["neg"] == {"acme": 1, "header:acme": 1}
    matcher.flush()
    model_path = tmp_path / "model.json"
    loaded = P.LearnedMatcher(model_path)
    assert loaded.cats["Correct"]["w"]["header:acme"] == 1
    model_path.write_text("{damaged", encoding="utf-8")
    recovered = P.LearnedMatcher(model_path)
    assert recovered.cats["Correct"]["w"]["header:acme"] == 1
    assert Path(str(model_path) + ".bak").exists()


def test_backtest_replays_each_event_only_after_scoring_it():
    events = [{
        "time": f"2025-01-{day:02d}T00:00:00+00:00",
        "category": "Acme", "features": ["header:acme"],
        "decided_by": "user",
    } for day in range(1, 6)]
    events.append({
        "time": "2025-01-06T00:00:00+00:00", "category": "Other",
        "features": ["header:acme"], "decided_by": "user",
    })
    result = P.replay_learned_history(events)
    assert result["tested"] == 1
    assert result["correct"] == 0
    assert result["accuracy"] == 0.0


def test_restore_and_reset_are_scoped_to_one_category(tmp_path):
    matcher = P.LearnedMatcher(tmp_path / "model.json")
    matcher.train("Unrelated", ["filename:other"])
    events = [
        {"time": "2025-01-01T00:00:00+00:00", "category": "Target",
         "features": ["header:target"], "decided_by": "user"},
        {"time": "2025-01-02T00:00:00+00:00", "category": "Right",
         "features": ["body:correction"], "corrected_from": "Target",
         "rejected_features": ["header:wrong"], "decided_by": "user"},
    ]
    restored = P.restore_learned_category("Target", events, matcher)
    assert restored == 1
    assert matcher.cats["Target"]["w"] == {"header:target": 1}
    assert matcher.cats["Target"]["neg"] == {"header:wrong": 1}
    assert "Unrelated" in matcher.cats
    P.reset_learned_category("Target", matcher)
    assert "Target" not in matcher.cats
    assert "Unrelated" in matcher.cats


def test_custom_date_template_keeps_year_folder(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(b"pdf")
    engine = P.SortEngine(_rules(tmp_path), {
        "date_enabled": True, "date_default_template": "{månad}/{år}",
        "year_subfolder": True,
    })
    extraction = P.Extraction(path=source, doc_date=date(2022, 3, 8),
                              date_source="dokumentdatum")
    subfolder, when, _ = engine.subfolder_for(extraction)
    assert subfolder == "2022/03"
    assert when == date(2022, 3, 8)


def test_unknown_document_date_keeps_year_under_unknown_folder(tmp_path):
    source = tmp_path / "unknown.pdf"
    source.write_bytes(b"pdf")
    engine = P.SortEngine(_rules(tmp_path), {
        "date_enabled": True, "date_fallback": "unknown",
        "date_default_template": "{år}/{månad}", "year_subfolder": True,
    })
    subfolder, _when, origin = engine.subfolder_for(P.Extraction(path=source))
    assert subfolder.endswith("/Utan datum")
    assert subfolder.split("/")[0].isdigit()
    assert origin == "saknas"


def test_unmatched_files_are_placed_inside_year_folder(tmp_path):
    source = tmp_path / "unmatched.pdf"
    source.write_bytes(b"pdf")
    output = tmp_path / "output"
    engine = P.SortEngine(_rules(tmp_path), {
        "output_dir": str(output), "unmatched_folder": "_Osorterat",
        "action": "move", "on_conflict": "rename",
        "year_subfolder": True,
    })
    decision = P.Decision(source, P.Extraction(path=source), [], "ask", "unsure")
    ok, target = engine.send_to_unmatched(decision)
    assert ok
    destination = Path(target)
    assert destination.parent.parent.name == "_Osorterat"
    assert destination.parent.name.isdigit()
    assert destination.exists()
