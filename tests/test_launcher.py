# -*- coding: utf-8 -*-
"""Starthjälpen får inte finnas i två olika versioner.

pdfsorter_system.install_helpers() skriver om pdfsorter.pyw när den
inbäddade kopian skiljer sig. Då måste de vara identiska - annars
ändras en spårad fil varje gång appen startar (och fixar som gjorts i
den ena kopian tappas).
"""
from __future__ import annotations

import pathlib

import pdfsorter_system as S

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_embedded_launcher_matches_disk():
    disk = (ROOT / "pdfsorter.pyw").read_text(encoding="utf-8")
    assert S.LAUNCHER_PYW == disk


def test_all_modules_report_same_version():
    import pdfsorter
    import pdfsorter_data
    import pdfsorter_read
    import pdfsorter_theme

    version = pdfsorter.APP_VERSION
    assert version == pdfsorter_data.VERSION
    assert version == pdfsorter_read.VERSION
    assert version == pdfsorter_theme.VERSION
    # pdfsorter_system.APP_VERSION sätts av configure() vid start (och av
    # testfixturerna), så den jämförs mot källfilen i stället.
    kallfil = (ROOT / "pdfsorter_system.py").read_text(encoding="utf-8")
    assert f'APP_VERSION = "{version}"' in kallfil
