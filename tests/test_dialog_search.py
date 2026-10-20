# -*- coding: utf-8 -*-
"""Sökbar kategori-rullgardin i granskningsdialogen.

Testar den rena sök-/tolkningslogiken (Tk krävs inte i testmiljön):
filtrering med början-först, skiftläge/diacritik och att en ofullständig
söksträng bara får bli en kategori när den pekar ut exakt en träff.
"""
from __future__ import annotations

import pdfsorter


NAMES = [
    "Pilkington", "CALL", "CASE OF FIRE", "EVACUATE",
    "FARA RÅDA", "PARKERINGEN AYGSINN", "RESCUE",
    "Utrymningsplan", "Utrymningsplan 2",
]


def test_empty_query_returns_everything_in_order():
    assert pdfsorter._filter_categories("", NAMES) == NAMES
    assert pdfsorter._filter_categories("   ", NAMES) == NAMES


def test_filters_by_substring_and_is_case_insensitive():
    träffar = pdfsorter._filter_categories("utrym", NAMES)
    assert träffar == ["Utrymningsplan", "Utrymningsplan 2"]
    assert pdfsorter._filter_categories("UTRYM", NAMES) == träffar


def test_diacritics_are_ignored():
    assert pdfsorter._filter_categories("fara rada", NAMES) == ["FARA RÅDA"]
    assert pdfsorter._filter_categories("råda", NAMES) == ["FARA RÅDA"]


def test_prefix_matches_come_before_substring_matches():
    names = ["Min Faktura", "Faktura", "Fakturering", "Annan"]
    träffar = pdfsorter._filter_categories("faktur", names)
    assert träffar == ["Faktura", "Fakturering", "Min Faktura"]


def test_resolve_exact_name():
    assert pdfsorter._resolve_category_name("Utrymningsplan", NAMES) == \
        "Utrymningsplan"


def test_resolve_unique_prefix():
    assert pdfsorter._resolve_category_name("Pilking", NAMES) == "Pilkington"
    assert pdfsorter._resolve_category_name("evac", NAMES) == "EVACUATE"


def test_resolve_unique_substring():
    assert pdfsorter._resolve_category_name("aygsinn", NAMES) == \
        "PARKERINGEN AYGSINN"


def test_ambiguous_query_is_not_guessed():
    # En ofullständig sträng som matchar två kategorier -> ingen gissning.
    assert pdfsorter._resolve_category_name(
        "utrymningspla", ["Utrymningsplan", "Utrymningsplan 2"]) == ""
    assert pdfsorter._resolve_category_name("utrymningsplan", []) == ""
    # ...men ett exakt namn vinner alltid, även när det är en delmängd.
    assert pdfsorter._resolve_category_name(
        "Utrymningsplan", ["Utrymningsplan 2", "Utrymningsplan"]) == \
        "Utrymningsplan"


def test_unknown_name_is_not_resolved():
    assert pdfsorter._resolve_category_name("Helt Ny Mapp", NAMES) == ""
    assert pdfsorter._resolve_category_name("", NAMES) == ""
