# -*- coding: utf-8 -*-
"""Stäng och minimera till systemfältet, med dialogskydd."""
from __future__ import annotations

import ast
from pathlib import Path

import pdfsorter as P
import pdfsorter_data as D

ROOT = Path(__file__).resolve().parents[1]


def test_defaults_show_manual_start_but_keep_os_autostart():
    assert D.DEFAULT_SETTINGS["autostart"] is True
    assert D.DEFAULT_SETTINGS["start_minimized"] is False
    assert D.DEFAULT_SETTINGS["tray_enabled"] is True
    assert D.DEFAULT_SETTINGS["close_to_tray"] is True
    assert D.DEFAULT_SETTINGS["minimize_to_tray"] is True


def test_minimize_goes_to_tray_by_default_and_for_legacy_missing_key():
    assert P._minimize_action("iconic", {}, True) == "tray"
    assert P._minimize_action("iconic", {"close_to_tray": True},
                              True) == "tray"


def test_minimize_stays_in_taskbar_if_user_turns_it_off():
    assert P._minimize_action("iconic", {"minimize_to_tray": False},
                              True) == "taskbar"


def test_minimize_to_tray_requires_a_tray_icon():
    assert P._minimize_action("iconic", {"minimize_to_tray": True},
                              False) == "taskbar"


def test_modal_review_dialog_keeps_window_in_taskbar():
    assert P._minimize_action("iconic", {"minimize_to_tray": True},
                              True, modal_open=True) == "taskbar"


def test_active_sort_restores_window_instead_of_minimizing():
    assert P._minimize_action("iconic", {"minimize_to_tray": True},
                              True, busy=True) == "restore"


def test_only_a_real_minimize_is_handled():
    for state in ("normal", "withdrawn", "zoomed", ""):
        assert P._minimize_action(state, {"minimize_to_tray": True},
                                  True) == "none"


def test_close_and_minimize_settings_remain_independent():
    assert P._minimize_action(
        "iconic", {"close_to_tray": True, "minimize_to_tray": False},
        True) == "taskbar"
    assert P._minimize_action(
        "iconic", {"close_to_tray": False, "minimize_to_tray": True},
        True) == "tray"


def test_existing_settings_are_migrated_to_tray_for_both_actions_once():
    settings = {
        "tray_enabled": False,
        "close_to_tray": False,
        "minimize_to_tray": False,
    }
    assert D._migrate_tray_behavior(settings)
    assert settings["tray_enabled"] is True
    assert settings["close_to_tray"] is True
    assert settings["minimize_to_tray"] is True
    assert settings["tray_minimize_migrated_v1"] is True


def test_user_can_change_tray_choices_after_one_time_migration():
    settings = {
        "tray_enabled": True,
        "close_to_tray": False,
        "minimize_to_tray": False,
        "tray_minimize_migrated_v1": True,
    }
    assert not D._migrate_tray_behavior(settings)
    assert settings["close_to_tray"] is False
    assert settings["minimize_to_tray"] is False


def test_autostart_minimized_migration_is_one_time():
    settings = {"autostart": False, "start_minimized": False,
                "tray_enabled": False}
    assert D._migrate_autostart_minimized(settings)
    assert settings["autostart"] is True
    assert settings["start_minimized"] is True
    assert settings["tray_enabled"] is True
    assert settings["autostart_minimized_migrated_v1"] is True
    settings["autostart"] = False
    settings["start_minimized"] = False
    assert not D._migrate_autostart_minimized(settings)
    assert settings["autostart"] is False
    assert settings["start_minimized"] is False


def test_manual_start_visible_migration_is_one_time():
    settings = {"start_minimized": True}
    assert D._migrate_manual_start_visible(settings)
    assert settings["start_minimized"] is False
    assert settings["manual_start_visible_migrated_v1"] is True
    settings["start_minimized"] = True
    assert not D._migrate_manual_start_visible(settings)
    assert settings["start_minimized"] is True


def test_upgrade_from_autostart_minimized_release_keeps_os_start_but_shows_manual():
    settings = {"autostart": True, "start_minimized": True,
                "autostart_minimized_migrated_v1": True}
    assert not D._migrate_autostart_minimized(settings)
    assert D._migrate_manual_start_visible(settings)
    assert settings["autostart"] is True
    assert settings["start_minimized"] is False


def test_load_settings_persists_one_time_startup_migrations(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSORTER_HOME", str(tmp_path / "data"))
    D._CONFIG_DIR_CACHE.clear()
    monkeypatch.setattr(D, "_JSON_DIR_CACHE", None)
    monkeypatch.setattr(D, "_JSON_FLYTTAD", False)
    old = dict(D.DEFAULT_SETTINGS)
    old.update({"tray_enabled": False, "close_to_tray": False,
                "minimize_to_tray": False, "autostart": False,
                "start_minimized": False,
                "tray_minimize_migrated_v1": False,
                "autostart_minimized_migrated_v1": False,
                "manual_start_visible_migrated_v1": False})
    D.save_settings(old)

    migrated = D.load_settings()
    assert migrated["tray_enabled"] is True
    assert migrated["close_to_tray"] is True
    assert migrated["minimize_to_tray"] is True
    assert migrated["tray_minimize_migrated_v1"] is True
    assert migrated["autostart"] is True
    assert migrated["start_minimized"] is False
    assert migrated["autostart_minimized_migrated_v1"] is True
    assert migrated["manual_start_visible_migrated_v1"] is True

    migrated.update({"close_to_tray": False, "minimize_to_tray": False,
                     "autostart": False, "start_minimized": False})
    D.save_settings(migrated)
    later = D.load_settings()
    assert later["close_to_tray"] is False
    assert later["minimize_to_tray"] is False
    assert later["autostart"] is False
    assert later["start_minimized"] is False


def test_app_wires_autostart_sync_and_minimized_start():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    app = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "App")
    init = next(node for node in app.body
                if isinstance(node, ast.FunctionDef) and node.name == "__init__")
    text = ast.unparse(init)
    assert "sync_autostart(vill)" in text
    assert "start_minimized" in text
    assert "get('start_minimized', False)" in text
    assert "hide_window" in text
