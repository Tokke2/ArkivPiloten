from pathlib import Path

import pdfsorter as P


def test_extract_invoice_identity_parses_swedish_number_and_amount():
    identity = P.extract_invoice_identity(
        "Fakturanummer: INV-2026/0042\nSumma att betala: 1 234,50 SEK",
        "Acme AB")

    assert identity == {
        "supplier": "acme ab",
        "invoice_number": "inv20260042",
        "amount_minor": 123450,
        "currency": "SEK",
    }


def test_extract_invoice_identity_supports_english_currency_and_number_labels():
    identity = P.extract_invoice_identity(
        "Invoice No. ABC-7788\nAmount due: EUR 2.345,67", "Example Ltd")

    assert identity == {
        "supplier": "example ltd",
        "invoice_number": "abc7788",
        "amount_minor": 234567,
        "currency": "EUR",
    }


def test_amount_parser_accepts_us_thousands_and_decimal_separators():
    assert P._invoice_amount_minor("1,234.56") == 123456
    assert P._invoice_amount_minor("1.234,56") == 123456
    assert P._invoice_amount_minor("1 234,56") == 123456


def test_duplicate_requires_supplier_invoice_number_amount_and_currency():
    current = P.extract_invoice_identity(
        "Fakturanr: INV-99\nAtt betala 500,00 kr", "Acme")
    same = P.extract_invoice_identity(
        "Fakturanummer INV 99\nSumma att betala 500,00 SEK", "ACME")
    different_supplier = dict(same, supplier="Other")
    different_amount = dict(same, amount_minor=50001)
    different_currency = dict(same, currency="EUR")

    assert P.invoice_identity_matches(current, same)
    assert not P.invoice_identity_matches(current, different_supplier)
    assert not P.invoice_identity_matches(current, different_amount)
    assert not P.invoice_identity_matches(current, different_currency)
    assert not P.invoice_identity_matches(current, dict(same, amount_minor="bad"))


def test_invoice_match_needs_explicit_invoice_number_and_payable_total():
    assert P.extract_invoice_identity(
        "Order number: 123456\nTotal: 500,00 SEK", "Acme") is None
    assert P.extract_invoice_identity(
        "Invoice number: ABC-123\nSubtotal: 500,00 SEK", "Acme") is None


def test_analyze_routes_a_probable_duplicate_to_review_not_auto_move(
        monkeypatch, tmp_path):
    output = tmp_path / "archive"
    existing = output / "Acme" / "2025" / "old.pdf"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"archived")
    incoming = tmp_path / "inbox" / "copy.pdf"
    incoming.parent.mkdir()
    incoming.write_bytes(b"incoming")
    monkeypatch.setattr(P, "json_dir", lambda: tmp_path / "config")
    text = "Fakturanummer: INV-2026-42\nSumma att betala: 1 234,50 SEK"
    monkeypatch.setattr(
        P, "read_pdf",
        lambda path, _settings: P.Extraction(path=Path(path), text=text))
    rules = P.Rules({"categories": [{"name": "Acme", "folder": "Acme",
                                     "keywords": []}]},
                    tmp_path / "rules.json")
    monkeypatch.setattr(
        P, "decide",
        lambda _rules, extraction, _settings: P.Decision(
            extraction.path, extraction, [P.CategoryScore("Acme", 10.0)], "auto"))
    engine = P.SortEngine(rules, {"output_dir": str(output)})

    decision = engine.analyze(incoming)

    assert decision.status == "ask"
    assert decision.invoice_duplicate["path"] == str(existing)


def test_engine_finds_existing_archive_invoice_and_returns_path(
        monkeypatch, tmp_path):
    output = tmp_path / "archive"
    existing = output / "Acme" / "2025" / "old.pdf"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"test")
    monkeypatch.setattr(P, "json_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(
        P, "read_pdf",
        lambda path, _settings: P.Extraction(
            path=Path(path), text=(
                "Fakturanummer: INV-2026-42\n"
                "Summa att betala: 1 234,50 SEK")))
    rules = P.Rules({"categories": [{"name": "Acme", "folder": "Acme",
                                     "keywords": []}]},
                    tmp_path / "rules.json")
    current = P.Extraction(
        path=tmp_path / "inbox" / "copy.pdf",
        text="Fakturanummer: INV-2026-42\nSumma att betala: 1 234,50 SEK")
    decision = P.Decision(
        current.path, current, [P.CategoryScore("Acme", 10.0)], "ask")
    engine = P.SortEngine(rules, {"output_dir": str(output)})

    duplicate = engine._find_invoice_duplicate(decision)

    assert duplicate is not None
    assert duplicate["path"] == str(existing)
    assert duplicate["invoice_number"] == "inv202642"
    assert duplicate["amount_minor"] == 123450
