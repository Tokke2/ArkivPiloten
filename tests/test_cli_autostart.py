# -*- coding: utf-8 -*-
"""CLI-autostarten måste spara inställningen - annars tar GUI-synken bort den."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _env(tmp_path):
    env = dict(os.environ)
    env.update({
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "home" / ".config"),
        "PDFSORTER_HOME": str(tmp_path / "data"),
        "PYTHONPATH": str(ROOT),
        "PYTHONWARNINGS": "ignore",
    })
    (tmp_path / "home").mkdir()
    (tmp_path / "data").mkdir()
    return env


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="testar den riktiga XDG-skrivningen")
def test_cli_install_autostart_persists_and_survives_sync(tmp_path):
    env = _env(tmp_path)
    r = subprocess.run(
        [sys.executable, str(ROOT / "pdfsorter.py"), "--install-autostart"],
        env=env, capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, r.stderr + r.stdout

    settings = json.loads(
        (tmp_path / "data" / "json" / "settings.json").read_text(encoding="utf-8"))
    assert settings["autostart"] is True
    desktop = tmp_path / "home" / ".config" / "autostart" / "arkivpiloten.desktop"
    assert desktop.is_file()

    # Simulera GUI:ts självläkande synk vid nästa start.
    code = (
        "import pathlib, pdfsorter_data as D, pdfsorter_system as S;"
        "S.configure(config_dir=D.config_dir, now_iso=D.now_iso,"
        f" main_script=pathlib.Path({str(ROOT / 'pdfsorter.py')!r}));"
        "print(S.sync_autostart(D.load_settings()['autostart']))")
    r2 = subprocess.run([sys.executable, "-c", code], env=env,
                        capture_output=True, text=True, timeout=60)
    assert r2.returncode == 0, r2.stderr + r2.stdout
    assert "synk" in r2.stdout
    assert desktop.is_file(), "GUI-synken tog bort CLI-autostarten"

    r3 = subprocess.run(
        [sys.executable, str(ROOT / "pdfsorter.py"), "--remove-autostart"],
        env=env, capture_output=True, text=True, timeout=90)
    assert r3.returncode == 0, r3.stderr + r3.stdout
    assert not desktop.exists()
    settings = json.loads(
        (tmp_path / "data" / "json" / "settings.json").read_text(encoding="utf-8"))
    assert settings["autostart"] is False
