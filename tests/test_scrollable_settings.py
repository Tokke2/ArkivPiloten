# -*- coding: utf-8 -*-
"""Inställningsfliken måste gå att rulla - annars syns inte autostart.

Rapporterat: "ser inte att jag kan ställa in autostart av appen". Orsaken
var inte att inställningen saknades: kryssrutan "Starta automatiskt med
datorn" fanns i kortet "Start och systemfält", som är det SJÄTTE och
nedersta kortet på fliken Inställningar. Fliken var en vanlig Frame utan
rullning, så allt under fönsterkanten - inklusive autostarten - gick inte
att nå.

Testerna låser:
* att fliken byggs i en rullbar canvas (AST-kontroll, ingen Tk behövs),
* att mushjulet rullar fliken men aldrig när pekaren står över en lista
  eller ett inmatningsfält,
* att bindningen bara läggs till en gång (annars rullar det dubbelt),
* att den kopplas tillbaka efter en dialog, eftersom dialogens
  ``unbind_all`` tar bort även flikens bindning.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pdfsorter as P

ROOT = Path(__file__).resolve().parents[1]


# -- rena hjälpare ---------------------------------------------------------
class _W:
    """Minimal widget: klassnamn + förälder."""

    def __init__(self, klass: str, master=None, namn=""):
        self._klass = klass
        self.master = master
        self.namn = namn or klass

    def winfo_class(self):
        return self._klass

    def __repr__(self):
        return f"<{self._klass}>"


def test_self_scrolling_widgets_are_recognised():
    for klass in ("Listbox", "Text", "Treeview", "TCombobox", "TEntry",
                  "Entry", "Spinbox", "TSpinbox", "Canvas"):
        assert P._widget_scrolls_itself(_W(klass)) is True, klass


def test_labels_and_frames_do_not_scroll_themselves():
    ram = _W("TFrame")
    assert P._widget_scrolls_itself(_W("TLabel", master=ram)) is False
    assert P._widget_scrolls_itself(_W("TCheckbutton", master=ram)) is False


def test_self_scrolling_parent_counts():
    """En etikett inuti en listbox ska räknas som listan."""
    lista = _W("Listbox")
    assert P._widget_scrolls_itself(_W("TLabel", master=lista)) is True


def test_a_broken_widget_never_raises():
    class Trasig:
        def winfo_class(self):
            raise RuntimeError("widgeten är förstörd")

    assert P._widget_scrolls_itself(Trasig()) is False
    assert P._widget_scrolls_itself(None) is False


def test_wheel_direction_on_windows_macos_and_x11():
    # Windows/macOS: delta ±120 respektive ±1 - bara tecknet används.
    # Returvärdet är yview-riktningen: positivt = ned, negativt = upp.
    # Hjul upp (delta > 0) betyder att innehållet ska röra sig upp.
    assert P._wheel_steps(SimpleNamespace(delta=120)) == -1
    assert P._wheel_steps(SimpleNamespace(delta=-120)) == 1
    assert P._wheel_steps(SimpleNamespace(delta=1)) == -1
    # X11: Button-4 = upp, Button-5 = ned, inget delta.
    assert P._wheel_steps(SimpleNamespace(delta=0, num=4)) == -1
    assert P._wheel_steps(SimpleNamespace(delta=0, num=5)) == 1
    # Saknade attribut ska ge noll steg, inte krasch.
    assert P._wheel_steps(SimpleNamespace()) == 0


# -- rullningen i fliken ---------------------------------------------------
class _Canvas:
    def __init__(self):
        self.scrolls = []

    def yview_scroll(self, steg, enhet):
        self.scrolls.append((steg, enhet))


def _app_with_canvas(canvas, pekare):
    app = object.__new__(P.App)
    app._scroll_canvases = [(canvas, "inställningar")]
    app.root = SimpleNamespace(
        winfo_containing=lambda x, y: pekare)
    return app


def test_wheel_over_the_tab_scrolls_the_tab():
    canvas = _Canvas()
    # Pekaren står på en etikett inne i ett kort som ligger i canvasen.
    kort = _W("TFrame", master=canvas)
    app = _app_with_canvas(canvas, _W("TLabel", master=kort))
    händelse = SimpleNamespace(x_root=10, y_root=10, delta=-120, num=0,
                               widget=None)
    assert app._tab_wheel_scroll(händelse) == "break"
    assert canvas.scrolls == [(3, "units")]


def test_wheel_over_a_list_does_not_move_the_tab():
    canvas = _Canvas()
    app = _app_with_canvas(canvas, _W("Listbox"))
    händelse = SimpleNamespace(x_root=10, y_root=10, delta=-120, num=0,
                               widget=None)
    assert app._tab_wheel_scroll(händelse) == ""
    assert canvas.scrolls == []


def test_wheel_outside_the_tab_is_left_alone():
    canvas = _Canvas()
    app = _app_with_canvas(canvas, _W("TFrame"))       # annan flik
    händelse = SimpleNamespace(x_root=99, y_root=99, delta=-120, num=0,
                               widget=None)
    assert app._tab_wheel_scroll(händelse) == ""
    assert canvas.scrolls == []


def test_missing_pointer_is_harmless():
    canvas = _Canvas()
    app = _app_with_canvas(canvas, None)
    händelse = SimpleNamespace(x_root=1, y_root=1, delta=-120, num=0,
                               widget=None)
    assert app._tab_wheel_scroll(händelse) == ""


# -- bindningen ------------------------------------------------------------
class _Root:
    def __init__(self):
        self.bindings = []

    def bind_all(self, seq, func, add=None):
        self.bindings.append((seq, func, add))


def test_binding_is_only_added_once(monkeypatch):
    root = _Root()
    monkeypatch.setattr(P, "_TAB_WHEEL_APP", None)
    P._bind_tab_wheel(root)
    P._bind_tab_wheel(root)
    P._bind_tab_wheel(root)
    assert len(root.bindings) == 3            # en per sekvens, inte nio
    assert all(add == "+" for _s, _f, add in root.bindings)


def test_dialog_close_reinstalls_the_binding(monkeypatch):
    """ReviewDialog._close gör unbind_all - då måste fliken kopplas tillbaka."""
    root = _Root()
    app = SimpleNamespace(root=root)
    monkeypatch.setattr(P, "_TAB_WHEEL_APP", app)
    P._bind_tab_wheel(root)
    assert len(root.bindings) == 3
    root._tab_wheel_bound = False          # det unbind_all gjorde
    P._reinstall_tab_wheel()
    assert len(root.bindings) == 6
    # Utan app (appen avstängd) händer ingenting och inget kraschar.
    monkeypatch.setattr(P, "_TAB_WHEEL_APP", None)
    P._reinstall_tab_wheel()


# -- fliken är faktiskt rullbar -------------------------------------------
def _funktion(namn: str) -> ast.FunctionDef:
    källa = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")
    träd = ast.parse(källa)
    for nod in ast.walk(träd):
        if isinstance(nod, ast.FunctionDef) and nod.name == namn:
            return nod
    raise AssertionError(f"{namn} finns inte")


def test_settings_tab_content_is_built_inside_a_scrollable_frame():
    """Korten MÅSTE ligga i den rullbara ramen, inte direkt i fliken."""
    f = _funktion("_build_sort_tab")
    tilldelning = [n for n in ast.walk(f)
                   if isinstance(n, ast.Assign)
                   and any(getattr(t, "id", "") == "g" for t in n.targets)]
    assert tilldelning, "hittar ingen 'g = ...' i _build_sort_tab"
    värdet = tilldelning[0].value
    assert isinstance(värdet, ast.Call), ast.dump(värdet)[:80]
    assert getattr(värdet.func, "attr", "") == "_scrollable_tab", \
        "inställningsfliken byggs inte med _scrollable_tab"


def test_the_autostart_card_is_placed_in_that_frame():
    f = _funktion("_build_sort_tab")
    kort = []
    for n in ast.walk(f):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "card" and len(n.args) >= 2):
            if isinstance(n.args[1], ast.Constant) and \
                    n.args[1].value == "Start och systemfält":
                kort.append(n)
    assert kort, "hittar inte kortet 'Start och systemfält'"
    första_arg = kort[0].args[0]
    assert getattr(första_arg, "id", "") == "g", \
        "autostart-kortet ligger utanför den rullbara ramen"


def test_autostart_checkbox_exists_and_calls_the_toggle():
    källa = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")
    assert "Starta automatiskt med datorn" in källa
    assert "command=self._toggle_autostart" in källa


# -- rullbar flik i praktiken (Tk-fria stand-ins) --------------------------
class _FakeCanvas:
    def __init__(self, parent, **kw):
        self.parent = parent
        self.kw = kw
        self.binds = []
        self.windows = []

    def yview(self, *a, **k):
        return (0.0, 1.0)

    def yview_scroll(self, steg, enhet):
        self.kw.setdefault("scrolls", []).append((steg, enhet))

    def configure(self, **kw):
        self.kw.update(kw)

    def grid(self, **kw):
        self.kw["grid"] = kw

    def bind(self, seq, func, add=None):
        self.binds.append((seq, add))

    def create_window(self, xy, **kw):
        self.windows.append(kw)
        return 1

    def itemconfigure(self, *a, **k):
        pass

    def bbox(self, *a):
        return (0, 0, 100, 500)

    def winfo_height(self):
        return 400


class _FakeWidget:
    def __init__(self, parent=None, **kw):
        self.parent = parent
        self.kw = kw
        self.binds = []

    def columnconfigure(self, *a, **k):
        pass

    def rowconfigure(self, *a, **k):
        pass

    def grid(self, **kw):
        self.kw["grid"] = kw

    def grid_remove(self):
        self.kw["removed"] = True

    def bind(self, seq, func, add=None):
        self.binds.append((seq, add))

    def winfo_reqheight(self):
        return 900

    def set(self, *a):
        """Scrollbar.set kopplas till canvasens yscrollcommand."""


def test_scrollable_tab_creates_canvas_and_scrollbar():
    app = object.__new__(P.App)
    app.tk = SimpleNamespace(Canvas=_FakeCanvas)
    app.ttk = SimpleNamespace(Scrollbar=_FakeWidget, Frame=_FakeWidget)
    app.C = {"bg": "#ffffff"}
    app._scroll_canvases = []
    flik = _FakeWidget()

    inre = app._scrollable_tab(flik, "inställningar")

    assert len(app._scroll_canvases) == 1
    canvas, namn = app._scroll_canvases[0]
    assert namn == "inställningar"
    assert isinstance(canvas, _FakeCanvas)
    assert canvas.windows, "innehållet lades aldrig i canvasen"
    assert inre is canvas.windows[0]["window"]
    # Rullning ska vara kopplad både till canvasen och till innehållet.
    assert any(seq == "<Configure>" for seq, _ in canvas.binds)
