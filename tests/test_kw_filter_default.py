# -*- coding: utf-8 -*-
"""Stödordslistan: dölj kopplade ord + se standardordet.

* En kryssruta "Dölj kopplade ord" filtrerar bort ord som redan har en
  mappkoppling, så att okopplade ord blir lätta att hitta. Valet sparas.
* Kategorins standardord (default_keyword) syns som ★ i en egen sorterbar
  kolumn - tidigare gick det att sätta men inte att se i listan.
"""
from __future__ import annotations

from types import SimpleNamespace

import pdfsorter as P
import pdfsorter_data as D


class _Tree:
    def __init__(self, selected=()):
        self.rows = {}
        self.selected = list(selected)

    def get_children(self):
        return list(self.rows)

    def delete(self, row):
        self.rows.pop(row, None)

    def selection(self):
        return list(self.selected)

    def insert(self, _parent, _end, iid=None, tags=(), values=()):
        self.rows[iid] = values

    def exists(self, iid):
        return iid in self.rows

    def selection_add(self, iid):
        if iid not in self.selected:
            self.selected.append(iid)


class _Rules:
    def __init__(self, cat):
        self.category = cat
        self.saved = 0

    def get(self, _name):
        return self.category

    def save(self):
        self.saved += 1


class _Label:
    def configure(self, **kwargs):
        self.text = kwargs["text"]


def _cat():
    return {
        "name": "Bank",
        "keywords": [{"text": "lon", "weight": 1.0},
                     {"text": "giro", "weight": 2.0}],
        "subfolder_keyword_map": {"giro": "Kvitton"},
        "default_keyword": "giro",
    }


def _app(cat=None, hide=False):
    app = object.__new__(P.App)
    app.kw_tree = _Tree()
    app.rules = _Rules(cat if cat is not None else _cat())
    app._selected_cat = lambda: "Bank"
    app._kw_sort = ("word", False)
    app.var_kw_hide_linked = SimpleNamespace(get=lambda: hide)
    app.lbl_kw_sum = _Label()
    return app


# -- kopplingshjälp ---------------------------------------------------------
def test_keyword_is_linked_follows_the_folder_mapping():
    cat = {"subfolder_keyword_map": {"giro": "Kvitton"}}

    assert P.keyword_is_linked(cat, "Giro") is True
    assert P.keyword_is_linked(cat, "lön") is False
    assert P.keyword_is_linked({}, "giro") is False
    assert P.keyword_is_linked(None, "giro") is False


# -- standardordets stjärna --------------------------------------------------
def test_default_word_gets_a_star_in_its_own_column():
    app = _app()

    P.App._refresh_keyword_view(app)

    assert len(app.kw_tree.rows["lon"]) == 7
    assert app.kw_tree.rows["lon"][-1] == ""
    assert app.kw_tree.rows["giro"][-1] == "★"
    assert app.kw_tree.rows["giro"][-2] == "Kvitton"


def test_no_star_without_a_default_word():
    cat = _cat()
    cat.pop("default_keyword")
    app = _app(cat)

    P.App._refresh_keyword_view(app)

    assert all(v[-1] == "" for v in app.kw_tree.rows.values())


def test_star_column_sorts_default_first():
    app = _app()
    app._kw_sort = ("std", True)

    P.App._refresh_keyword_view(app)

    assert list(app.kw_tree.rows) == ["giro", "lon"]


def test_changing_default_refreshes_the_keyword_view():
    cat = _cat()
    cat["default_keyword"] = ""
    app = object.__new__(P.App)
    app._selected_cat = lambda: "Bank"
    app.rules = _Rules(cat)
    app.var_default_keyword = SimpleNamespace(get=lambda: "Lon",
                                              set=lambda _v: None)
    refreshed = []
    app._refresh_subfolder_map = lambda: refreshed.append("map")
    app._refresh_keyword_view = lambda: refreshed.append("words")
    app.lbl_subfolder_map_status = _Label()

    P.App._cat_default_changed(app)

    assert cat["default_keyword"] == "lon"
    assert refreshed == ["map", "words"]


# -- filtret -----------------------------------------------------------------
def test_hide_linked_filter_shows_only_unlinked_words():
    app = _app(hide=True)

    P.App._refresh_keyword_view(app)

    assert list(app.kw_tree.rows) == ["lon"]
    assert "kopplade dolda" in app.lbl_kw_sum.text
    assert "visar 1 av 2" in app.lbl_kw_sum.text


def test_filter_off_shows_everything_without_notice():
    app = _app(hide=False)

    P.App._refresh_keyword_view(app)

    assert sorted(app.kw_tree.rows) == ["giro", "lon"]
    assert "kopplade dolda" not in app.lbl_kw_sum.text


def test_toggle_saves_the_setting_and_refreshes(monkeypatch):
    saved = {}
    monkeypatch.setattr(P, "save_settings", lambda s: saved.update(s))
    app = object.__new__(P.App)
    app.settings = {}
    app.var_kw_hide_linked = SimpleNamespace(get=lambda: True)
    refreshed = []
    app._refresh_keyword_view = lambda: refreshed.append(True)

    P.App._toggle_kw_hide_linked(app)

    assert saved == {"kw_hide_linked": True}
    assert refreshed == [True]


def test_filter_checkbox_is_wired_and_translated():
    import ast
    from pathlib import Path

    source = Path(P.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    app = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "App")
    build = next(n for n in app.body
                 if isinstance(n, ast.FunctionDef)
                 and n.name == "_build_cats_tab")
    text = ast.unparse(build)

    assert "var_kw_hide_linked" in text
    assert "Dölj kopplade ord" in text
    assert "_toggle_kw_hide_linked" in text
    assert "Dölj kopplade ord" in P._UI_EN
    assert D.DEFAULT_SETTINGS["kw_hide_linked"] is False
