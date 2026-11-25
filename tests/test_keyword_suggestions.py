from __future__ import annotations
from collections import Counter

from pdfsorter_data import (
    DEFAULT_SETTINGS,
    _migrate_keyword_suggestions,
)
from pdfsorter_read import Candidate, suggest_keywords
from pdfsorter import ReviewDialog


def test_suggest_keywords_returns_up_to_25_terms_by_default():
    text = " ".join(f"vendorword{number:02d}" for number in range(35))

    candidates = suggest_keywords(text)

    assert DEFAULT_SETTINGS["keywords_per_file"] == 25
    assert len(candidates) == 25


def test_old_default_is_migrated_to_25_once():
    settings = {"keywords_per_file": 15}

    assert _migrate_keyword_suggestions(settings)
    assert settings["keywords_per_file"] == 25
    assert settings["keyword_suggestions_migrated_v1"] is True

    settings["keywords_per_file"] = 12
    assert not _migrate_keyword_suggestions(settings)
    assert settings["keywords_per_file"] == 12


def test_migration_preserves_a_custom_limit_above_15():
    settings = {"keywords_per_file": 30}

    assert _migrate_keyword_suggestions(settings)

    assert settings["keywords_per_file"] == 30
    assert settings["keyword_suggestions_migrated_v1"] is True


def test_review_suggestion_note_explains_type_and_exact_match_count():
    once = Candidate("invoice", "invoice", "word", 1, 1.0)
    several = Candidate("acme group", "ACME GROUP", "company", 4, 1.0)

    assert ReviewDialog._candidate_count_note(once) == "ord · 1 träff"
    assert ReviewDialog._candidate_count_note(several) == (
        "företagsnamn · 4 träffar")


def test_document_title_company_and_identifiers_rank_before_generic_words():
    text = """FAKTURA 2025-004
Exempelföretag AB
Org.nr 556016-0680
VAT SE556016068001
Bankgiro 123-4567
leveransvillkor information betalning"""

    candidates = suggest_keywords(text)
    kinds = [candidate.kind for candidate in candidates]
    important = ["title", "company", "orgnr", "vat", "giro"]

    assert [kind for kind in important if kind in kinds] == important
    assert kinds[0] == "title"
    assert kinds.index("company") < kinds.index("orgnr")
    assert [kinds.index(kind) for kind in important] == sorted(
        kinds.index(kind) for kind in important)
    prioritized = {"title", "company", "sender", "orgnr", "vat", "giro"}
    other_positions = [i for i, kind in enumerate(kinds)
                       if kind not in prioritized]
    assert not other_positions or max(kinds.index(kind) for kind in important) < min(
        other_positions)


def test_explicit_document_title_is_extracted_from_ocr_text():
    candidates = suggest_keywords(
        "Titel: Underhållsrapport för fastighet\nOrg.nr 556016-0680")

    assert candidates[0].kind == "title"
    assert candidates[0].text == "underhållsrapport för fastighet"


def test_priority_is_independent_of_frequency_or_existing_keyword_score():
    text = """Faktura
Nordisk Exempel AB
Org.nr 556016-0680
VAT SE556016068001
Bankgiro 123-4567
""" + " ofta förekommande ord" * 12

    candidates = suggest_keywords(text, existing=Counter({
        "faktura": 3,
        "nordisk exempel ab": 3,
        "556016-0680": 3,
        "se556016068001": 3,
        "123-4567": 3,
    }))
    kinds = [candidate.kind for candidate in candidates]

    important = ["title", "company", "orgnr", "vat", "giro"]
    assert kinds[0] == "title"
    assert [kinds.index(kind) for kind in important] == sorted(
        kinds.index(kind) for kind in important)
    prioritized = {"title", "company", "sender", "orgnr", "vat", "giro"}
    other_positions = [i for i, kind in enumerate(kinds)
                       if kind not in prioritized]
    assert not other_positions or max(kinds.index(kind) for kind in important) < min(
        other_positions)


def test_barcode_and_qr_strong_identities_are_parsed_and_ranked(
        tmp_path, monkeypatch):
    import pdfsorter as P
    import pdfsorter_read as R

    # 1. Payload parsing for Swedish invoice QR JSON, URL QR, and Code128/EAN
    tokens = R.parse_barcode_payloads([
        ("QRCODE", '{"uqr":1,"nme":"Nordisk Glas AB","cid":"556033-9086","iref":"INV-771"}'),
        ("QRCODE", "https://pay.nordiskglas.se/faktura/991"),
        ("EAN13", "7310865001818"),
    ])
    assert "556033-9086" in tokens
    assert "qr:556033-9086" in tokens
    assert "Nordisk Glas AB" in tokens
    assert "pay.nordiskglas.se" in tokens
    assert "7310865001818" in tokens
    assert "barcode:7310865001818" in tokens

    # 2. Extraction cache + scan_pdf_barcodes integration (even on scan-only PDFs)
    pdf_file = tmp_path / "qr_only.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n%%EOF\n")
    monkeypatch.setattr(R, "scan_pdf_barcodes",
                        lambda _p, max_pages=2: ["7310865001818", "barcode:7310865001818"])
    monkeypatch.setattr(R, "ocr_available", lambda: False)
    ext = R.extract(pdf_file)
    assert ext.error == ""
    assert "7310865001818" in ext.combined
    restored = R.Extraction.from_cache_dict(pdf_file, ext.to_cache_dict())
    assert restored.barcodes == ["7310865001818", "barcode:7310865001818"]

    # 3. suggest_keywords treats [QR/Streckkod] tokens as weight-3.0 strong IDs
    cands = suggest_keywords(ext.combined)
    by_text = {c.text: c for c in cands}
    assert by_text["barcode:7310865001818"].kind == "barcode"
    assert by_text["barcode:7310865001818"].label == "QR-/streckkod"
    assert R.KIND_INFO["barcode"][0] == 3.0

    # 4. Strong ID matching recognizes qr:/barcode: and GS1-valid EAN-13 only
    assert P.keyword_strength("qr:556033-9086") == "barcode"
    assert P.keyword_strength("barcode:INV-771") == "barcode"
    assert P.keyword_strength("7310865001818") == "barcode"  # valid EAN-13
    assert P.keyword_strength("7310865001819") == ""         # bad check digit
    assert P.keyword_strength("20251124") != "barcode"       # 8-digit date not barcode
    assert P.keyword_strength("202511") == ""                # plain short number not strong
