from pathlib import Path
from types import SimpleNamespace

import pytest

import pdfsorter as P
from pdfsorter_data import Rules


def _pdf(path: Path, text="Horsetools faktura") -> Path:
    fitz = pytest.importorskip("fitz")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((48, 60), text, fontsize=12)
    doc.save(path)
    doc.close()
    return path


def _app(tmp_path, source, *, status="auto", monkeypatch=None):
    output = tmp_path / "Arkiv"
    rules = Rules({"categories": [
        {"name": "Fel mapp", "folder": "Fel mapp"},
        {
            "name": "HorseTools Sweden AB",
            "folder": "HorseTools Sweden AB",
            "keywords": ["Horsetools", "faktura"],
            "default_keyword": "horsetools",
            "subfolder_keyword_map": {"faktura": "Faktura"},
        },
    ]}, tmp_path / "rules.json")
    extraction = P.read_pdf(source, {})
    decision = P.Decision(
        source, extraction,
        [P.CategoryScore("HorseTools Sweden AB", 10)], status)
    engine = P.SortEngine(rules, {
        "output_dir": str(output), "year_subfolder": False,
        "date_enabled": False, "tag_pdf_metadata": False, "action": "move",
    })
    engine.analyze = lambda _path: decision
    engine._remember_content_file = lambda *_args, **_kwargs: None

    app = P.App.__new__(P.App)
    app.settings = {"output_dir": str(output), "action": "move",
                   "dry_run": False}
    app.rules = rules
    app.engine = engine
    app.archive_watcher = SimpleNamespace(running=True)
    app.queued_decisions = []
    app._log_threadsafe = lambda *_args, **_kwargs: None
    app._note_watch_activity = lambda **_kwargs: None
    app._handle = lambda decision, **_kwargs: app.queued_decisions.append(decision)
    return app, decision, output


def test_archive_watch_moves_confidently_misfiled_pdf_to_mapped_folder(
        monkeypatch, tmp_path):
    source = _pdf(tmp_path / "Arkiv" / "Fel mapp" / "2025" / "wrong.pdf")
    app, _decision, output = _app(tmp_path, source, monkeypatch=monkeypatch)
    monkeypatch.setattr(P, "exact_auto_category",
                        lambda *_args: "HorseTools Sweden AB")
    monkeypatch.setattr(P, "load_history", lambda: [])
    monkeypatch.setattr(P, "append_history", lambda _event: None)

    app._on_archived_file(source)

    destination = output / "HorseTools Sweden AB" / "Faktura" / "wrong.pdf"
    assert destination.exists()
    assert not source.exists()
    assert not app.queued_decisions


def test_archive_watch_starts_for_configured_archive_and_can_be_disabled(
        monkeypatch, tmp_path):
    made = []

    class FakeWatcher:
        def __init__(self, folders, on_file, **kwargs):
            self.folders = folders
            self.on_file = on_file
            self.kwargs = kwargs
            self.running = False
            made.append(self)

        def start(self):
            self.running = True

        def stop(self):
            self.running = False

    monkeypatch.setattr(P, "MultiFolderWatcher", FakeWatcher)
    app = P.App.__new__(P.App)
    app.settings = {
        "output_dir": str(tmp_path / "Arkiv"),
        "archive_watch_enabled": True,
        "archive_watch_interval": 30,
        "stable_seconds": 2,
        "input_dirs": [],
    }
    app.archive_watcher = None
    app._archive_watch_root = None
    app._log = lambda *_args, **_kwargs: None

    app._sync_archive_watch()

    assert len(made) == 1
    assert made[0].running
    assert made[0].folders == [(tmp_path / "Arkiv").resolve()]
    assert made[0].kwargs["recursive"] is True
    assert made[0].kwargs["interval"] == 30

    app.settings["archive_watch_enabled"] = False
    app._sync_archive_watch()
    assert not made[0].running
    assert app.archive_watcher is None


def test_archive_watch_queues_possible_misplacement_when_not_auto_safe(
        tmp_path):
    source = _pdf(tmp_path / "Arkiv" / "Fel mapp" / "2025" / "review.pdf")
    app, decision, output = _app(tmp_path, source, status="ask")

    app._on_archived_file(source)

    assert source.exists()
    assert not (output / "HorseTools Sweden AB" / "Faktura" / "review.pdf").exists()
    assert app.queued_decisions == [decision]
    assert "felplacering" in decision.reason.lower()
