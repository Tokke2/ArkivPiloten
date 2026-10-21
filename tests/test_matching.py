# -*- coding: utf-8 -*-
"""Matchningsmotorn: starka bevis, identifierarformat och negativ inlärning.

Tre saker prövas, alla utan Tkinter:

1. Bara riktiga identifierare får räknas som starka bevis. Årtal, datum,
   belopp och versionsnummer är vardagsmat och får aldrig kringgå
   beviskraven i _auto_blocker.
2. Samma nummer matchar oavsett skiljetecken - "556033-9086",
   "556033 9086", "5560339086" och "556033–9086" är samma organisation.
3. Ett stödord som lett fel väger mindre nästa gång, och den lärda
   klassificeraren får negativa bevis av användarens korrigeringar.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import pdfsorter as P
from pdfsorter_data import Rules


def _rules(tmp_path, words, name="Pilkington"):
    data = {"categories": [{
        "name": name, "folder": name,
        "keywords": [{"text": w, "weight": 1.0} for w in words],
    }]}
    return Rules(data, tmp_path / "rules.json")


# -- 1. starka bevis -------------------------------------------------------
def test_years_dates_amounts_and_versions_are_not_strong():
    for text in ("2025", "2024", "2024-01", "24.10.2025", "1.234",
                 "123456", "v1.4.4", "2025:12"):
        assert P.keyword_strength(text) == "", text


def test_real_identifiers_are_still_strong():
    assert P.keyword_strength("556033-9086") == "orgnr"
    assert P.keyword_strength("556033 9086") == "orgnr"
    assert P.keyword_strength("SE556033908601") == "vat"
    assert P.keyword_strength("031-1234") == "giro"
    assert P.keyword_strength("pilkington.se") == "domain"
    assert P.keyword_strength("www.pilkington.co.uk") == "domain"
    assert P.keyword_strength("IF26") == "kod"
    assert P.keyword_strength("AB-1200") == "kod"


def test_ten_digits_with_bad_checksum_is_not_strong():
    # Fel kontrollsiffra = kundnummer, inte avsändarbevis (REQ-C1 AC-1.2).
    assert P.keyword_strength("556033-9087") == ""


# -- 2. samma identifierare i alla format ----------------------------------
def test_orgnr_matches_every_separator_style():
    pat = P._cached_pattern({"text": "556033-9086", "whole_word": True})
    for text in ("556033-9086", "556033 9086", "5560339086", "556033–9086"):
        assert pat.search(P.normalize(text)), text


def test_orgnr_written_without_separator_matches_dashed_text():
    pat = P._cached_pattern({"text": "5560339086", "whole_word": True})
    assert pat.search("556033-9086")
    assert pat.search("556033 9086")


def test_flexible_identifier_keeps_word_boundaries():
    pat = P._cached_pattern({"text": "556033-9086", "whole_word": True})
    assert not pat.search("9556033-9086")
    assert not pat.search("556033-90860")


def test_vat_matches_spaced_and_compact_forms():
    pat = P._cached_pattern({"text": "SE556033908601", "whole_word": True})
    assert pat.search(P.normalize("se 556033 9086 01"))
    assert pat.search(P.normalize("SE556033908601"))


def test_ordinary_words_are_not_flexible():
    assert not P._is_flexible("pilkington")
    assert not P._is_flexible("saint-gobain")
    assert not P._is_flexible("utrymningsplan")


def test_middle_dot_is_accepted_as_separator():
    # En del typsnitt och OCR ger "·" i stället för bindestreck.
    pat = P._cached_pattern({"text": "556033-9086", "whole_word": True})
    assert pat.search(P.normalize("556033·9086"))
    assert pat.search(P.normalize("556033•9086"))
    assert P.keyword_strength("556033·9086") == "orgnr"


def test_domain_keeps_its_dot():
    # En domän får inte bli flexibel - då kunde "Pilkington se bilaga"
    # matcha "pilkington.se".
    assert not P._is_flexible("pilkington.se")
    pat = P._cached_pattern({"text": "pilkington.se", "whole_word": True})
    assert not pat.search(P.normalize("Pilkington se bilaga"))
    assert pat.search(P.normalize("se www.pilkington.se")[3:])


def test_score_text_matches_orgnr_in_the_identity_zone(tmp_path):
    rules = _rules(tmp_path, ["556033-9086"])
    text = "Pilkington Sverige AB\nOrg.nr 556033 9086\nFaktura 123"
    scores = P.score_text(rules, text)
    assert scores and scores[0].name == "Pilkington"
    assert scores[0].matched == ["556033-9086"]
    assert scores[0].anchored          # står på en rad med org.nr


# -- 3. negativ inlärning --------------------------------------------------
def _recent(rejected):
    return {"text": "x", "rejected": rejected,
            "rejected_at": datetime.now().astimezone().isoformat()}


def test_reject_factor_lowers_weight_and_floors_at_zero():
    assert P._reject_factor({"text": "x"}) == 1.0
    assert P._reject_factor(_recent(1)) == pytest.approx(0.8, abs=1e-6)
    assert P._reject_factor(_recent(5)) < 1e-6


def test_reject_factor_forgets_old_rejections():
    old = {"text": "x", "rejected": 4,
           "rejected_at": (datetime.now().astimezone()
                           - timedelta(days=365)).isoformat()}
    # Ett år gammalt avvisande väger hälften så tungt -> faktorn 0,6.
    assert P._reject_factor(old) == pytest.approx(0.6, abs=0.02)


def test_rejected_keyword_stops_scoring(tmp_path):
    rules = _rules(tmp_path, ["556033-9086"])
    text = "Pilkington Sverige AB\nOrg.nr 556033 9086\nFaktura 123"
    kw = rules.get("Pilkington")["keywords"][0]
    kw["rejected"] = 5
    kw["rejected_at"] = datetime.now().astimezone().isoformat()
    assert P.score_text(rules, text) == []


def test_register_reject_survives_save_and_load(tmp_path):
    rules = _rules(tmp_path, ["pilkington", "556033-9086"])
    rules.register_reject("Pilkington", ["556033-9086"])
    rules.save()
    back = Rules.load(tmp_path / "rules.json")
    kw = next(k for k in back.get("Pilkington")["keywords"]
              if k["text"] == "556033-9086")
    assert kw["rejected"] == 1
    assert kw["rejected_at"]
    # Det ord som inte ledde fel är orört.
    annat = next(k for k in back.get("Pilkington")["keywords"]
                 if k["text"] == "pilkington")
    assert "rejected" not in annat


def test_correction_trains_the_wrong_category_negatively(tmp_path):
    lm = P.LearnedMatcher(tmp_path / "learned.json")
    for _ in range(6):
        lm.train("A", ["glas", "faktura"])
        lm.train("B", ["glas", "faktura"])
    assert lm.predict(["glas", "faktura"])[0] == "A"
    for _ in range(3):
        lm.train("B", ["glas"], rejected_for="A")
    vinnare, marginal, _n = lm.predict(["glas", "faktura"])
    assert vinnare == "B" and marginal > 0
    assert lm.cats["A"]["neg"]["glas"] == 3


def test_learned_bonus_can_move_a_close_race():
    scores = [P.CategoryScore("A", 2.0, ["x"], {"x": "body"}),
              P.CategoryScore("B", 1.95, ["y"], {"y": "body"})]
    P._apply_learned_ranking(scores, ("B", 0.9, 10))
    assert scores[0].name == "B"
    assert scores[0].bonus == P._LEARNED_BONUS


def test_learned_bonus_never_lowers_proved_evidence():
    scores = [P.CategoryScore("A", 2.0, ["556033-9086"],
                              {"556033-9086": "identity"}),
              P.CategoryScore("B", 1.9, ["pilkington"],
                              {"pilkington": "body"})]
    P._apply_learned_ranking(scores, ("B", 0.9, 10))
    assert scores[0].name == "A"
    assert scores[1].bonus == 0.0


def test_learned_bonus_requires_confidence_and_a_known_category():
    scores = [P.CategoryScore("A", 2.0), P.CategoryScore("B", 1.9)]
    P._apply_learned_ranking(scores, ("B", 0.05, 10))      # osäker modell
    assert scores[0].name == "A" and scores[0].bonus == 0.0
    P._apply_learned_ranking(scores, ("C", 0.9, 10))       # okänd kategori
    assert scores[0].name == "A" and scores[0].bonus == 0.0
