from __future__ import annotations

import pdfsorter as P
from pdfsorter_data import Rules


def _app_with_rules(rules, *, confirm):
    app = P.App.__new__(P.App)
    app.rules = rules
    app.root = object()
    app.messages = []
    app.errors = []
    app.logs = []
    app.messagebox = type("MessageBox", (), {
        "askyesno": staticmethod(lambda *args, **kwargs: confirm),
        "showinfo": staticmethod(
            lambda *args, **kwargs: app.messages.append(args[1])),
        "showerror": staticmethod(
            lambda *args, **kwargs: app.errors.append(args[1])),
    })
    app._refresh_categories = lambda: None
    app._warm_patterns = lambda: None
    app._log = lambda *args, **kwargs: app.logs.append(args)
    return app


def test_clear_all_categories_backs_up_and_can_be_undone_after_restart(tmp_path):
    path = tmp_path / "rules.json"
    rules = Rules({"categories": [
        {"name": "Acme", "keywords": [{"text": "invoice"}]},
        {"name": "Other", "keywords": [{"text": "receipt"}]},
    ]}, path)
    rules.save()
    app = _app_with_rules(rules, confirm=True)

    P.App._cat_clear_all(app)

    assert rules.categories == []
    assert rules.names() == []
    assert rules.all_keyword_texts() == {}
    assert Rules.load(path).categories == []
    assert "Tog bort alla 2 kategorier" in app.logs[0][0]
    backups = app._category_clear_backup_files()
    assert len(backups) == 1
    assert Rules.load(backups[0]).names() == ["Acme", "Other"]

    # A fresh app instance can find and restore the durable backup.
    restored_rules = Rules.load(path)
    restore_app = _app_with_rules(restored_rules, confirm=True)
    assert restore_app._category_clear_backup_path() == backups[0]

    P.App._cat_restore_clear_backup(restore_app)

    assert restored_rules.names() == ["Acme", "Other"]
    assert Rules.load(path).names() == ["Acme", "Other"]
    assert not backups[0].exists()


def test_clear_all_categories_keeps_rules_when_cancelled(tmp_path):
    rules = Rules({"categories": [
        {"name": "Acme", "keywords": [{"text": "invoice"}]},
    ]}, tmp_path / "rules.json")
    app = _app_with_rules(rules, confirm=False)

    P.App._cat_clear_all(app)

    assert rules.names() == ["Acme"]
    assert rules.all_keyword_texts() == {"invoice": 1}
    assert not app.logs
    assert not app._category_clear_backup_files()


def test_clear_all_categories_handles_empty_rules(tmp_path):
    app = _app_with_rules(Rules({"categories": []}, tmp_path / "rules.json"),
                          confirm=False)

    P.App._cat_clear_all(app)

    assert app.messages == ["Det finns inga kategorier att tömma."]
    assert not app.logs


def test_clear_all_categories_aborts_if_backup_cannot_be_created(tmp_path, monkeypatch):
    rules = Rules({"categories": [
        {"name": "Acme", "keywords": [{"text": "invoice"}]},
    ]}, tmp_path / "rules.json")
    app = _app_with_rules(rules, confirm=True)

    def fail_copy(*_args, **_kwargs):
        raise OSError("disk is read-only")

    monkeypatch.setattr(P.shutil, "copy2", fail_copy)
    P.App._cat_clear_all(app)

    assert rules.names() == ["Acme"]
    assert "Kategorierna är kvar" in app.errors[0]
    assert not app._category_clear_backup_files()
