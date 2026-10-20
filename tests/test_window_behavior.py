# -*- coding: utf-8 -*-
"""Fönsterbeteende: minimering och krysset är två olika saker.

Tidigare styrde close_to_tray (krysset) även minimering, så ett tryck på
minimera-knappen gömde fönstret i systemfältet trots att inställningen
lovade något annat. Testerna låser att minimering stannar i
aktivitetsfältet som standard och bara går till systemfältet när
minimize_to_tray är påslaget och ikonen finns.
"""
from __future__ import annotations

import pdfsorter as P
import pdfsorter_data as D


def test_default_settings_keep_minimize_in_taskbar():
    assert D.DEFAULT_SETTINGS["minimize_to_tray"] is False
    assert D.DEFAULT_SETTINGS["close_to_tray"] is True


def test_minimize_stays_in_taskbar_by_default():
    assert P._minimize_action("iconic", {}, True) == "taskbar"
    # Ett gammalt settings-dict utan nyckeln ska också stanna i taskbar.
    assert P._minimize_action("iconic", {"close_to_tray": True},
                              True) == "taskbar"


def test_minimize_goes_to_tray_when_enabled():
    assert P._minimize_action("iconic", {"minimize_to_tray": True},
                              True) == "tray"


def test_minimize_to_tray_requires_a_tray_icon():
    assert P._minimize_action("iconic", {"minimize_to_tray": True},
                              False) == "taskbar"


def test_only_a_real_minimize_is_handled():
    for state in ("normal", "withdrawn", "zoomed", ""):
        assert P._minimize_action(state, {"minimize_to_tray": True},
                                  True) == "none"


def test_close_to_tray_does_not_affect_minimize():
    settings = {"close_to_tray": True, "minimize_to_tray": False}
    assert P._minimize_action("iconic", settings, True) == "taskbar"
    settings = {"close_to_tray": False, "minimize_to_tray": True}
    assert P._minimize_action("iconic", settings, True) == "tray"
