from __future__ import annotations

from datetime import date
from pathlib import Path

import pdfsorter as P
from pdfsorter_read import Extraction


CATEGORY = "Handelsbanken"


def _history_events(transactions: int = 5, payouts: int = 5):
    events = []
    types = (
        ("Transaktioner", transactions,
         "Handelsbanken Kontoinformation Transaktioner Inbetalning Kontonummer saldo"),
        ("Utbetalningar", payouts,
         "Handelsbanken Utbetalningar Sok utbetalning Mottagarnamn mottagarkonto status"),
    )
    index = 0
    for label, count, text in types:
        for _ in range(count):
            path = Path(f"/manual/handelsbanken-{index}.pdf")
            extraction = Extraction(path=path, text=text)
            events.append({
                "category": CATEGORY,
                "decided_by": "user",
                "source": str(path),
                "subfolder_choice": label,
                "features": P.learn_features(extraction),
            })
            index += 1
    return events


def test_manual_subfolder_learning_needs_five_examples_per_type():
    events = _history_events(transactions=5, payouts=4)
    extraction = Extraction(
        path=Path("/new/payout.pdf"),
        text="Handelsbanken Utbetalningar Sok utbetalning Mottagarnamn mottagarkonto status")

    folder, has_examples = P.learned_manual_subfolder(CATEGORY, extraction, events)

    assert has_examples
    assert folder == ""


def test_manual_subfolder_learning_sorts_known_types_and_asks_if_unsure():
    events = _history_events()
    payout = Extraction(
        path=Path("/new/payout.pdf"),
        text="Handelsbanken Utbetalningar Sok utbetalning Mottagarnamn mottagarkonto status")
    unclear = Extraction(path=Path("/new/unclear.pdf"),
                         text="Handelsbanken dokument")

    folder, has_examples = P.learned_manual_subfolder(CATEGORY, payout, events)
    unclear_folder, unclear_has_examples = P.learned_manual_subfolder(
        CATEGORY, unclear, events)

    assert has_examples
    assert folder == "Utbetalningar"
    assert unclear_has_examples
    assert unclear_folder == ""


def test_automatic_sort_uses_confident_manual_subfolder_label(
        monkeypatch, tmp_path):
    source = tmp_path / "payout.pdf"
    source.write_bytes(b"document bytes")
    events = _history_events()
    for index in range(90):
        events.append({
            "category": CATEGORY,
            "decided_by": "user",
            "source": f"/manual/other-{index}.pdf",
            "features": ["generic", "confirmed"],
        })
    monkeypatch.setattr(P, "load_history", lambda: events)
    monkeypatch.setattr(P, "exact_auto_category", lambda *_args: CATEGORY)
    monkeypatch.setattr(P, "append_history", lambda _event: None)
    rules = P.Rules({"categories": [{
        "name": CATEGORY, "folder": CATEGORY, "subfolder": "{år}",
    }]}, tmp_path / "rules.json")
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "out"), "year_subfolder": True,
        "date_enabled": True,
    })
    extraction = Extraction(
        path=source, doc_date=date(2025, 3, 14),
        text="Handelsbanken Utbetalningar Sok utbetalning Mottagarnamn mottagarkonto status")
    decision = P.Decision(
        source, extraction, [P.CategoryScore(CATEGORY, 10.0)], "auto")

    ok, result = engine.apply(decision, CATEGORY, [], decided_by="auto")

    assert ok, result
    assert (tmp_path / "out" / CATEGORY / "2025" / "Utbetalningar"
            / "payout.pdf").exists()


def test_automatic_sort_reviews_if_subfolder_type_is_uncertain(
        monkeypatch, tmp_path):
    source = tmp_path / "unclear.pdf"
    source.write_bytes(b"document bytes")
    events = _history_events()
    events.extend({"category": CATEGORY, "decided_by": "user",
                   "source": f"/manual/other-{index}.pdf",
                   "features": ["generic", "confirmed"]}
                  for index in range(90))
    monkeypatch.setattr(P, "load_history", lambda: events)
    monkeypatch.setattr(P, "exact_auto_category", lambda *_args: CATEGORY)
    rules = P.Rules({"categories": [{"name": CATEGORY, "folder": CATEGORY}]},
                    tmp_path / "rules.json")
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "out"), "year_subfolder": False,
        "date_enabled": False,
    })
    extraction = Extraction(path=source, text="Handelsbanken dokument")
    decision = P.Decision(
        source, extraction, [P.CategoryScore(CATEGORY, 10.0)], "auto")

    ok, message = engine.apply(decision, CATEGORY, [], decided_by="auto")

    assert not ok
    assert "dokumenttypen" in message.lower()
    assert source.exists()


def test_manual_subfolder_choice_is_recorded_for_future_learning(
        monkeypatch, tmp_path):
    source = tmp_path / "transactions.pdf"
    source.write_bytes(b"document bytes")
    captured = []
    monkeypatch.setattr(P, "append_history", captured.append)
    monkeypatch.setattr(P, "_learned", lambda: P.LearnedMatcher(load=False))
    rules = P.Rules({"categories": [{"name": CATEGORY, "folder": CATEGORY}]},
                    tmp_path / "rules.json")
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "out"), "year_subfolder": False,
        "date_enabled": False,
    })
    extraction = Extraction(
        path=source,
        text="Handelsbanken Kontoinformation Transaktioner Inbetalning Kontonummer saldo")
    decision = P.Decision(source, extraction,
                          [P.CategoryScore(CATEGORY, 2.0)], "ask")

    ok, result = engine.apply(
        decision, CATEGORY, [], decided_by="user",
        subfolder_override="Transaktioner")

    assert ok, result
    assert captured[0]["subfolder_choice"] == "Transaktioner"
    assert captured[0]["decided_by"] == "user"


def test_subfolder_training_ignores_automatic_sorts():
    events = _history_events(transactions=5, payouts=0)
    for index in range(5):
        events.append({
            "category": CATEGORY,
            "decided_by": "auto",
            "source": f"/auto/{index}.pdf",
            "subfolder_choice": "Utbetalningar",
            "features": ["utbetalningar", "betalning"],
        })
    extraction = Extraction(path=Path("/new/doc.pdf"),
                            text="Handelsbanken Utbetalningar Sok utbetalning")

    folder, has_examples = P.learned_manual_subfolder(CATEGORY, extraction, events)

    assert has_examples
    assert folder == ""
