from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pdfsorter as P
from pdfsorter_data import Rules


def _manual_events(category: str, count: int) -> list[dict[str, str]]:
    return [{"category": category, "decided_by": "user",
             "source": f"/inbox/manual-{index}.pdf"}
            for index in range(count)]


def _decision(path: Path, status: str = "auto") -> P.Decision:
    extraction = P.Extraction(path=path, text="Acme invoice")
    return P.Decision(
        path, extraction, [P.CategoryScore("Acme", 10.0)], status, "high score")


def test_learned_match_is_only_a_suggestion(monkeypatch, tmp_path):
    class LearnedModel:
        def predict(self, _features):
            return ("Acme", 0.99, 12)

    monkeypatch.setattr(P, "_learned", lambda: LearnedModel())
    monkeypatch.setattr(P, "learn_features", lambda _extraction: ["body:invoice"])
    rules = Rules({"categories": []}, tmp_path / "rules.json")
    extraction = P.Extraction(path=tmp_path / "unknown.pdf", text="invoice")

    decision = P.decide(rules, extraction, {"learned_matching": True})

    assert decision.status == "ask"
    assert decision.best is None
    assert decision.learned_hint == ("Acme", 12)


def test_shared_keywords_do_not_count_as_category_exclusive_exact_evidence(
        tmp_path):
    rules = Rules({"categories": [
        {"name": "Kontoutdrag", "folder": "Kontoutdrag", "keywords": [
            {"text": "Handelsbanken", "weight": 1.0},
            {"text": "kontoutdrag", "weight": 1.0},
            {"text": "saldo", "weight": 1.0},
        ]},
        {"name": "Lånebesked", "folder": "Lånebesked", "keywords": [
            {"text": "Handelsbanken", "weight": 1.0},
            {"text": "lånebesked", "weight": 1.0},
        ]},
    ]}, tmp_path / "rules.json")
    extraction = P.Extraction(
        path=tmp_path / "statement.pdf",
        text="Handelsbanken kontoutdrag saldo")

    assert P.exact_support_matches(rules, extraction) == {
        "Kontoutdrag": ["kontoutdrag", "saldo"]}


def test_manual_confirmation_count_is_distinct_and_category_specific():
    events = _manual_events("Acme", 2)
    events += [dict(events[0]), {"category": "Other", "decided_by": "user",
                                 "source": "/inbox/other.pdf"},
               {"category": "Acme", "decided_by": "auto",
                "source": "/inbox/automatic.pdf"}]

    assert P.manual_category_confirmations("Acme", events) == 2
    assert P.manual_category_confirmations("Other", events) == 1


def test_auto_requires_two_exclusive_words_and_100_manual_category_confirms(
        monkeypatch, tmp_path):
    rules = Rules({"categories": [{
        "name": "Acme", "folder": "Acme",
        "keywords": [{"text": "Acme", "weight": 1.0,
                      "whole_word": True, "source": "user"},
                     {"text": "invoice", "weight": 1.0,
                      "whole_word": True, "source": "user"}],
    }]}, tmp_path / "rules.json")

    monkeypatch.setattr(P, "load_history", lambda: _manual_events("Acme", 99))
    one_exact = P.decide(rules, P.Extraction(
        path=tmp_path / "one.pdf", text="ACME receipt"),
        {"learned_matching": False})
    under_threshold = P.decide(rules, P.Extraction(
        path=tmp_path / "under-threshold.pdf", text="ACME invoice"),
        {"learned_matching": False})
    assert under_threshold.status == "ask"
    assert "99/100" in under_threshold.reason

    monkeypatch.setattr(P, "load_history", lambda: _manual_events("Acme", 100))
    both_exact = P.decide(rules, P.Extraction(
        path=tmp_path / "exact.pdf", text="ACME invoice"),
        {"learned_matching": False})
    embedded = P.decide(rules, P.Extraction(
        path=tmp_path / "embedded.pdf", text="XAcmeZ invoice"),
        {"learned_matching": False})

    assert one_exact.status == "ask"
    assert both_exact.status == "auto"
    assert both_exact.best.name == "Acme"
    assert embedded.status == "ask"


def test_apply_rejects_forged_auto_with_only_one_exact_support_word(tmp_path):
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"unchanged")
    rules = Rules({"categories": [{
        "name": "Acme", "folder": "Acme",
        "keywords": [{"text": "Acme", "weight": 1.0}],
    }]}, tmp_path / "rules.json")
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "out"), "year_subfolder": False,
    })
    forged = _decision(source, "auto")

    ok, message = engine.apply(forged, "Acme", ["Acme"], decided_by="auto")

    assert not ok
    assert "minst två" in message.lower()
    assert source.exists()
    assert not (tmp_path / "out" / "Acme" / source.name).exists()


