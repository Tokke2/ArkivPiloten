# -*- coding: utf-8 -*-
"""Datamappens läge: portabelt, overridat eller användarmapp."""
from __future__ import annotations

import pdfsorter_data as D


def _reset(monkeypatch):
    D._CONFIG_DIR_CACHE.clear()
    monkeypatch.setattr(D, "_JSON_DIR_CACHE", None, raising=False)
    monkeypatch.setattr(D, "_JSON_FLYTTAD", False, raising=False)


def test_writable_app_dir_stays_portable(tmp_path, monkeypatch):
    _reset(monkeypatch)
    app = tmp_path / "app"
    app.mkdir()
    monkeypatch.setattr(D, "_app_dir", lambda: app)
    monkeypatch.setattr(D, "_skrivbar", lambda p: True)
    monkeypatch.delenv("PDFSORTER_HOME", raising=False)
    assert D.config_dir() == app
    assert D.config_dir_mode() == "portable"


def test_readonly_app_dir_uses_user_data_dir(tmp_path, monkeypatch):
    """Systeminstallation (/Applications, /opt) måste kunna spara data."""
    _reset(monkeypatch)
    app = tmp_path / "app"
    app.mkdir()
    monkeypatch.setattr(D, "_app_dir", lambda: app)
    monkeypatch.setattr(D, "_skrivbar", lambda p: False)
    monkeypatch.delenv("PDFSORTER_HOME", raising=False)
    assert D.config_dir() == D._os_config_dir()
    assert D.config_dir_mode() == "user"
    assert D.config_dir().is_dir()


def test_pdfsorter_home_wins(tmp_path, monkeypatch):
    _reset(monkeypatch)
    app = tmp_path / "app"
    app.mkdir()
    data = tmp_path / "data"
    monkeypatch.setattr(D, "_app_dir", lambda: app)
    monkeypatch.setattr(D, "_skrivbar", lambda p: True)
    monkeypatch.setenv("PDFSORTER_HOME", str(data))
    assert D.config_dir() == data
    assert D.config_dir_mode() == "override"
    assert data.is_dir()
    assert D.json_dir().is_dir()
