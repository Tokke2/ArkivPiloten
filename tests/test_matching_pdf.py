# -*- coding: utf-8 -*-
"""Ände-till-ände: riktiga PDF-filer läses och matchas.

Testerna bygger små PDF:er med PyMuPDF, kör programmets egen
textutvinning och sedan decide(). Det är den enda delen av kedjan som
inte går att pröva med påhittade strängar, och den fångar sådant som
bara syns med verklig text: zoner, sidhuvud, mottagarblock och
organisationsnummer i olika skrivsätt.

Hoppas över om PyMuPDF saknas (t.ex. i en miljö utan läsaren) - appen
fungerar då ändå, men just det här testet behöver den.
"""
from __future__ import annotations

import pytest

pymupdf = pytest.importorskip("pymupdf")

import pdfsorter as P                     # noqa: E402
from pdfsorter_data import Rules          # noqa: E402
from pdfsorter_read import extract        # noqa: E402

#: Normalnivån i appen - den nivå de flesta kör med.
NORMAL = {"strictness": "normal", "learned_matching": False}

FILLER = (
    "Med vänlig hälsning\n"
    "Detta är en faktura avseende leverans av glas till byggprojektet.\n"
    "Betalningsvillkor 30 dagar. Dröjsmålsränta enligt lag.\n"
    "Fakturanummer 12345. Vår referens är Anna Andersson.\n"
)


def _pdf(path, lines):
    doc = pymupdf.open()
    page = doc.new_page()                 # A4, 595 x 842 punkter
    y = 60
    for line in lines:
        page.insert_text((60, y), line, fontsize=10)
        y += 16
    doc.save(str(path))
    doc.close()
    return path


def _rules(tmp_path, categories):
    data = {"categories": categories}
    return Rules(data, tmp_path / "rules.json")


def _decide(path, rules):
    ext = extract(path)
    assert not ext.error, ext.error
    return P.decide(rules, ext, NORMAL)


def test_invoice_with_orgnr_in_any_format_is_filed_automatically(tmp_path):
    """Samma organisation, fyra skrivsätt - alla ska ge samma beslut."""
    rules = _rules(tmp_path, [{
        "name": "Pilkington", "folder": "Pilkington",
        "keywords": [{"text": "556033-9086", "weight": 1.0}],
    }])
    # Fyra skrivsätt, inklusive "·" som en del typsnitt/OCR ger i
    # stället för bindestreck.
    for i, orgnr in enumerate(("556033-9086", "556033 9086",
                               "556033·9086", "5560339086")):
        path = _pdf(tmp_path / f"faktura{i}.pdf", [
            "Pilkington Sverige AB",
            "Glasgatan 1, 123 45 Stockholm",
            f"Org.nr {orgnr}  VAT SE556033908601",
            "Faktura",
            "Fakturanummer 4711",
            FILLER,
        ])
        d = _decide(path, rules)
        assert d.status == "auto", (orgnr, d.reason)
        assert d.best.name == "Pilkington"


def test_year_or_date_alone_never_files_a_document(tmp_path):
    """Ett årtal/datum var förut ett "starkt bevis" och kunde flytta filen."""
    rules = _rules(tmp_path, [{
        "name": "Projekt 2024", "folder": "Projekt 2024",
        "keywords": [{"text": "2024-01", "weight": 1.0}],
    }])
    path = _pdf(tmp_path / "datum.pdf", [
        "Faktura 2024-01",
        "Projektperiod januari 2024",
        FILLER,
    ])
    d = _decide(path, rules)
    assert d.status == "ask", d.reason
    assert "bevis" in d.reason.lower() or "stödord" in d.reason.lower()


def test_company_only_in_recipient_block_is_not_the_sender(tmp_path):
    rules = _rules(tmp_path, [{
        "name": "Pilkington", "folder": "Pilkington",
        "keywords": [{"text": "pilkington", "weight": 2.0}],
    }])
    path = _pdf(tmp_path / "kund.pdf", [
        "Glasmästeri Norden AB",
        "Faktura 778",
        "Kund: Pilkington Sverige AB",
        "Leveransadress: Glasgatan 1",
        FILLER,
    ])
    d = _decide(path, rules)
    assert d.status == "ask", d.reason
    assert d.best is not None and d.best.only_recipient


def test_year_is_not_reported_as_a_strong_evidence(tmp_path):
    """Samma sak på detaljnivå: årtalet får inte bli conclusive."""
    ext = extract(_pdf(tmp_path / "ar.pdf", ["Faktura 2025", FILLER]))
    scores = P.score_text(_rules(tmp_path, [{
        "name": "X", "folder": "X",
        "keywords": [{"text": "2025", "weight": 1.0}],
    }]), ext.combined, ext.path.name, ext.page_header, ext.page_footer)
    assert scores, "ordet finns i texten och ska ge poäng"
    assert not scores[0].has_strong
    assert not scores[0].is_conclusive


def test_correction_teaches_the_wrong_category_to_back_off(tmp_path):
    """Rättelse -> ordet väger mindre -> nästa liknande fil frågar i stället."""
    rules = _rules(tmp_path, [
        {"name": "Pilkington", "folder": "Pilkington",
         "keywords": [{"text": "glas", "weight": 1.0}]},
        {"name": "Annat", "folder": "Annat", "keywords": []},
    ])
    path = _pdf(tmp_path / "fel.pdf", ["Glas och glasmästeri", FILLER])
    före = _decide(path, rules)
    assert före.best is not None and före.best.name == "Pilkington"

    # Användaren rättar filen till "Annat" - då registreras avvisandet.
    rules.register_reject("Pilkington", före.best.matched)
    efter = _decide(path, rules)
    assert not efter.scores or efter.scores[0].score < före.best.score
