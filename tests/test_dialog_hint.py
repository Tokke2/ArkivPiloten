# -*- coding: utf-8 -*-
"""The category search hint explains keyboard search and reset controls."""
from __future__ import annotations

from types import SimpleNamespace

import pdfsorter as P


class _Label:
    def __init__(self):
        self.text = ""

    def configure(self, *, text):
        self.text = text


def _dialog():
    label = _Label()
    return SimpleNamespace(
        _combo_hint_lbl=label,
        _all_categories=["Pilkington", "PARKERINGEN AYGSINN", "Utrymningsplan"],
    ), label


def test_empty_search_hint_explains_type_enter_and_escape():
    dialog, label = _dialog()

    P.ReviewDialog._combo_show_hint(dialog)

    assert label.text == (
        "3 mappar · skriv för att söka; Enter väljer; Esc visar alla.")


def test_active_search_hint_explains_navigation_and_escape():
    dialog, label = _dialog()

    P.ReviewDialog._combo_show_hint(dialog, "pil")

    assert "1 träff" in label.text
    assert "↑/↓ + Enter" in label.text
    assert "Esc visar alla mappar" in label.text
