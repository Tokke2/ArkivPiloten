# -*- coding: utf-8 -*-
"""Målsökvägen ska synas i granskningsdialogen före bekräftelse."""
import pdfsorter as P


def test_preview_joins_base_subfolder_and_filename(tmp_path):
    base = tmp_path / "Arkiv" / "Handelsbanken" / "2026"

    dest = P.preview_destination_path(base, "Utbetalningar", "kv.pdf")

    assert dest == base / "Utbetalningar" / "kv.pdf"


def test_preview_supports_nested_subfolders_and_empty_choice(tmp_path):
    base = tmp_path / "Arkiv"

    assert P.preview_destination_path(base, "A/B", "x.pdf") == base / "A" / "B" / "x.pdf"
    assert P.preview_destination_path(base, "", "x.pdf") == base / "x.pdf"


def test_preview_rejects_unsafe_subfolders_but_keeps_base(tmp_path):
    base = tmp_path / "Arkiv"

    assert P.preview_destination_path(base, "../utanfor", "x.pdf") == base / "x.pdf"
    assert P.preview_destination_path(base, "/absolut", "x.pdf") == base / "x.pdf"


def test_preview_returns_none_without_base_and_dir_without_filename(tmp_path):
    assert P.preview_destination_path(None, "A", "x.pdf") is None
    assert P.preview_destination_path(tmp_path, "A", "") == tmp_path / "A"


def test_review_dialog_shows_destination_preview():
    import inspect

    source = inspect.getsource(P.ReviewDialog.__init__)
    assert "self.lbl_destination" in source
    assert "trace_add" in source
    assert callable(P.ReviewDialog._update_destination_preview)
