"""Tangentbordsnavigering i huvudfönstret, utan att starta Tk."""
from __future__ import annotations

import ast
from pathlib import Path

import pdfsorter as P

ROOT = Path(__file__).resolve().parents[1]


class FakeRoot:
    def __init__(self):
        self.bindings = {}
        self.focused = None
        self.widgets = {}
        self.parent = None
        self.is_toplevel = True
        self.exists = True

    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = callback

    def bind_all(self, sequence, callback, add=None):
        self.bindings["all:" + sequence] = callback

    def focus_get(self):
        return self.focused

    def nametowidget(self, name):
        return self.widgets[name]


class FakeWidget:
    def __init__(self, name, parent=None, *, mapped=True, takefocus="0",
                 state="normal", children=(), toplevel=False):
        self.name = name
        self.parent = parent
        self.is_toplevel = toplevel
        self.mapped = mapped
        self.options = {"takefocus": takefocus, "state": state}
        self.children = list(children)
        self.focused = False
        self.destroyed = False
        self.exists = True
        for child in self.children:
            child.parent = self

    def __str__(self):
        return self.name

    def cget(self, key):
        return self.options[key]

    def winfo_children(self):
        return self.children

    def winfo_ismapped(self):
        return self.mapped

    def winfo_toplevel(self):
        node = self
        while node.parent is not None and not getattr(node, "is_toplevel", False):
            node = node.parent
        return node

    def winfo_exists(self):
        return self.exists

    def focus_set(self):
        self.focused = True

    def destroy(self):
        self.destroyed = True
        self.exists = False


class FakeNotebook(FakeWidget):
    def __init__(self, tabs):
        super().__init__(".nb")
        self._tabs = list(tabs)
        self._selected = self._tabs[0]
        self.selected_calls = []

    def tabs(self):
        return tuple(self._tabs)

    def select(self, tab=None):
        if tab is not None:
            self._selected = str(tab)
            self.selected_calls.append(str(tab))
        return self._selected


def _bare_app():
    app = object.__new__(P.App)
    app.root = FakeRoot()
    pages = [FakeWidget(f".nb.page{i}") for i in range(7)]
    app.nb = FakeNotebook([str(page) for page in pages])
    app.status = FakeWidget(".status", parent=app.root, takefocus="1")
    app.root.widgets = {str(page): page for page in pages}
    app.tab_sort = pages[0]
    app.page = pages[0]
    app._errors = []
    app._fel = lambda exc, where: app._errors.append((exc, where))
    return app, pages


def test_navigation_bindings_cover_tabs_focus_and_escape():
    app, _pages = _bare_app()
    P.App._install_keyboard_navigation(app)
    assert "<Control-Tab>" in app.root.bindings
    assert "<Control-Shift-Tab>" in app.root.bindings
    assert "<Control-ISO_Left_Tab>" in app.root.bindings
    assert all(f"<Control-Key-{i}>" in app.root.bindings for i in range(1, 8))
    assert "<F6>" in app.root.bindings
    assert "<Shift-F6>" in app.root.bindings
    assert "all:<Escape>" in app.root.bindings


def test_control_tab_cycles_forward_and_back_through_visible_tabs():
    app, _pages = _bare_app()
    assert P.App._keyboard_tab_step(app, 1) == "break"
    assert app.nb.select() == ".nb.page1"
    assert P.App._keyboard_tab_step(app, -1) == "break"
    assert app.nb.select() == ".nb.page0"
    app.nb.select(".nb.page0")
    P.App._keyboard_tab_step(app, -1)
    assert app.nb.select() == ".nb.page6"


def test_control_number_selects_one_based_tab_and_ignores_out_of_range():
    app, _pages = _bare_app()
    P.App._keyboard_tab_number(app, 7)
    assert app.nb.select() == ".nb.page6"
    P.App._keyboard_tab_number(app, 8)
    assert app.nb.select() == ".nb.page6"


def test_escape_closes_focused_dialog_but_never_main_window():
    app, _pages = _bare_app()
    app.root.parent = None
    dialog = FakeWidget(".dialog", parent=app.root, toplevel=True)
    child = FakeWidget(".dialog.entry", parent=dialog)
    app.root.focused = child
    assert P.App._keyboard_escape(app) == "break"
    assert dialog.destroyed

    app.root.focused = app.status
    assert P.App._keyboard_escape(app) is None
    assert app.root.exists


def test_escape_is_safe_when_nothing_has_focus():
    app, _pages = _bare_app()
    assert P.App._keyboard_escape(app) is None


def test_f6_cycles_notebook_content_and_status_in_both_directions():
    app, pages = _bare_app()
    button = FakeWidget(".nb.page0.button", takefocus="ttk::takefocus")
    pages[0].children.append(button)
    button.parent = pages[0]

    app.root.focused = app.nb
    P.App._keyboard_focus_step(app, 1)
    assert button.focused

    app.root.focused = button
    P.App._keyboard_focus_step(app, 1)
    assert app.status.focused

    app.root.focused = app.status
    P.App._keyboard_focus_step(app, 1)
    assert app.nb.focused

    app.nb.focused = False
    app.root.focused = app.nb
    P.App._keyboard_focus_step(app, -1)
    assert app.status.focused


def test_f6_skips_unmapped_and_disabled_controls():
    app, pages = _bare_app()
    hidden = FakeWidget(".hidden", mapped=False, takefocus="1")
    disabled = FakeWidget(".disabled", takefocus="1", state="disabled")
    usable = FakeWidget(".usable", takefocus="1")
    pages[0].children = [hidden, disabled, usable]

    assert P.App._keyboard_first_focusable(app, pages[0]) is usable


def test_real_app_installs_navigation_after_creating_status_line():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    app = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "App")
    init = next(node for node in app.body
                if isinstance(node, ast.FunctionDef) and node.name == "__init__")
    calls = [node for node in ast.walk(init)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr == "_install_keyboard_navigation"]
    assert len(calls) == 1
    install_call = calls[0].lineno
    status_assign = next(node.lineno for node in ast.walk(init)
                         if isinstance(node, ast.Assign)
                         and any(isinstance(target, ast.Attribute)
                                 and target.attr == "status"
                                 for target in node.targets))
    assert install_call > status_assign


def test_keyboard_handlers_never_close_the_root_window():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    app = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "App")
    escape = next(node for node in app.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "_keyboard_escape")
    assert any(isinstance(node, ast.Compare)
               and isinstance(node.left, ast.Name)
               and node.left.id == "top"
               for node in ast.walk(escape))
