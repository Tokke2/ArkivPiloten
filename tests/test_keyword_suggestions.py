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
