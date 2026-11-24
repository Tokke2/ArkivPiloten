# -*- coding: utf-8 -*-
"""Menyraden: samma funktioner som flikarna, nåbara utan att leta.

Flikarna kräver att man minns var saker bor - autostarten låg längst ned på
Inställningar och gick inte ens att rulla fram (se
test_scrollable_settings.py). Menyraden är den genväg som alltid syns.

Innehållet beskrivs som data i ``meny_spec()``, just för att kunna granskas
här utan Tk: att varje post pekar på en metod som finns, att genvägarna är
unika och att autostarten finns med.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pdfsorter as P
import pdfsorter_data as D

ROOT = Path(__file__).resolve().parents[1]


def _alla_poster():
    for meny in P.meny_spec():
        for post in meny["poster"]:
            if post.get("typ") != "avdelare":
                yield meny["titel"], post


# -- innehållet ------------------------------------------------------------
def test_the_menu_bar_has_the_expected_menus():
    titlar = [m["titel"] for m in P.meny_spec()]
    assert titlar == ["Arkiv", "Inställningar", "Visa", "Hjälp"]


def test_every_entry_has_a_text_and_unique_id():
    ids = [post["id"] for _m, post in _alla_poster()]
    assert len(ids) == len(set(ids)), f"dubblerade id:n: {ids}"
    for titel, post in _alla_poster():
        assert post.get("text"), f"{titel}/{post['id']} saknar text"


def test_only_separators_are_separators():
    for meny in P.meny_spec():
        for post in meny["poster"]:
            if post.get("typ") == "avdelare":
                assert set(post) == {"typ"}, post
            else:
                assert post.get("typ") != "avdelare"


def test_autostart_is_reachable_from_the_menu():
    """Det användaren inte hittade i flikarna ska ligga i menyn."""
    poster = {p["id"]: p for _m, p in _alla_poster()}
    auto = poster["autostart"]
    assert auto["typ"] == "kryss"
    assert auto["var"] == "var_autostart"
    assert auto["atgard"] == "_toggle_autostart"
    assert "automatiskt" in auto["text"].lower()


def test_every_action_points_at_a_real_method():
    for titel, post in _alla_poster():
        metod = post.get("atgard")
        if not metod:
            continue
        funktion = getattr(P.App, metod, None)
        assert callable(funktion), f"{titel}/{post['id']}: {metod} finns inte"


def test_every_tab_entry_points_at_a_real_tab():
    for titel, post in _alla_poster():
        if post.get("typ") != "flik":
            continue
        assert post["flik"] in P._MENY_FLIKAR, post


def test_check_and_radio_entries_are_bound_to_variables():
    for titel, post in _alla_poster():
        typ = post.get("typ")
        if typ in ("kryss", "radio"):
            assert post.get("var"), f"{titel}/{post['id']} saknar variabel"
        if typ == "radio":
            assert "varde" in post, post
        if post.get("installning"):
            assert post["installning"] in D.DEFAULT_SETTINGS, post


def test_settings_saved_from_the_menu_exist_in_default_settings():
    for _titel, post in _alla_poster():
        nyckel = post.get("installning")
        if nyckel:
            assert nyckel in D.DEFAULT_SETTINGS


def test_shortcuts_are_unique():
    snabba = [post["snabb"] for _m, post in _alla_poster() if post.get("snabb")]
    assert len(snabba) == len(set(snabba)), snabba


def test_the_shortcuts_cover_the_daily_work():
    snabba = {post["id"]: post.get("snabb") for _m, post in _alla_poster()}
    assert snabba["sortera_nu"] == "F5"
    assert snabba["avsluta"] == "Ctrl+Q"
    assert snabba["hjalp"] == "F1"


# -- tangenterna -----------------------------------------------------------
def test_platform_modifier():
    assert P.meny_snabbmodifierare("darwin") == "Command"
    assert P.meny_snabbmodifierare("win32") == "Ctrl"
    assert P.meny_snabbmodifierare("linux") == "Ctrl"


def test_tk_sequences_for_windows_and_macos():
    # Utan Shift binds gemener, med Shift versaler - annars matchar Tk
    # inte tangenten på alla plattformar.
    assert P.meny_snabb_tangent("Ctrl+O", "win32") == \
        "<Control-KeyPress-o>"
    assert P.meny_snabb_tangent("Ctrl+O", "darwin") == \
        "<Command-KeyPress-o>"
    assert P.meny_snabb_tangent("Ctrl+Shift+A", "linux") == \
        "<Control-Shift-KeyPress-A>"
    assert P.meny_snabb_tangent("Ctrl+Shift+O", "win32") == \
        "<Control-Shift-KeyPress-O>"
    assert P.meny_snabb_tangent("F5") == "<F5>"
    assert P.meny_snabb_tangent("F1") == "<F1>"
    assert P.meny_snabb_tangent("") == ""


def test_no_shortcut_collides_with_a_navigation_key():
    """Menygenvägarna får inte ta över tangenter dialogerna använder."""
    reserverade = {"<Return>", "<Escape>", "<Tab>", "<Up>", "<Down>",
                   "<Left>", "<Right>", "<Prior>", "<Next>",
                   "<Home>", "<End>"}
    for _m, post in _alla_poster():
        if post.get("snabb"):
            sekvens = P.meny_snabb_tangent(post["snabb"])
            assert sekvens not in reserverade, sekvens


def test_every_shortcut_is_bindable():
    for _m, post in _alla_poster():
        snabb = post.get("snabb")
        if snabb:
            sekvens = P.meny_snabb_tangent(snabb)
            assert sekvens.startswith("<") and sekvens.endswith(">"), sekvens


# -- att menyraden faktiskt byggs -----------------------------------------
def _metod(klassnamn: str, namn: str) -> ast.FunctionDef:
    """Hämta en metod ur en specifik klass - __init__ finns i flera."""
    träd = ast.parse((ROOT / "pdfsorter.py").read_text(encoding="utf-8"))
    for nod in ast.walk(träd):
        if isinstance(nod, ast.ClassDef) and nod.name == klassnamn:
            for barn in nod.body:
                if isinstance(barn, ast.FunctionDef) and barn.name == namn:
                    return barn
    raise AssertionError(f"{klassnamn}.{namn} finns inte")


def _funktion(namn: str) -> ast.FunctionDef:
    """Modulnivåfunktion."""
    träd = ast.parse((ROOT / "pdfsorter.py").read_text(encoding="utf-8"))
    for nod in ast.walk(träd):
        if isinstance(nod, ast.FunctionDef) and nod.name == namn:
            return nod
    raise AssertionError(f"{namn} finns inte")


def _kod(nod: ast.AST) -> str:
    """Källkoden utan docstring - en docstring får inte styra testet."""
    kopia = ast.parse(ast.unparse(nod)).body
    if kopia and isinstance(kopia[0], ast.FunctionDef):
        f = kopia[0]
        if (f.body and isinstance(f.body[0], ast.Expr)
                and isinstance(f.body[0].value, ast.Constant)
                and isinstance(f.body[0].value.value, str)):
            f.body = f.body[1:] or [ast.Pass()]
    return ast.unparse(kopia[0])


def test_the_menu_bar_is_built_at_startup():
    init = _metod("App", "__init__")
    anrop = [n for n in ast.walk(init)
             if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "_build_menubar"]
    assert anrop, "__init__ bygger aldrig menyraden"


def test_the_menu_is_attached_to_the_window():
    källor = _kod(_metod("App", "_build_menubar"))
    assert "menu=bar" in källor, "menyraden kopplas inte till fönstret"
    assert "meny_spec()" in källor


def test_menu_shortcuts_are_bound_to_the_root_window():
    källor = _kod(_metod("App", "_bind_meny_snabb"))
    assert "self.root.bind" in källor
    assert "bind_all" not in källor, \
        "genvägar ska bara gälla huvudfönstret, inte dialogerna"


# -- klickfunktionerna (Tk-fria stand-ins) --------------------------------
def _app(**extra):
    app = object.__new__(P.App)
    app.settings = {}
    app._h = lambda *a, **k: None
    app._ui = lambda *a, **k: None
    app._log = lambda *a, **k: None
    app._fel = lambda exc, var: None
    for k, v in extra.items():
        setattr(app, k, v)
    return app


def test_tab_entry_selects_the_tab():
    valda = []

    class Notebook:
        def select(self, flik):
            valda.append(flik)

    app = _app(nb=Notebook(), tab_opts="INSTÄLLNINGAR")
    app._visa_flik("tab_opts")
    assert valda == ["INSTÄLLNINGAR"]
    # En flik som inte finns ska bara ignoreras.
    app._visa_flik("tab_finns_inte")
    assert valda == ["INSTÄLLNINGAR"]


def test_check_setting_is_saved_and_applied(monkeypatch):
    sparade = []
    monkeypatch.setattr(P, "save_settings", lambda s: sparade.append(dict(s)))
    startad = []
    app = _app(var_tray=SimpleNamespace(get=lambda: False),
               _meny_tray=lambda på: startad.append(på))
    app._meny_kryss("tray_enabled", "var_tray")
    assert app.settings["tray_enabled"] is False
    assert sparade and sparade[0]["tray_enabled"] is False
    assert startad == [False]


def test_toggle_setting_does_not_touch_the_tray(monkeypatch):
    monkeypatch.setattr(P, "save_settings", lambda s: None)
    startad = []
    app = _app(var_min_tray=SimpleNamespace(get=lambda: True),
               _meny_tray=lambda på: startad.append(på))
    app._meny_kryss("minimize_to_tray", "var_min_tray")
    assert app.settings["minimize_to_tray"] is True
    assert startad == []


def test_menu_action_falls_back_to_a_log_instead_of_crashing():
    poster = []

    def logg(kategori, meddelande, nivå="info"):
        poster.append((kategori, meddelande, nivå))

    app = _app(_h=logg)
    app._meny_atgard({"id": "trasig", "text": "Trasig",
                      "atgard": "_finns_inte"})()
    assert poster and poster[0][2] == "warn"
    assert "_finns_inte" in poster[0][1]


def test_menu_action_calls_the_real_method():
    anrop = []
    app = _app(_sort_now=lambda: anrop.append("sortera"))
    app._meny_atgard({"id": "sortera_nu", "atgard": "_sort_now"})()
    assert anrop == ["sortera"]


def test_about_text_is_complete_enough_for_support():
    text = P.App._meny_om_text(object.__new__(P.App))
    assert P.APP_NAME in text
    assert P.APP_VERSION in text
    assert "GitHub Releases" in text
    assert "Python" in text
    assert "Loggar:" in text


# -- hjälpen ska berätta om menyn ----------------------------------------
def test_help_mentions_the_menu_bar():
    import pdfsorter_system as S
    text = S.help_as_text()
    assert "MENYRADEN" in text          # hjälpen versaliserar rubriker
    assert "Ctrl+B" in text and "F5" in text


# -- hela bygget med Tk-attrapper (verifierar den riktiga vägen) -----------
class _FakeMenu:
    """Nog av tk.Menu för att bygga menyraden och kunna granska den."""

    def __init__(self, parent=None, tearoff=1):
        self.parent = parent
        self.tearoff = tearoff
        self.poster = []          # (typ, etikett, accel, kommando)
        self.kaskader = []

    def add_separator(self):
        self.poster.append(("avdelare", None, None, None))

    def add_command(self, label="", accelerator="", command=None):
        self.poster.append(("kommando", label, accelerator, command))

    def add_checkbutton(self, label="", accelerator="", variable=None,
                        command=None):
        self.poster.append(("kryss", label, accelerator, command))

    def add_radiobutton(self, label="", accelerator="", variable=None,
                        value=None, command=None):
        self.poster.append(("radio", label, accelerator, command))

    def add_cascade(self, label="", menu=None):
        self.kaskader.append((label, menu))


class _FakeBool:
    def __init__(self, value=False):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _FakeRoot:
    def __init__(self):
        self.menu = None
        self.bindningar = []

    def configure(self, **kw):
        if "menu" in kw:
            self.menu = kw["menu"]

    def bind(self, sekvens, func):
        self.bindningar.append((sekvens, func))


class _FakeTk:
    Menu = _FakeMenu
    BooleanVar = _FakeBool


def _byggd_meny():
    app = object.__new__(P.App)
    app.tk = _FakeTk
    app.root = _FakeRoot()
    app._h = lambda *a, **k: None
    app._ui = lambda *a, **k: None
    app.settings = {}
    app.var_bevaka = _FakeBool(False)
    app.var_autostart = _FakeBool(False)
    app.var_tray = _FakeBool(True)
    app.var_min_tray = _FakeBool(False)
    app.var_close_tray = _FakeBool(True)
    app.var_theme = _FakeBool("ljus")
    app._sort_now = lambda: None
    app._add_input_dir = lambda: None
    app._remove_input_dir = lambda: None
    app._toggle_watch = lambda: None
    app._toggle_autostart = lambda: None
    app._open_log_dir = lambda: None
    app.open_output = lambda: None
    app.quit_app = lambda: None
    app._make_shortcut = lambda: None
    app._save_icon = lambda: None
    app._copy_ai_report = lambda: None
    app._copy_support_log = lambda: None
    app._check_updates_gui = lambda manual=False: None
    app._meny_om = lambda: None
    app.nb = None
    app._build_menubar()
    return app


def test_menubar_is_built_with_all_menus_and_attached_to_the_window():
    app = _byggd_meny()
    assert app.menubar is not None
    assert app.root.menu is app.menubar
    assert [t for t, _m in app.menubar.kaskader] == [
        "Arkiv", "Inställningar", "Visa", "Hjälp"]
    # Separatorer hamnar som egna poster, inte som tomma kommandon.
    for _titel, meny in app.menubar.kaskader:
        assert any(p[0] == "kommando" for p in meny.poster)


def test_menubar_contains_the_autostart_entry():
    app = _byggd_meny()
    inst = dict(app.menubar.kaskader)["Inställningar"]
    etiketter = [p[1] for p in inst.poster if p[1]]
    assert any("Starta automatiskt" in e for e in etiketter), etiketter


def test_menu_entries_are_callable():
    app = _byggd_meny()
    for _titel, meny in app.menubar.kaskader:
        for typ, etikett, _accel, kommando in meny.poster:
            if typ == "avdelare":
                continue
            assert callable(kommando), f"{etikett} saknar funktion"


def test_shortcuts_are_bound_and_displayed():
    app = _byggd_meny()
    sekvenser = {s for s, _f in app.root.bindningar}
    forvantade = {P.meny_snabb_tangent(p["snabb"])
                  for _m, p in _alla_poster() if p.get("snabb")}
    assert forvantade <= sekvenser, forvantade - sekvenser
    # Acceleratorn syns också i menyn (Ctrl byts mot Command på macOS).
    arkiv = dict(app.menubar.kaskader)["Arkiv"]
    accel = {p[1]: p[2] for p in arkiv.poster if p[0] == "kommando"}
    assert accel["Sortera nu"] == "F5"
    assert accel["Avsluta"].endswith("+Q")
