# -*- coding: utf-8 -*-
"""Sökbar kategori-rullgardin i granskningsdialogen.

Testar den rena sök-, typahead- och tolkningslogiken (Tk krävs inte):
"p" ska bara ge namn som BÖRJAR på p (som en rullgardin som hoppar dit),
"pil" ska ge PIL-namnen, och en ofullständig söksträng får aldrig bli en
ny mapp när den pekar ut flera befintliga kategorier.
"""
from __future__ import annotations

from types import SimpleNamespace

import pdfsorter


NAMES = [
    "Pilkington", "CALL", "CASE OF FIRE", "EVACUATE",
    "FARA RÅDA", "PARKERINGEN AYGSINN", "RESCUE",
    "Utrymningsplan", "Utrymningsplan 2",
]


def test_empty_query_returns_everything_in_order():
    assert pdfsorter._filter_categories("", NAMES) == NAMES
    assert pdfsorter._filter_categories("   ", NAMES) == NAMES


def test_single_letter_jumps_to_prefix_matches_only():
    # "p" ska INTE dra in "Utrymningsplan" bara för att det finns ett p.
    assert pdfsorter._filter_categories("p", NAMES) == [
        "Pilkington", "PARKERINGEN AYGSINN"]


def test_typing_more_narrows_to_pil():
    assert pdfsorter._filter_categories("pil", NAMES) == ["Pilkington"]
    assert pdfsorter._filter_categories("PIL", NAMES) == ["Pilkington"]


def test_prefix_never_mixes_in_substring_matches():
    names = ["Min Faktura", "Faktura", "Fakturering", "Annan"]
    assert pdfsorter._filter_categories("faktur", names) == [
        "Faktura", "Fakturering"]


def test_falls_back_to_word_start_then_substring():
    # Ingen börjar på "råda", men ordet i FARA RÅDA börjar på det.
    assert pdfsorter._filter_categories("råda", NAMES) == ["FARA RÅDA"]
    assert pdfsorter._filter_categories("rada", NAMES) == ["FARA RÅDA"]
    # Ingen börjar på "aygsinn" - då visas namnet som innehåller det.
    assert pdfsorter._filter_categories("aygsinn", NAMES) == [
        "PARKERINGEN AYGSINN"]


def test_rank_reports_how_the_match_was_made():
    assert pdfsorter._rank_categories("", NAMES)[1] == "all"
    assert pdfsorter._rank_categories("p", NAMES)[1] == "prefix"
    assert pdfsorter._rank_categories("råda", NAMES)[1] == "word"
    # "aygsinn" är ett ord i namnet -> ordnivå; "gsin" är bara delsträng.
    assert pdfsorter._rank_categories("aygsinn", NAMES)[1] == "word"
    assert pdfsorter._rank_categories("gsin", NAMES)[1] == "contains"
    assert pdfsorter._rank_categories("zzz", NAMES) == ([], "none")


def test_typeahead_index_jumps_like_a_dropdown():
    values = ["Pilkington", "CALL", "PARKERINGEN AYGSINN", "Utrymningsplan"]
    assert pdfsorter._typeahead_index(values, "p") == 0
    assert pdfsorter._typeahead_index(values, "pil") == 0
    assert pdfsorter._typeahead_index(values, "pa") == 2
    assert pdfsorter._typeahead_index(values, "utrym") == 3
    assert pdfsorter._typeahead_index(values, "zzz") == -1
    assert pdfsorter._typeahead_index(values, "") == -1


def test_typeahead_cycles_from_current_position():
    values = ["Pilkington", "PARKERINGEN AYGSINN", "Utrymningsplan"]
    assert pdfsorter._typeahead_index(values, "p", 1) == 1
    assert pdfsorter._typeahead_index(values, "p", 2) == 0


def test_typeahead_ignores_case_and_diacritics():
    assert pdfsorter._typeahead_index(["FARA RÅDA"], "fara") == 0
    assert pdfsorter._typeahead_index(["FARA RÅDA"], "FARA") == 0


def test_resolve_exact_name():
    assert pdfsorter._resolve_category_name("Utrymningsplan", NAMES) == \
        "Utrymningsplan"


def test_resolve_unique_prefix():
    assert pdfsorter._resolve_category_name("Pilking", NAMES) == "Pilkington"
    assert pdfsorter._resolve_category_name("evac", NAMES) == "EVACUATE"


