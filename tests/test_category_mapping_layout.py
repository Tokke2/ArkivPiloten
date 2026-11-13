from pathlib import Path

import pdfsorter as P

ROOT = Path(__file__).resolve().parents[1]


def test_category_mapping_has_top_selector_and_two_role_specific_fields():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")

    assert "self.cat_combo = ttk.Combobox(" in source
    assert "mapcard.grid(row=2, column=1" in source
    assert "rightcard.grid(row=2, column=0" in source
    assert 'self.var_cat_select.trace_add(' in source
    assert '"write", lambda *_args: self._on_cat_select()' in source
    assert "self.default_keyword_combo = ttk.Combobox(" in source
    assert 'cols = ("word", "kind", "weight", "whole", "hits")' in source
    assert 'columns=("folder",), show="headings"' in source
    assert 'text="SPARDA STÖDORD"' in source
    assert 'text="SKAPADE MAPPAR"' in source
    assert 'text="+ Skapa mapp…"' in source
    assert 'text="Öppna kopplingsdialog…"' in source
    assert 'left_frame.grid(row=1, column=0' in source
    assert 'right_frame.grid(row=1, column=1' in source
    assert 'dialog.bind("<Control-m>", assign_selected' in source
    assert source.count("_create_category_mapping_folder(cat,") >= 2


def test_mapping_lists_show_only_created_folders_and_saved_support_words():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")

    assert 'self.subfolder_map_trees = [self.subfolder_map_tree]' in source
    assert 'for map_index in range(3):' not in source
    assert 'tree = trees[index % len(trees)]' not in source
    assert 'words = list(cat["keywords"])' in source
    assert 'self.var_kwsearch' not in source
    assert 'text="Sök stödord"' not in source
    assert 'self.root.bind("<Control-m>", self._cat_map_assign_selected' in source
    assert 'folders.setdefault(value.casefold(), value)' in source
    assert 'mapping.values()' not in source[
        source.index('    def _subfolder_mapping_options('):
        source.index('    def _open_subfolder_keyword_editor(')]


def test_keyboard_action_assigns_multiple_selected_words_to_selected_folder():
    class Tree:
        def __init__(self, selected=(), values=None):
            self.selected = selected
            self.values = values or {}

        def selection(self):
            return self.selected

        def item(self, row, _option):
            return self.values[row]

    class KeywordTree(Tree):
        def set(self, row, _column):
            return self.values[row]

    class Rules:
        def __init__(self):
            self.category = {"subfolder_keyword_map": {}}

        def get(self, _name):
            return self.category

        def save(self):
            pass

    class Label:
        def configure(self, **kwargs):
            self.text = kwargs["text"]

    class Notebook:
        def select(self):
            return "categories"

    app = object.__new__(P.App)
    app.nb = Notebook()
    app.tab_cats = "categories"
    app._selected_cat = lambda: "Supplier"
    app.rules = Rules()
    app.kw_tree = KeywordTree(
        selected=("one", "two"), values={"one": "Invoice", "two": "Amount"})
    app.subfolder_map_trees = [Tree(selected=("folder",), values={
        "folder": ("Invoices",)})]
    app.lbl_subfolder_map_status = Label()
    app._refresh_subfolder_map = lambda: None

    assert P.App._cat_map_assign_selected(app) == "break"
    assert app.rules.category["subfolder_keyword_map"] == {
        "invoice": "Invoices", "amount": "Invoices"}


def test_folder_options_deduplicate_created_folders_across_years(tmp_path):
    output = tmp_path / "Archive"
    for year in ("2024", "2025"):
        (output / "Supplier" / year / "Transaktioner" / "Inbetalningar").mkdir(
            parents=True)
    (output / "Supplier" / "2025" / "Utbetalningar").mkdir(parents=True)

    app = object.__new__(P.App)
    app.settings = {"output_dir": str(output)}
    app._category_subfolder_base = lambda _cat: output / "Supplier" / "2026"
    options = P.App._subfolder_mapping_options(app, {"folder": "Supplier"})

    assert options == ["Transaktioner", "Transaktioner/Inbetalningar", "Utbetalningar"]


def test_uncreated_saved_mapping_targets_are_not_shown(tmp_path):
    output = tmp_path / "Archive"
    (output / "Supplier" / "2025").mkdir(parents=True)
    app = object.__new__(P.App)
    app.settings = {"output_dir": str(output)}
    app._category_subfolder_base = lambda _cat: output / "Supplier" / "2026"

    assert P.App._subfolder_mapping_options(app, {
        "folder": "Supplier",
        "subfolder_keyword_map": {"invoice": "NotCreated"},
    }) == []


def test_folder_creation_makes_a_real_directory_under_category_year(tmp_path):
    output = tmp_path / "Archive"
    app = object.__new__(P.App)
    app.settings = {"output_dir": str(output)}
    app._category_subfolder_base = lambda _cat: output / "Supplier" / "2026"

    folder, error = P.App._create_category_mapping_folder(
        app, {"folder": "Supplier"}, "Invoices/Received")

    assert not error
    assert folder == "Invoices/Received"
    assert (output / "Supplier" / "2026" / "Invoices" / "Received").is_dir()

    rejected, error = P.App._create_category_mapping_folder(
        app, {"folder": "Supplier"}, "../outside")
    assert not rejected and error
    assert not (output / "outside").exists()


def test_default_support_word_selector_is_scoped_to_selected_category():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")

    assert "self.var_default_keyword = tk.StringVar()" in source
    assert "cat[\"default_keyword\"] = word" in source
    assert "self._refresh_subfolder_map()" in source
