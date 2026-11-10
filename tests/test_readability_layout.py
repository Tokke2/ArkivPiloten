from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pdfsorter_read as R


def test_ocr_reconstructs_lines_and_paragraphs():
    data = {
        "text": ["INVOICE", "number", "1042", "Northwind", "Services"],
        "conf": ["91", "88", "96", "89", "92"],
        "block_num": [1, 1, 1, 2, 2],
        "par_num": [1, 1, 1, 1, 1],
        "line_num": [1, 1, 1, 1, 1],
        "word_num": [1, 2, 3, 1, 2],
    }

    class FakeTesseract:
        Output = SimpleNamespace(DICT="dict")

        @staticmethod
        def image_to_data(_image, **_kwargs):
            return data

        @staticmethod
        def image_to_string(_image, **_kwargs):
            raise AssertionError("text fallback should not be used")

    confidence, text = R._ocr_pass(None, "eng", "--psm 3", FakeTesseract)
    assert confidence == 91.2
    assert text == "INVOICE number 1042\n\nNorthwind Services"


def test_review_dialog_opens_long_ocr_details_separately():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")
    assert 'text="Visa resultat per sida…"' in source
    assert '"\\n\\n".join(details)' in source
    assert "def _show_ocr_details(self)" in source


def test_review_dialog_places_keywords_left_and_decision_controls_right():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")
    assert "self._all.columnconfigure(0, weight=1, uniform=\"review-columns\")" in source
    assert "head.grid(row=0, column=1" in source
    assert "box.grid(row=0, column=0, rowspan=row_box + 1" in source
    assert "catbox.grid(row=row_box, column=1" in source
    assert "_fit_geometry(self.win, 1280, 900, 1000, 680)" in source
    assert "wide = self._outer.winfo_width() >= 980" in source
    assert "columnspan=2" in source
    assert "height = max(140, min(440, self.win.winfo_height() - 420))" in source
    assert "command=self._outer.yview" in source