def test_apply_rejects_forged_auto_before_100_manual_confirms(
        monkeypatch, tmp_path):
    monkeypatch.setattr(P, "load_history", lambda: _manual_events("Acme", 99))
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"unchanged")
    rules = Rules({"categories": [{
        "name": "Acme", "folder": "Acme",
        "keywords": [{"text": "Acme", "weight": 1.0},
                     {"text": "invoice", "weight": 1.0}],
    }]}, tmp_path / "rules.json")
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "out"), "year_subfolder": False,
    })
    decision = P.Decision(
        source, P.Extraction(path=source, text="Acme invoice"),
        [P.CategoryScore("Acme", 10.0)], "auto")

    ok, message = engine.apply(decision, "Acme", ["Acme", "invoice"],
                               decided_by="auto")

    assert not ok
    assert "hundra" in message.lower()
    assert source.exists()


def test_filename_only_support_match_requires_review(tmp_path):
    rules = Rules({"categories": [{
        "name": "Acme", "folder": "Acme",
        "keywords": [{"text": "Acme", "weight": 1.0}],
    }]}, tmp_path / "rules.json")
    decision = P.decide(rules, P.Extraction(
        path=tmp_path / "Acme-invoice.pdf", text="Invoice"),
        {"learned_matching": False})
    assert decision.status == "ask"


def test_rejected_exact_support_word_requires_review(tmp_path):
    rules = Rules({"categories": [{
        "name": "Acme", "folder": "Acme",
        "keywords": [{"text": "Acme", "weight": 1.0, "rejected": 1}],
    }]}, tmp_path / "rules.json")
    decision = P.decide(rules, P.Extraction(
        path=tmp_path / "corrected.pdf", text="Acme invoice"),
        {"learned_matching": False})
    assert decision.status == "ask"


def test_same_exact_keyword_in_two_categories_requires_review(tmp_path):
    rules = Rules({"categories": [
        {"name": "Acme", "folder": "Acme",
         "keywords": [{"text": "Acme", "weight": 1.0}]},
        {"name": "Acme archive", "folder": "Acme archive",
         "keywords": [{"text": "Acme", "weight": 1.0}]},
    ]}, tmp_path / "rules.json")
    decision = P.decide(rules, P.Extraction(
        path=tmp_path / "ambiguous.pdf", text="Acme invoice"),
        {"learned_matching": False})
    assert decision.status == "ask"


def test_apply_rejects_automatic_and_rescan_without_exact_rule(tmp_path):
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"unchanged")
    rules = Rules({"categories": [{"name": "Acme", "folder": "Acme"}]},
                  tmp_path / "rules.json")
    engine = P.SortEngine(rules, {"output_dir": str(tmp_path / "out")})

    for source_type in ("auto", "rescan"):
        ok, message = engine.apply(
            _decision(source), "Acme", [], decided_by=source_type)
        assert not ok
        assert "exakt" in message.lower()
        assert source.exists()
        assert not (tmp_path / "out" / "Acme" / source.name).exists()


def test_exact_support_match_can_move_during_rescan(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "load_history", lambda: _manual_events("Acme", 100))
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"unchanged")
    rules = Rules({"categories": [{
        "name": "Acme", "folder": "Acme",
        "keywords": [{"text": "Acme", "weight": 1.0},
                     {"text": "invoice", "weight": 1.0}],
    }]}, tmp_path / "rules.json")
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "out"), "year_subfolder": False,
        "date_enabled": False,
    })
    decision = P.decide(rules, P.Extraction(
        path=source, text="Acme invoice"), {"learned_matching": False})

    ok, _ = engine.apply(decision, "Acme", decision.best.matched,
                         decided_by="rescan")

    assert ok
    assert not source.exists()
    assert (tmp_path / "out" / "Acme" / "invoice.pdf").exists()


def test_clear_all_support_words_preserves_categories(tmp_path):
    rules = Rules({"categories": [
        {"name": "Acme", "folder": "Acme",
         "keywords": [{"text": "Acme", "weight": 1.0}]},
        {"name": "Other", "folder": "Other",
         "keywords": [{"text": "Other", "weight": 1.0}]},
    ]}, tmp_path / "rules.json")
    app = P.App.__new__(P.App)
    app.rules = rules
    app.root = object()
    app.messagebox = type("MessageBox", (), {
        "askyesno": staticmethod(lambda *_args, **_kwargs: True),
    })
    app._refresh_categories = lambda: None
    app._log = lambda *_args, **_kwargs: None

    P.App._kw_clear_all(app)

    assert rules.names() == ["Acme", "Other"]
    assert all(not cat["keywords"] for cat in rules.categories)


def test_rescan_worker_moves_exact_support_match(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "load_history", lambda: _manual_events("Acme", 100))
    source = tmp_path / "learned-exact.pdf"
    source.write_bytes(b"matching content")
    rules = Rules({"categories": [{
        "name": "Acme", "folder": "Acme",
        "keywords": [{"text": "Acme", "weight": 1.0},
                     {"text": "invoice", "weight": 1.0}],
    }]}, tmp_path / "rules.json")
    real_engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "out"), "year_subfolder": False,
        "date_enabled": False,
    })

    class Engine:
        def analyze(self, path):
            return P.decide(rules, P.Extraction(
                path=path, text="Acme invoice"), {"learned_matching": False})

        def apply(self, *args, **kwargs):
            return real_engine.apply(*args, **kwargs)

        def flush_rules(self):
            return None

    monkeypatch.setattr(P, "append_history", lambda _event: None)
    monkeypatch.setattr(P, "json_dir", lambda: tmp_path / "app-json")
    app = _bare_app()
    app.engine = Engine()
    app.rules = rules
    app._rescanning = True

    P.App._rescan_worker(app, [source], "Acme")

    assert not source.exists()
    assert (tmp_path / "out" / "Acme" / source.name).exists()


