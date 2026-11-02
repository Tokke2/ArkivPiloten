# -*- coding: utf-8 -*-
"""Typing stays in the category search field when its popup is opened."""
from __future__ import annotations

from types import SimpleNamespace

import pdfsorter as P


def _dialog(state, scheduled, focus_calls):
    combo = SimpleNamespace(
        _replace_on_type=False,
        get=lambda: "Lidingö",
        focus_set=lambda: focus_calls.append("focus"),
        icursor=lambda pos: focus_calls.append(("icursor", pos)),
    )
    dialog = SimpleNamespace(
        combo=combo,
        _all_categories=["Lidingö", "Lindab"],
        win=SimpleNamespace(after_idle=scheduled.append),
        _popdown_open=lambda: state["open"],
        _popdown_clear_selection=lambda: None,
        _bind_popdown_return=lambda: None,
    )
    dialog._keep_combo_search_focus = lambda: \
        P.ReviewDialog._keep_combo_search_focus(dialog)
    return dialog


def test_mouse_opened_dropdown_returns_focus_to_search_field():
    state = {"open": False}
    scheduled = []
    focus_calls = []
    dialog = _dialog(state, scheduled, focus_calls)

    P.ReviewDialog._combo_schedule_popup_bind(dialog)

    # Tk's class binding opens the popup after the widget binding returns.
    state["open"] = True
    assert len(scheduled) == 3
    scheduled[-1]()

    assert focus_calls == ["focus", ("icursor", "end")]


def test_keyboard_opened_dropdown_returns_focus_to_search_field():
    state = {"open": False}
    scheduled = []
    focus_calls = []
    dialog = _dialog(state, scheduled, focus_calls)
    dialog._combo_suggestions_visible = lambda: False

    result = P.ReviewDialog._combo_navigate(
        dialog, SimpleNamespace(keysym="Down"))

    # Tk opens the popup after the Down binding returns.
    state["open"] = True
    assert result == ""
    assert len(scheduled) == 2
    scheduled[-1]()

    assert focus_calls == ["focus", ("icursor", "end")]
