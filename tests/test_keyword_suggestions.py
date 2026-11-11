from __future__ import annotations

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
