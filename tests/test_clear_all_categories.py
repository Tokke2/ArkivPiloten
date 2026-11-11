from __future__ import annotations

import pdfsorter as P
from pdfsorter_data import Rules


def _app_with_rules(rules, *, confirm):
    app = P.App.__new__(P.App)
    app.rules = rules
    app.root = object()
    app.messages = []
    app.logs = []
    app.messagebox = type("MessageBox", (), {
        "askyesno": staticmethod(lambda *args, **kwargs: confirm),
        "showinfo": staticmethod(
            lambda *args, **kwargs: app.messages.append(args[1])),
    })
    app._refresh_categories = lambda: None
    app._log = lambda *args, **kwargs: app.logs.append(args)
    return app


def test_clear_all_categories_removes_rules_after_confirmation(tmp_path):
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


def test_clear_all_categories_keeps_rules_when_cancelled(tmp_path):
    rules = Rules({"categories": [
        {"name": "Acme", "keywords": [{"text": "invoice"}]},
    ]}, tmp_path / "rules.json")
    app = _app_with_rules(rules, confirm=False)

    P.App._cat_clear_all(app)

    assert rules.names() == ["Acme"]
    assert rules.all_keyword_texts() == {"invoice": 1}
    assert not app.logs


def test_clear_all_categories_handles_empty_rules(tmp_path):
    app = _app_with_rules(Rules({"categories": []}, tmp_path / "rules.json"),
                          confirm=False)

    P.App._cat_clear_all(app)

    assert app.messages == ["Det finns inga kategorier att tömma."]
    assert not app.logs
