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


def test_open_dropdown_installs_live_search_key_binding():
    calls = []
    bound = []
    tk = SimpleNamespace(call=lambda *args: calls.append(args))
    combo = SimpleNamespace(
        tk=tk,
        _bind=lambda what, sequence, func, add=None:
            bound.append((what, sequence, func, add)),
    )
    dialog = SimpleNamespace(
        combo=combo,
        win=SimpleNamespace(register=lambda fn: "pick-callback"),
        _popdown_lb_path=lambda: ".combo.popdown.f.l",
        _combo_pick=lambda event=None: "break",
        _combo_popup_keypress=lambda event: "break",
        _return_bound_listbox=None,
    )

    P.ReviewDialog._bind_popdown_return(dialog)

    assert any(call[1:3] == (".combo.popdown.f.l", "<Return>")
               for call in calls)
    assert bound == [(("bind", ".combo.popdown.f.l"), "<KeyPress>",
                      dialog._combo_popup_keypress, "+")]


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


class _SearchCombo:
    def __init__(self, text):
        self.text = text
        self.values = []
        self._ta_seed = ""

    def get(self):
        return self.text

    def __setitem__(self, key, value):
        assert key == "values"
        self.values = list(value)


def test_typing_in_search_field_keeps_an_already_open_dropdown_posted():
    combo = _SearchCombo("li")
    refreshed = []
    rendered = []
    dialog = SimpleNamespace(
        combo=combo,
        _popdown_open=lambda: True,
        _all_categories=["Lindab", "Lidingö", "Ekonomikontor"],
        _combo_render_suggestions=rendered.append,
        _combo_show_hint=lambda *args: None,
        mode=SimpleNamespace(set=lambda value: None),
        _sync=lambda: None,
        new_entry=SimpleNamespace(delete=lambda *args: None),
        _combo_refresh_popup=refreshed.append,
    )

    P.ReviewDialog._combo_search(
        dialog, SimpleNamespace(keysym="n", state=0))

    assert combo.values == ["Lindab", "Lidingö"]
    assert rendered == [[]]  # the native popup is used; no second list appears
    assert refreshed == [True]  # do not unpost the dropdown while typing


def test_live_typeahead_highlights_first_match_in_open_dropdown():
    calls = []

    class Combo:
        tk = SimpleNamespace(call=lambda *args: calls.append(args))

        def __getitem__(self, key):
            assert key == "values"
            return ["Lidingö", "Lindab"]

        @staticmethod
        def get():
            return "li"

    selected = []
    dialog = SimpleNamespace(
        combo=Combo(),
        _popdown_open=lambda: True,
        _popdown_select_first=lambda: selected.append("first"),
        _popdown_clear_selection=lambda: selected.append("clear"),
    )

    P.ReviewDialog._combo_refresh_popup(dialog, keep_open=True)

    assert calls == [("ttk::combobox::ConfigureListbox", dialog.combo)]
    assert selected == ["first"]


def test_first_typeahead_match_is_highlighted_and_scrolled_into_view():
    calls = []

    def tk_call(*args):
        calls.append(args)
        if args == (".combo.popdown.f.l", "size"):
            return 3
        return ""

    dialog = SimpleNamespace(
        combo=SimpleNamespace(tk=SimpleNamespace(call=tk_call)),
        _popdown_open=lambda: True,
        _popdown_lb_path=lambda: ".combo.popdown.f.l",
        _popdown_clear_selection=lambda: calls.append(("clear-selection",)),
    )

    P.ReviewDialog._popdown_select_first(dialog)

    assert calls == [
        (".combo.popdown.f.l", "size"),
        (".combo.popdown.f.l", "selection", "clear", 0, "end"),
        (".combo.popdown.f.l", "selection", "set", 0),
        (".combo.popdown.f.l", "activate", 0),
        (".combo.popdown.f.l", "see", 0),
    ]


def test_empty_typeahead_does_not_highlight_first_open_dropdown_item():
    calls = []

    class Combo:
        tk = SimpleNamespace(call=lambda *args: calls.append(args))

        def __getitem__(self, key):
            assert key == "values"
            return []

        @staticmethod
        def get():
            return "missing"

    selected = []
    dialog = SimpleNamespace(
        combo=Combo(),
        _popdown_open=lambda: True,
        _popdown_select_first=lambda: selected.append("first"),
        _popdown_clear_selection=lambda: selected.append("clear"),
    )

    P.ReviewDialog._combo_refresh_popup(dialog, keep_open=True)

    assert selected == ["clear"]
