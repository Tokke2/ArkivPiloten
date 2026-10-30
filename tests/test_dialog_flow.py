# -*- coding: utf-8 -*-
"""Granskningsdialogens sökfält, kört genom dialogens RIKTIGA metoder.

Tidigare testades bara de rena hjälpfunktionerna. Här används en liten
Tk-fri stand-in för de widgetar dialogmetoderna rör, så att själva
flödet prövas: skriv "p" -> listan filtreras, skriv "i" och "l" -> PIL
kvar, Enter väljer. Inget Tkinter behövs, så testet går även i CI.
"""
from __future__ import annotations

from types import SimpleNamespace

import pdfsorter as P

NAMES = ["Pilkington", "CALL", "CASE OF FIRE", "EVACUATE",
         "FARA RÅDA", "PARKERINGEN AYGSINN", "RESCUE",
         "Utrymningsplan", "Utrymningsplan 2"]


class _FakeTk:
    def __init__(self):
        self.calls = []
        self.on_call = None

    def call(self, *args):
        self.calls.append(args)
        if self.on_call is not None:
            self.on_call(*args)
        return ""


class _FakeCombo:
    """Nog av ttk.Combobox för dialogmetoderna."""

    def __init__(self, values):
        self.values = list(values)
        self.text = values[0] if values else ""
        self.tk = _FakeTk()
        self._ta_seed = ""
        self.selected = None

    def __getitem__(self, key):
        if key != "values":
            raise KeyError(key)
        return list(self.values)

    def __setitem__(self, key, value):
        if key != "values":
            raise KeyError(key)
        self.values = list(value)

    def get(self):
        return self.text

    def set(self, value):
        self.text = value

    def current(self, index=None):
        if index is None:
            return self.selected if self.selected is not None else -1
        self.selected = index
        if 0 <= index < len(self.values):
            self.text = self.values[index]
        return index

    def selection_range(self, first, last):
        self.tk.calls.append(("selection_range", first, last))

    def icursor(self, pos):
        self.tk.calls.append(("icursor", pos))


class _FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _FakeEntry:
    def __init__(self):
        self.text = ""
        self.state = "normal"

    def delete(self, first, last=None):
        self.text = ""

    def insert(self, index, text):
        self.text = text if index == 0 else self.text + text

    def configure(self, **kw):
        if "state" in kw:
            self.state = kw["state"]

    def get(self):
        return self.text


class _Stub:
    """Minimal Tk-fri stand-in för ReviewDialog."""

    def __init__(self, names=NAMES):
        self._all_categories = list(names)
        self.combo = _FakeCombo(names)
        self.mode = _FakeVar("existing")
        self.new_entry = _FakeEntry()
        self._combo_hint_lbl = None          # ingen Tk-label i testet
        self.popdown_open = False
        self.posted = []                     # seed per öppning
        self.unposted = 0
        # Tk:s Unpost gör listan omappad - modellera det, så att
        # _combo_reset_values ser samma sak som i det riktiga programmet.
        self.combo.tk.on_call = self._tk_call

    # -- dialogens egna hjälpare, ersatta med bokföring -------------------
    def _popdown_open(self):
        return self.popdown_open

    def _post_dropdown(self, seed=None):
        if seed is not None:
            self.combo._ta_seed = seed
        self.posted.append(seed)
        self.popdown_open = True

    def _combo_unpost(self):                 # används av _combo_search
        self.popdown_open = False
        self.unposted += 1

    # -- riktiga metoder från ReviewDialog -------------------------------
    _sync = P.ReviewDialog._sync
    _combo_show_hint = P.ReviewDialog._combo_show_hint
    _combo_search = P.ReviewDialog._combo_search
    _combo_pick = P.ReviewDialog._combo_pick
    _combo_reset = P.ReviewDialog._combo_reset
    _combo_reset_values = P.ReviewDialog._combo_reset_values
    _combo_navigate = P.ReviewDialog._combo_navigate
    _combo_chosen = P.ReviewDialog._combo_chosen
    _combo_focus_in = P.ReviewDialog._combo_focus_in

    # -- Tk-anrop som dialogen gör via self.combo.tk ---------------------
    def _tk_call(self, *args):
        if args and args[0] == "ttk::combobox::Unpost":
            self.popdown_open = False
            self.unposted += 1