def test_subfolder_override_is_relative_and_traversal_is_rejected(tmp_path):
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"unchanged")
    rules = Rules({"categories": [{"name": "Acme", "folder": "Acme"}]},
                  tmp_path / "rules.json")
    engine = P.SortEngine(rules, {
        "output_dir": str(tmp_path / "out"), "year_subfolder": False,
        "date_enabled": False,
    })
    decision = P.Decision(source, P.Extraction(path=source), [], "ask")

    ok, _ = engine.apply(decision, "Acme", [], decided_by="user",
                         subfolder_override="Reviewed/2025")

    assert ok
    assert (tmp_path / "out" / "Acme" / "Reviewed" / "2025" / "invoice.pdf").exists()
    assert P.validate_subfolder_override("../escape")[1]
    assert P.validate_subfolder_override("C:\\outside")[1]


def _bare_app() -> P.App:
    app = P.App.__new__(P.App)
    app.settings = {"ask_when_unsure": False}
    app.queue = []
    app._queued_paths = set()
    app.visible = False
    app.watcher = None
    app._post = lambda callback: None
    app._log_threadsafe = lambda *_args, **_kwargs: None
    app._refresh_queue = lambda: None
    app._sync_tray = lambda: None
    return app


class _RejectInexactEngine:
    def apply(self, *_args, **_kwargs):
        return False, "Automatisk flyttning kräver en exakt stödordsträff."


def test_watch_handler_queues_non_exact_match_for_review(tmp_path):
    source = tmp_path / "watched.pdf"
    source.write_bytes(b"keep in input")
    app = _bare_app()
    app.engine = _RejectInexactEngine()
    decision = _decision(source)

    P.App._handle(app, decision, from_watch=True)

    assert source.exists()
    assert len(app.queue) == 1
    assert app.queue[0].status == "ask"
    assert "exakt" in app.queue[0].reason.lower()


def test_rescan_queues_inexact_auto_decision_after_apply_rejects(tmp_path):
    source = tmp_path / "learned-match.pdf"
    source.write_bytes(b"keep in input")

    class Engine(_RejectInexactEngine):
        def analyze(self, path):
            return _decision(path)

    app = _bare_app()
    app.engine = Engine()
    app.rules = Rules({"categories": []}, tmp_path / "rules.json")
    app._rescanning = True

    P.App._rescan_worker(app, [source], "Acme")

    assert source.exists()
    assert [d.path for d in app.queue] == [source]
    assert app.queue[0].status == "ask"


def test_learned_queue_refreshes_suggestion_and_keeps_inexact_file(tmp_path,
                                                                   monkeypatch):
    source = tmp_path / "queued.pdf"
    source.write_bytes(b"review me")
    existing = P.Decision(source, P.Extraction(path=source), [], "ask")
    suggested = _decision(source, "auto")
    monkeypatch.setattr(P, "decide", lambda *_args: suggested)

    app = _bare_app()
    app.queue = [existing]
    app._queued_paths = {str(source)}
    app.rules = Rules({"categories": []}, tmp_path / "rules.json")
    app.engine = _RejectInexactEngine()

    P.App._apply_rule_to_queue(app, 0)

    assert source.exists()
    assert app.queue[0] is suggested
    assert app.queue[0].status == "ask"
    assert "exakt" in app.queue[0].reason.lower()


def test_cli_no_ask_flag_still_checks_exact_support_match(tmp_path, monkeypatch,
                                                          capsys):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    source = incoming / "invoice.pdf"
    source.write_bytes(b"do not move")
    output = tmp_path / "archive"

    class Engine(_RejectInexactEngine):
        stats = {"sorted": 0, "unmatched": 0, "left": 1, "error": 0}

        def __init__(self, *_args, **_kwargs):
            pass

        def analyze(self, path):
            return _decision(path)

    monkeypatch.setattr(P, "load_settings", lambda: {
        "input_dir": str(incoming), "output_dir": str(output),
        "ask_when_unsure": False,
    })
    monkeypatch.setattr(P.Rules, "load", lambda *_args, **_kwargs:
                        Rules({"categories": []}, tmp_path / "rules.json"))
    monkeypatch.setattr(P, "SortEngine", Engine)
    monkeypatch.setattr(P, "flush_learned", lambda: None)
    monkeypatch.setattr(P, "session_log", lambda *_args, **_kwargs: None)

    result = P.run_cli(argparse.Namespace(
        input=None, output=None, rules=None, no_ask=True, dry_run=False,
        copy=False, exclude=None, json=True, watch=False, verbose=False))

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert source.exists()
    assert not (output / "Acme" / source.name).exists()
    assert payload["results"][0]["needs_review"] is True
    assert payload["results"][0]["category"] == "Acme"
