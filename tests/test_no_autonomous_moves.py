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


def test_apply_rejects_automatic_and_rescan_sources_without_moving(tmp_path):
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"unchanged")
    rules = Rules({"categories": [{"name": "Acme", "folder": "Acme"}]},
                  tmp_path / "rules.json")
    engine = P.SortEngine(rules, {"output_dir": str(tmp_path / "out")})

    for source_type in ("auto", "rescan"):
        ok, message = engine.apply(
            _decision(source), "Acme", [], decided_by=source_type)
        assert not ok
        assert "bekräft" in message.lower()
        assert source.exists()
        assert not (tmp_path / "out" / "Acme" / source.name).exists()


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


def test_watch_handler_queues_high_confidence_match_for_confirmation(tmp_path):
    source = tmp_path / "watched.pdf"
    source.write_bytes(b"keep in input")
    app = _bare_app()
    decision = _decision(source)

    P.App._handle(app, decision, from_watch=True)

    assert source.exists()
    assert len(app.queue) == 1
    assert app.queue[0].status == "ask"
    assert "bekräfta" in app.queue[0].reason.lower()


def test_rescan_only_queues_suggestions_and_never_applies(tmp_path):
    source = tmp_path / "learned-match.pdf"
    source.write_bytes(b"keep in input")

    class Engine:
        def analyze(self, path):
            return _decision(path)

        def apply(self, *_args, **_kwargs):
            raise AssertionError("rescan must never move files")

    app = _bare_app()
    app.engine = Engine()
    app.rules = Rules({"categories": []}, tmp_path / "rules.json")
    app._rescanning = True

    P.App._rescan_worker(app, [source], "Acme")

    assert source.exists()
    assert [d.path for d in app.queue] == [source]
    assert app.queue[0].status == "ask"


def test_learned_queue_refreshes_suggestion_without_moving_file(tmp_path, monkeypatch):
    source = tmp_path / "queued.pdf"
    source.write_bytes(b"review me")
    existing = P.Decision(source, P.Extraction(path=source), [], "ask")
    suggested = _decision(source, "auto")
    monkeypatch.setattr(P, "decide", lambda *_args: suggested)

    class Engine:
        def apply(self, *_args, **_kwargs):
            raise AssertionError("learning may suggest, not move")

    app = _bare_app()
    app.queue = [existing]
    app._queued_paths = {str(source)}
    app.rules = Rules({"categories": []}, tmp_path / "rules.json")
    app.engine = Engine()

    P.App._apply_rule_to_queue(app, 0)

    assert source.exists()
    assert app.queue[0] is suggested
    assert app.queue[0].status == "ask"
    assert "bekräfta" in app.queue[0].reason.lower()


def test_cli_no_ask_flag_still_leaves_suggested_file_in_input(tmp_path, monkeypatch,
                                                                capsys):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    source = incoming / "invoice.pdf"
    source.write_bytes(b"do not move")
    output = tmp_path / "archive"

    class Engine:
        stats = {"sorted": 0, "unmatched": 0, "left": 1, "error": 0}

        def __init__(self, *_args, **_kwargs):
            pass

        def analyze(self, path):
            return _decision(path)

        def apply(self, *_args, **_kwargs):
            raise AssertionError("CLI must not auto-apply a suggestion")

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
