from types import SimpleNamespace

import pdfsorter as P
from pdfsorter_read import Extraction


def test_update_restart_persists_pending_review_files(tmp_path, monkeypatch):
    previous = tmp_path / "existing.pdf"
    current = tmp_path / "queued.pdf"
    previous.write_bytes(b"first")
    current.write_bytes(b"second")
    saved = []

    class Rules:
        def save(self):
            pass

    app = object.__new__(P.App)
    app.settings = {"pending_review_paths": [str(previous)]}
    app.queue = [SimpleNamespace(path=current)]
    app._collect_settings = lambda: True
    app.watcher = None
    app._stop_archive_watch = lambda: None
    app.rules = Rules()
    app._h = lambda *_args, **_kwargs: None
    app._log = lambda *_args, **_kwargs: None
    monkeypatch.setattr(P, "save_settings", lambda settings: saved.append(
        list(settings["pending_review_paths"])))
    monkeypatch.setattr(P, "flush_history", lambda: None)

    P.App._spara_fore_omstart(app)

    assert app.settings["pending_review_paths"] == [
        str(previous.resolve()), str(current.resolve())]
    assert saved[-1] == app.settings["pending_review_paths"]


def test_updated_app_restores_persisted_reviews_as_manual_questions(
        tmp_path, monkeypatch):
    pending = tmp_path / "needs-review.pdf"
    pending.write_bytes(b"pdf")
    saved = []

    class Engine:
        def analyze(self, path):
            return P.Decision(path, Extraction(path=path), [], "auto")

    class Thread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    app = object.__new__(P.App)
    app.settings = {"pending_review_paths": [str(pending),
                                              str(tmp_path / "missing.pdf")]}
    app.engine = Engine()
    app.queue = []
    app._queued_paths = set()
    app._refresh_queue = lambda: None
    app._log = lambda *_args, **_kwargs: None
    app._post = lambda callback: callback()
    monkeypatch.setattr(P.threading, "Thread", Thread)
    monkeypatch.setattr(P, "save_settings", lambda settings: saved.append(
        list(settings["pending_review_paths"])))

    P.App._restore_pending_review_queue(app)

    assert len(app.queue) == 1
    assert app.queue[0].path == pending
    assert app.queue[0].status == "ask"
    assert "Återställd" in app.queue[0].reason
    assert app.settings["pending_review_paths"] == []
    assert saved[-1] == []