def _key(keysym, char=""):
    return SimpleNamespace(keysym=keysym, char=char or keysym,
                           state=0, widget=None)


def _type(stub, text):
    """Skriv tecken för tecken som Tk gör: fältet får texten först."""
    for ch in text:
        stub.combo.text = stub.combo.get() + ch
        stub._combo_search(_key(ch))


def test_review_dialog_uses_an_editable_free_text_folder_search():
    import inspect

    source = inspect.getsource(P.ReviewDialog.__init__)
    assert 'text="Befintlig mapp:"' in source
    assert 'text="VART SKA FILEN SPARAS?"' in source
    assert 'text="STÖDORD OCH TRÄFFAR"' in source
    assert 'state="normal"' in source
    assert 'self.combo.bind("<KeyRelease>", self._combo_search)' in source
    assert "self.combo.bind(\"<Return>\", self._combo_pick)" in source


def test_typing_p_shows_only_names_starting_with_p():
    stub = _Stub()
    stub.combo.text = ""
    _type(stub, "p")
    assert stub.combo["values"] == ["Pilkington", "PARKERINGEN AYGSINN"]
    assert stub.mode.get() == "existing"
    assert stub.posted == ["p"]              # listan öppnades med träffarna


def test_typing_p_i_l_keeps_narrowing_to_pil():
    stub = _Stub()
    stub.combo.text = ""
    _type(stub, "p")
    assert stub.combo["values"] == ["Pilkington", "PARKERINGEN AYGSINN"]
    _type(stub, "il")
    assert stub.combo["values"] == ["Pilkington"]
    assert stub.combo._ta_seed == "pil"


def test_enter_picks_the_unique_hit_and_restores_the_list():
    stub = _Stub()
    stub.combo.text = ""
    _type(stub, "pil")
    stub._combo_pick(_key("Return"))
    assert stub.combo.get() == "Pilkington"
    assert stub.combo["values"] == NAMES     # hela listan tillbaka
    assert stub.mode.get() == "existing"
    assert stub.new_entry.text == ""


def test_unknown_name_becomes_a_new_folder():
    stub = _Stub()
    stub.combo.text = ""
    _type(stub, "Zzz Projekt")
    assert stub.combo["values"] == []        # inga falska träffar
    assert stub.mode.get() == "new"
    assert stub.new_entry.text == "Zzz Projekt"
    assert stub.new_entry.state == "normal"


def test_accent_and_case_do_not_matter():
    stub = _Stub()
    stub.combo.text = ""
    _type(stub, "fara rada")
    assert stub.combo["values"] == ["FARA RÅDA"]


def test_ambiguous_enter_opens_the_list_instead_of_guessing():
    stub = _Stub()
    stub.combo.text = ""
    _type(stub, "utrymningspla")             # matchar två mappar
    assert len(stub.combo["values"]) == 2
    stub._combo_pick(_key("Return"))
    assert stub.mode.get() == "existing"
    assert stub.combo["values"] == ["Utrymningsplan", "Utrymningsplan 2"]
    assert stub.new_entry.text == ""


def test_escape_restores_the_full_list():
    stub = _Stub()
    stub.combo.text = ""
    _type(stub, "pil")
    assert stub._combo_reset(_key("Escape")) == "break"
    assert stub.combo["values"] == NAMES


def test_arrow_up_walks_the_full_list():
    stub = _Stub()
    stub.combo.set("Pilkington")
    assert stub._combo_navigate(_key("Up")) == "break"
    assert stub.combo.get() == NAMES[-1]     # sista posten, cykliskt
    assert stub._combo_navigate(_key("Up")) == "break"
    assert stub.combo.get() == NAMES[-2]


def test_focus_selects_the_text_so_the_first_key_replaces_it():
    stub = _Stub()
    stub.combo.set("Pilkington")
    stub._combo_focus_in(_key("FocusIn"))
    assert ("selection_range", 0, "end") in stub.combo.tk.calls
    assert stub.combo["values"] == NAMES