def test_resolve_unique_substring():
    assert pdfsorter._resolve_category_name("aygsinn", NAMES) == \
        "PARKERINGEN AYGSINN"


def test_ambiguous_query_is_not_guessed():
    # En ofullständig sträng som matchar två kategorier -> ingen gissning.
    assert pdfsorter._resolve_category_name(
        "utrymningspla", ["Utrymningsplan", "Utrymningsplan 2"]) == ""
    assert pdfsorter._resolve_category_name("utrymningsplan", []) == ""
    # ...men ett exakt namn vinner alltid, även när det är en delmängd.
    assert pdfsorter._resolve_category_name(
        "Utrymningsplan", ["Utrymningsplan 2", "Utrymningsplan"]) == \
        "Utrymningsplan"


def test_unknown_name_is_not_resolved():
    assert pdfsorter._resolve_category_name("Helt Ny Mapp", NAMES) == ""
    assert pdfsorter._resolve_category_name("", NAMES) == ""


# -- typahead i en öppen lista (samma kod som rullgardinens popdown) --------
class _FejkladLista:
    """Minimal listbox som _ta_listbox kan arbeta mot (Tk krävs inte)."""

    def __init__(self, items, path):
        self.items = list(items)
        self.path = path
        self.sel = None

    def __str__(self):
        return self.path

    def size(self):
        return len(self.items)

    def get(self, i):
        return self.items[i]

    def curselection(self):
        return () if self.sel is None else (self.sel,)

    def selection_clear(self, first, last):
        self.sel = None

    def selection_set(self, i):
        self.sel = i

    def activate(self, i):
        pass

    def see(self, i):
        pass


def _tangent(widget, ch, keysym=None):
    from types import SimpleNamespace
    return SimpleNamespace(widget=widget, char=ch,
                           keysym=keysym or ch, state=0)


def test_open_list_builds_the_search_word_p_i_l():
    from pdfsorter import _ta_listbox
    lb = _FejkladLista(NAMES, ".test_ta_pil.lb")
    _ta_listbox(_tangent(lb, "p"))
    assert lb.sel == 0                       # första P-namnet
    _ta_listbox(_tangent(lb, "i"))
    _ta_listbox(_tangent(lb, "l"))
    assert lb.sel == 0
    assert lb.items[lb.sel] == "Pilkington"


def test_open_list_keeps_narrowing_and_handles_backspace():
    from pdfsorter import _ta_listbox
    lb = _FejkladLista(NAMES, ".test_ta_back.lb")
    for ch in "park":
        _ta_listbox(_tangent(lb, ch))
    assert lb.items[lb.sel] == "PARKERINGEN AYGSINN"
    _ta_listbox(_tangent(lb, "", keysym="BackSpace"))
    assert lb.items[lb.sel] == "PARKERINGEN AYGSINN"


def test_repeated_letter_cycles_to_next_match():
    from pdfsorter import _ta_listbox
    lb = _FejkladLista(["Pilkington", "PARKERINGEN AYGSINN", "RESCUE"],
                       ".test_ta_cycle.lb")
    _ta_listbox(_tangent(lb, "p"))
    assert lb.items[lb.sel] == "Pilkington"
    _ta_listbox(_tangent(lb, "p"))           # "pp" -> nästa P-namn
    assert lb.items[lb.sel] == "PARKERINGEN AYGSINN"


# -- rullgardinens listval rullas till filtrerad träff även när öppen -----
def test_post_dropdown_scrolls_to_first_filtered_match_when_already_open():
    for opened, expected_call in (
            (False, "ttk::combobox::Post"),
            (True, "ttk::combobox::ConfigureListbox")):
        calls = []
        scheduled = []
        selected = []

        def tk_call(*args):
            calls.append(args)
            return ""

        combo = SimpleNamespace(_ta_seed="", tk=SimpleNamespace(call=tk_call))
        win = SimpleNamespace(after_idle=scheduled.append)
        dialog = SimpleNamespace(
            combo=combo,
            win=win,
            _popdown_open=lambda opened=opened: opened,
            _popdown_select_first=lambda: selected.append(True),
        )

        pdfsorter.ReviewDialog._post_dropdown(dialog, seed="pil")

        assert combo._ta_seed == "pil"
        assert calls[0][0] == expected_call
        assert len(scheduled) == 1
        scheduled.pop()()
        assert selected == [True]
