from pathlib import Path

import pytest

import pdfsorter as P
from pdfsorter_data import Rules
from pdfsorter_read import Extraction


def _pdf(path: Path, text: str) -> Path:
    fitz = pytest.importorskip("fitz")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((48, 60), text, fontsize=12)
    doc.save(path)
    doc.close()
    return path


def _extraction(path: Path, text: str) -> Extraction:
    source = _pdf(path, text)
    return P.read_pdf(source, {})


def _rules(path: Path, mapping=None):
    return Rules({"categories": [{
        "name": "HorseTools Sweden AB",
        "folder": "HorseTools Sweden AB",
        "keywords": ["Horsetools", "faktura", "utbetalning"],
        "default_keyword": "horsetools",
        "subfolder_keyword_map": mapping or {
            "faktura": "Faktura",
            "utbetalning": "Utbetalningar",
        },
    }]}, path)


def test_exact_keyword_mapping_selects_its_folder_only(tmp_path):
    rules = _rules(tmp_path / "rules.json")
    invoice = _extraction(tmp_path / "invoice.pdf", "Horsetools faktura")
    payment = _extraction(tmp_path / "payment.pdf", "Horsetools utbetalning")
    unknown = _extraction(tmp_path / "unknown.pdf", "Horsetools avtal")

    assert P.match_subfolder_keyword(
        rules, "HorseTools Sweden AB", invoice) == ("Faktura", True)
    assert P.match_subfolder_keyword(
        rules, "HorseTools Sweden AB", payment) == ("Utbetalningar", True)
    assert P.match_subfolder_keyword(
        rules, "HorseTools Sweden AB", unknown) == ("", True)


def test_conflicting_mapped_words_require_review(tmp_path):
    rules = _rules(tmp_path / "rules.json")
    extraction = _extraction(
        tmp_path / "both.pdf", "Horsetools faktura utbetalning")

    assert P.match_subfolder_keyword(
        rules, "HorseTools Sweden AB", extraction) == ("", True)


def test_selected_default_word_is_required_for_automatic_category_evidence(
        tmp_path):
    rules = _rules(tmp_path / "rules.json")
    cat = rules.get("HorseTools Sweden AB")
    cat["keywords"].append({
        "text": "kundnummer 98765", "weight": 1, "whole_word": True,
        "hits": 0, "source": "user",
    })
    without_default = _extraction(
        tmp_path / "no-anchor.pdf", "faktura kundnummer 98765")
    with_default = _extraction(
        tmp_path / "anchor.pdf", "Horsetools faktura")

    assert P.exact_support_matches(rules, without_default) == {}
    assert list(P.exact_support_matches(rules, with_default)) == [
        "HorseTools Sweden AB"]


def test_apply_routes_to_mapped_subfolder_and_keeps_category_safety(
        monkeypatch, tmp_path):
    source = _pdf(tmp_path / "invoice.pdf", "Horsetools faktura")
    rules = _rules(tmp_path / "rules.json")
    monkeypatch.setattr(P, "exact_auto_category",
                        lambda *_args: "HorseTools Sweden AB")
    monkeypatch.setattr(P, "load_history", lambda: [])
    monkeypatch.setattr(P, "append_history", lambda _event: None)
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "Arkiv"), "year_subfolder": False,
        "date_enabled": False, "tag_pdf_metadata": False,
    })
    decision = P.Decision(
        source, P.read_pdf(source, {}),
        [P.CategoryScore("HorseTools Sweden AB", 10)], "auto")

    ok, result = engine.apply(
        decision, "HorseTools Sweden AB", ["Horsetools", "faktura"],
        decided_by="auto")

    assert ok, result
    assert (tmp_path / "Arkiv" / "HorseTools Sweden AB" / "Faktura"
            / "invoice.pdf").exists()


def test_active_mapping_without_unique_match_leaves_source_untouched(
        monkeypatch, tmp_path):
    source = _pdf(tmp_path / "invoice.pdf", "Horsetools faktura utbetalning")
    rules = _rules(tmp_path / "rules.json")
    monkeypatch.setattr(P, "exact_auto_category",
                        lambda *_args: "HorseTools Sweden AB")
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "Arkiv"), "year_subfolder": False,
        "date_enabled": False,
    })
    decision = P.Decision(
        source, P.read_pdf(source, {}),
        [P.CategoryScore("HorseTools Sweden AB", 10)], "auto")

    ok, message = engine.apply(
        decision, "HorseTools Sweden AB", ["Horsetools", "faktura"],
        decided_by="auto")

    assert not ok
    assert "kopplade" in message.lower()
    assert source.exists()


def test_confirming_current_archive_destination_does_not_create_rename_copy(
        monkeypatch, tmp_path):
    output = tmp_path / "Arkiv"
    source = _pdf(output / "HorseTools Sweden AB" / "Faktura" / "invoice.pdf",
                  "Horsetools faktura")
    rules = _rules(tmp_path / "rules.json")
    monkeypatch.setattr(P, "append_history", lambda _event: None)
    engine = P.SortEngine(rules, {
        "output_dir": str(output), "year_subfolder": False,
        "date_enabled": False, "tag_pdf_metadata": False,
    })
    engine._remember_content_file = lambda *_args, **_kwargs: None
    decision = P.Decision(
        source, P.read_pdf(source, {}),
        [P.CategoryScore("HorseTools Sweden AB", 10)], "ask")

    ok, message = engine.apply(
        decision, "HorseTools Sweden AB", ["Horsetools", "faktura"],
        decided_by="user", subfolder_override="Faktura")

    assert ok, message
    assert source.exists()
    assert list(source.parent.glob("*.pdf")) == [source]


def test_default_and_folder_links_roundtrip_and_stale_links_are_removed(tmp_path):
    path = tmp_path / "rules.json"
    rules = _rules(path)
    rules.save()

    loaded = Rules.load(path)
    cat = loaded.get("HorseTools Sweden AB")
    assert cat["default_keyword"] == "horsetools"
    assert cat["subfolder_keyword_map"] == {
        "faktura": "Faktura", "utbetalning": "Utbetalningar"}

    loaded.remove_keyword("HorseTools Sweden AB", "faktura")
    loaded.save()
    reloaded = Rules.load(path).get("HorseTools Sweden AB")
    assert "faktura" not in reloaded["subfolder_keyword_map"]
