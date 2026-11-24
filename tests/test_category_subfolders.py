from __future__ import annotations

from datetime import date
import pdfsorter as P
from pdfsorter_data import Rules
from pdfsorter_read import Extraction


def test_category_default_and_per_file_subfolders_are_nested(tmp_path):
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"category subfolder")
    rules = Rules({"categories": [{
        "name": "Acme", "folder": "Acme",
        "subfolder_path": "Fakturor/Skannat",
    }]}, tmp_path / "rules.json")
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "out"), "year_subfolder": False,
        "date_enabled": False,
    })
    decision = P.Decision(source, Extraction(path=source), [], "ask")

    ok, message = engine.apply(
        decision, "Acme", [], decided_by="user", subfolder_override="Granskad")

    assert ok, message
    assert (tmp_path / "out" / "Acme" / "Fakturor" / "Skannat"
            / "Granskad" / "invoice.pdf").exists()
    assert Rules.load(rules.path).get("Acme")["subfolder_path"] == "Fakturor/Skannat"


def test_category_default_subfolder_follows_date_folder(tmp_path):
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"category dated subfolder")
    rules = Rules({"categories": [{
        "name": "Acme", "folder": "Acme", "subfolder": "{år}",
        "subfolder_path": "Fakturor",
    }]}, tmp_path / "rules.json")
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "out"), "year_subfolder": True,
        "date_enabled": True,
    })
    extraction = Extraction(path=source, doc_date=date(2025, 3, 14))
    decision = P.Decision(source, extraction, [], "ask")

    ok, message = engine.apply(decision, "Acme", [], decided_by="user")

    assert ok, message
    assert (tmp_path / "out" / "Acme" / "2025" / "Fakturor"
            / "invoice.pdf").exists()


def test_invalid_category_subfolder_is_rejected_without_moving_file(tmp_path):
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"unsafe path")
    rules = Rules({"categories": [{
        "name": "Acme", "folder": "Acme", "subfolder_path": "../escape",
    }]}, tmp_path / "rules.json")
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "out"), "year_subfolder": False,
        "date_enabled": False,
    })
    decision = P.Decision(source, Extraction(path=source), [], "ask")

    ok, message = engine.apply(decision, "Acme", [], decided_by="user")

    assert not ok
    assert "ogiltig" in message.lower()
    assert source.exists()
    assert not (tmp_path / "escape" / source.name).exists()


def test_rules_keep_category_subfolder_path_and_default_it_for_old_rules(tmp_path):
    rules = Rules({"categories": [
        {"name": "Old", "keywords": []},
        {"name": "New", "keywords": [], "subfolder_path": "Invoices/Scanned"},
    ]}, tmp_path / "rules.json")

    assert rules.get("Old")["subfolder_path"] == ""
    assert rules.get("New")["subfolder_path"] == "Invoices/Scanned"
    rules.save()
    loaded = Rules.load(rules.path)
    assert loaded.get("New")["subfolder_path"] == "Invoices/Scanned"


def test_category_settings_picker_base_uses_year_and_date_template(tmp_path):
    app = P.App.__new__(P.App)
    app.settings = {
        "output_dir": str(tmp_path / "out"), "year_subfolder": True,
        "date_enabled": True,
    }
    cat = {"folder": "Acme", "subfolder": "{år}/{månad}"}

    base = P.App._category_subfolder_base(app, cat, date(2024, 3, 14))

    assert base == tmp_path / "out" / "Acme" / "2024" / "03"


def test_review_picker_base_includes_category_default_and_document_year(tmp_path):
    source = tmp_path / "invoice.pdf"
    rules = Rules({"categories": [{
        "name": "Acme", "folder": "Acme", "subfolder": "{år}",
        "subfolder_path": "Fakturor",
    }]}, tmp_path / "rules.json")
    settings = {"output_dir": str(tmp_path / "out"), "year_subfolder": True,
                "date_enabled": True}
    app = P.App.__new__(P.App)
    app.rules = rules
    app.settings = settings
    app.engine = P.SortEngine(rules, settings)
    decision = P.Decision(
        source, Extraction(path=source, doc_date=date(2024, 2, 1)), [], "ask")

    base = P.App._review_subfolder_base(app, decision, "Acme")

    assert base == tmp_path / "out" / "Acme" / "2024" / "Fakturor"
