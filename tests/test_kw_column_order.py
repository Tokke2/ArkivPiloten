# -*- coding: utf-8 -*-
"""Stödordstabellens kolumner går att flytta genom att dra rubrikerna."""
from types import SimpleNamespace

import pdfsorter as P
import pdfsorter_data as D


def test_normalize_column_order_keeps_valid_and_repairs_broken():
    saved = ["hits", "word", "folder", "kind", "weight", "whole"]

    assert P.normalize_column_order(saved) == saved
    assert P.normalize_column_order([]) == list(P.KW_COLUMNS)
    assert P.normalize_column_order(["word", "hits"]) == list(P.KW_COLUMNS)
    assert P.normalize_column_order("word") == list(P.KW_COLUMNS)
    assert P.normalize_column_order(None) == list(P.KW_COLUMNS)
    assert D.DEFAULT_SETTINGS["kw_column_order"] == []


def test_drop_column_moves_to_nearest_gap():
    order = ["a", "b", "c", "d"]
    widths = [100, 100, 100, 100]

    # Släpp mitt i c:s andra halva: b hamnar efter c.
    assert P.drop_column_at(order, "b", widths, 260) == ["a", "c", "b", "d"]
    # Släpp längst till vänster: c hamnar först.
    assert P.drop_column_at(order, "c", widths, 40) == ["c", "a", "b", "d"]
    # Släpp i det egna spannet: ingen flytt.
    assert P.drop_column_at(order, "b", widths, 150) == order
    # Utanför kanterna: kläms fast i änden.
    assert P.drop_column_at(order, "b", widths, 999) == ["a", "c", "d", "b"]
    assert P.drop_column_at(order, "c", widths, -5) == ["c", "a", "b", "d"]


def test_drop_column_ignores_invalid_input():
    order = ["a", "b"]

    assert P.drop_column_at(order, "x", [10, 10], 5) == order
    assert P.drop_column_at(order, "a", [10], 5) == order
    assert P.drop_column_at(order, "a", [10, 10], "z") == order
    assert P.drop_column_at([], "a", [], 5) == []


class _Tree:
    def __init__(self):
        self.display = list(P.KW_COLUMNS)
        self.widths = {c: 100 for c in P.KW_COLUMNS}
        self.region = "heading"
        self.column_id = "#1"

    def __getitem__(self, key):
        assert key == "displaycolumns"
        return list(self.display)

    def __setitem__(self, key, value):
        assert key == "displaycolumns"
        self.display = list(value)

    def identify_region(self, _x, _y):
        return self.region

    def identify_column(self, _x):
        return self.column_id

    def column(self, col, _option):
        return self.widths[col]

    def configure(self, **_kwargs):
        pass


def _drag_app(monkeypatch):
    saved = {}
    monkeypatch.setattr(P, "save_settings", lambda s: saved.update(s))
    app = object.__new__(P.App)
    app.kw_tree = _Tree()
    app.settings = {}
    app._kw_col_drag = None
    app._kw_col_moved = False
    return app, saved


def test_heading_drag_moves_column_and_saves_order(monkeypatch):
    app, saved = _drag_app(monkeypatch)
    app.kw_tree.column_id = "#2"  # TYP-kolumnen

    P.App._kw_column_drag_start(app, SimpleNamespace(x=150, y=5))
    P.App._kw_column_drag_motion(app, SimpleNamespace(x=320, y=5))
    P.App._kw_column_drag_release(app, SimpleNamespace(x=320, y=5))

    assert app.kw_tree.display[2] == "kind"
    assert saved["kw_column_order"] == app.kw_tree.display


def test_plain_heading_click_sorts_but_drag_does_not(monkeypatch):
    app, _saved = _drag_app(monkeypatch)
    app.kw_tree.column_id = "#1"

    P.App._kw_column_drag_start(app, SimpleNamespace(x=50, y=5))
    P.App._kw_column_drag_release(app, SimpleNamespace(x=52, y=5))

    assert app.kw_tree.display == list(P.KW_COLUMNS)  # klick = ingen flytt
    assert app._kw_col_moved is False

    app._kw_col_moved = True  # draget sätter flaggan före rubrikkommandot
    app._kw_sort = ("hits", True)
    P.App._sort_keywords(app, "word")

    assert app._kw_sort == ("hits", True)  # sorteringen hoppades över
    assert app._kw_col_moved is False


def test_drag_start_ignores_rows_and_unknown_columns(monkeypatch):
    app, _saved = _drag_app(monkeypatch)
    app.kw_tree.region = "cell"

    P.App._kw_column_drag_start(app, SimpleNamespace(x=50, y=100))

    assert app._kw_col_drag is None

    app.kw_tree.region = "heading"
    app.kw_tree.column_id = "#0"
    P.App._kw_column_drag_start(app, SimpleNamespace(x=0, y=5))

    assert app._kw_col_drag is None
