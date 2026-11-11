from __future__ import annotations

from pathlib import Path

import pytest

import pdfsorter as P
from pdfsorter_data import Rules
from pdfsorter_read import Extraction


def _pdf_with_text(path: Path, text: str, *, x: float = 50, y: float = 50) -> Path:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page(width=300, height=400)
    page.insert_text((x, y), text, fontsize=12)
    doc.save(path)
    doc.close()
    return path


def _template(bbox=(0.05, 0.03, 0.65, 0.22), folder="Inbetalningar"):
    return {"folder": folder, "page": 0, "bbox": list(bbox),
            "text": "transaktioner - inbetalningar", "enabled": True}


def test_drawn_template_extracts_exact_text_from_selected_page_region(tmp_path):
    source = _pdf_with_text(
        tmp_path / "source.pdf", "Transaktioner - Inbetalningar")

    template = P.create_pdf_subfolder_template(
        source, 0, (0.05, 0.03, 0.7, 0.22), "Inbetalningar")

    assert template["folder"] == "Inbetalningar"
    assert template["text"] == "transaktioner - inbetalningar"
    assert template["page"] == 0
    assert template["enabled"] is True


def test_template_matches_same_text_in_same_area_only(tmp_path):
    rules = Rules({"categories": [{
        "name": "Handelsbanken", "folder": "Handelsbanken",
        "subfolder_templates": [_template()],
    }]}, tmp_path / "rules.json")
    same = Extraction(path=_pdf_with_text(
        tmp_path / "same.pdf", "Transaktioner - Inbetalningar"))
    changed = Extraction(path=_pdf_with_text(
        tmp_path / "changed.pdf", "Utbetalningar - Sök utbetalning"))
    other_area = Extraction(path=_pdf_with_text(
        tmp_path / "other-area.pdf", "Transaktioner - Inbetalningar",
        x=50, y=330))

    assert P.match_subfolder_template(rules, "Handelsbanken", same) == (
        "Inbetalningar", True)
    assert P.match_subfolder_template(rules, "Handelsbanken", changed) == (
        "", True)
    assert P.match_subfolder_template(rules, "Handelsbanken", other_area) == (
        "", True)


def test_automatic_apply_routes_through_a_matching_optional_template(
        monkeypatch, tmp_path):
    source = _pdf_with_text(
        tmp_path / "incoming.pdf", "Transaktioner - Inbetalningar")
    rules = Rules({"categories": [{
        "name": "Handelsbanken", "folder": "Handelsbanken",
        "subfolder_templates": [_template()],
    }]}, tmp_path / "rules.json")
    monkeypatch.setattr(P, "exact_auto_category",
                        lambda *_args: "Handelsbanken")
    monkeypatch.setattr(P, "load_history", lambda: [])
    monkeypatch.setattr(P, "append_history", lambda _event: None)
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "out"), "year_subfolder": False,
        "date_enabled": False, "tag_pdf_metadata": False,
    })
    extraction = Extraction(path=source)
    decision = P.Decision(
        source, extraction, [P.CategoryScore("Handelsbanken", 10)], "auto")

    ok, result = engine.apply(
        decision, "Handelsbanken", [], decided_by="auto")

    assert ok, result
    assert (tmp_path / "out" / "Handelsbanken" / "Inbetalningar"
            / "incoming.pdf").exists()


def test_automatic_apply_does_not_fall_back_when_enabled_template_misses(
        monkeypatch, tmp_path):
    source = _pdf_with_text(
        tmp_path / "unrecognized.pdf", "Utbetalningar - Sök utbetalning")
    rules = Rules({"categories": [{
        "name": "Handelsbanken", "folder": "Handelsbanken",
        "subfolder_templates": [_template()],
    }]}, tmp_path / "rules.json")
    monkeypatch.setattr(P, "exact_auto_category",
                        lambda *_args: "Handelsbanken")
    monkeypatch.setattr(P, "load_history", lambda: [])
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "out"), "year_subfolder": False,
        "date_enabled": False,
    })
    decision = P.Decision(
        source, Extraction(path=source),
        [P.CategoryScore("Handelsbanken", 10)], "auto")

    ok, message = engine.apply(
        decision, "Handelsbanken", [], decided_by="auto")

    assert not ok
    assert "mallarna" in message.lower()
    assert source.exists()


def test_conflicting_templates_require_review_and_toggle_is_optional(tmp_path):
    templates = [_template(folder="Inbetalningar"),
                 _template(folder="Transaktioner")]
    rules = Rules({"categories": [{
        "name": "Handelsbanken", "folder": "Handelsbanken",
        "subfolder_templates": templates,
    }]}, tmp_path / "rules.json")
    source = Extraction(path=_pdf_with_text(
        tmp_path / "both.pdf", "Transaktioner - Inbetalningar"))

    assert P.match_subfolder_template(rules, "Handelsbanken", source) == (
        "", True)
    rules.get("Handelsbanken")["subfolder_templates_enabled"] = False
    assert P.match_subfolder_template(rules, "Handelsbanken", source) == (
        "", False)


def test_template_rules_survive_rules_json_roundtrip(tmp_path):
    path = tmp_path / "rules.json"
    rules = Rules({"categories": [{
        "name": "Handelsbanken", "folder": "Handelsbanken",
        "subfolder_templates": [_template()],
        "subfolder_templates_enabled": False,
    }]}, path)
    rules.save()

    loaded = Rules.load(path)

    assert loaded.get("Handelsbanken")["subfolder_templates"] == [_template()]
    assert loaded.get("Handelsbanken")["subfolder_templates_enabled"] is False


def test_template_rejects_empty_or_invalid_selection(tmp_path):
    source = _pdf_with_text(tmp_path / "empty.pdf", "Some text")

    with pytest.raises(ValueError, match="markerad|markerade"):
        P.create_pdf_subfolder_template(source, 0, (0.8, 0.8, 0.2, 0.2),
                                        "Inbetalningar")
    with pytest.raises(ValueError, match="ingen markerbar"):
        P.create_pdf_subfolder_template(source, 0, (0.7, 0.8, 0.95, 0.95),
                                        "Inbetalningar")
