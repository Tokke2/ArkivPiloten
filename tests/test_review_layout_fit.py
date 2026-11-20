# -*- coding: utf-8 -*-
"""Granskningsdialogen: mappvalet syns utan rullning, fönstret ryms på
skärmen och förhandsvisningen renderas skarpt på HiDPI."""
from __future__ import annotations

from pathlib import Path

import pytest

import pdfsorter as P

ROOT = Path(__file__).resolve().parents[1]


class _DpiWin:
    def __init__(self, dpi):
        self._dpi = dpi

    def winfo_fpixels(self, _spec):
        if isinstance(self._dpi, Exception):
            raise self._dpi
        return self._dpi


def test_preview_zoom_scales_with_display_density():
    assert P._preview_render_zoom(_DpiWin(96.0)) == pytest.approx(1.4)
    assert P._preview_render_zoom(_DpiWin(120.0)) == pytest.approx(1.75)
    assert P._preview_render_zoom(_DpiWin(144.0)) == pytest.approx(2.1)
    assert P._preview_render_zoom(_DpiWin(192.0)) == pytest.approx(2.8)
    # Taket är dubbla baszoomen även på mycket täta skärmar.
    assert P._preview_render_zoom(_DpiWin(288.0)) == pytest.approx(2.8)


def test_preview_zoom_falls_back_to_base_on_bad_values():
    assert P._preview_render_zoom(_DpiWin(RuntimeError("x"))) == pytest.approx(1.4)
    assert P._preview_render_zoom(_DpiWin(0.0)) == pytest.approx(1.4)
    assert P._preview_render_zoom(_DpiWin(-50.0)) == pytest.approx(1.4)


def test_folder_choice_is_placed_above_preview():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")

    assert "row_box, row_sep, row_prev = 1, 2, 3" in source
    assert "catbox.grid(row=row_box, column=1" in source
    assert "prev.grid(row=row_prev, column=1" in source


def test_preview_downscale_uses_sharp_resampling():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")

    assert "resample=Image.LANCZOS" in source


def test_window_maximum_is_clamped_to_the_screen():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")

    assert "win.maxsize(avail_w, avail_h)" in source
