from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_category_mapping_has_top_selector_and_requested_two_column_layout():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")

    assert "self.cat_combo = ttk.Combobox(" in source
    assert "mapcard.grid(row=2, column=0" in source
    assert "rightcard.grid(row=2, column=1" in source
    assert "self.default_keyword_combo = ttk.Combobox(" in source
    assert "self.kw_tree.bind(\"<ButtonRelease-1>\", self._cat_map_drag_release" in source


def test_category_mapping_shows_all_words_and_three_folder_drop_views():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")

    assert 'self.subfolder_map_trees = []' in source
    assert 'for map_index in range(3):' in source
    assert 'tree = trees[index % len(trees)]' in source
    assert 'target not in getattr(self, "subfolder_map_trees", ())' in source
    assert 'words = list(cat["keywords"])' in source
    assert 'self.var_kwsearch' not in source
    assert 'text="Sök stödord"' not in source


def test_default_support_word_selector_is_scoped_to_selected_category():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")

    assert "self.var_default_keyword = tk.StringVar()" in source
    assert "cat[\"default_keyword\"] = word" in source
    assert "self._refresh_subfolder_map()" in source
