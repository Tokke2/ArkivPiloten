"""Smart, daglig rensning av den återskapbara PDF-textdiskcachen."""
from __future__ import annotations

import ast
import hashlib
import os
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from pathlib import Path

import pdfsorter as P
import pdfsorter_data as D

ROOT = Path(__file__).resolve().parents[1]


def _entry(cache: P.DiskTextCache, number: int, *, age: float = 0,
           size: int = 8) -> Path:
    path = cache.dir / (hashlib.sha1(str(number).encode()).hexdigest() + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


def _cache(tmp_path) -> P.DiskTextCache:
    cache = P.DiskTextCache()
    cache.dir = tmp_path / "cache"
    return cache


def test_daily_cache_cleanup_defaults_are_enabled_and_persisted():
    assert D.DEFAULT_SETTINGS["cache_cleanup_enabled"] is True
    assert D.DEFAULT_SETTINGS["last_cache_cleanup"] == ""


def test_cleanup_due_uses_a_full_24_hour_interval():
    now = datetime(2026, 10, 27, 12, 0, 0)
    assert P.disk_cache_cleanup_due("", now=now)
    assert P.disk_cache_cleanup_due("bad timestamp", now=now)
    assert not P.disk_cache_cleanup_due(
        (now - timedelta(hours=23, minutes=59)).isoformat(), now=now)
    assert P.disk_cache_cleanup_due(
        (now - timedelta(hours=24)).isoformat(), now=now)
    assert P.disk_cache_cleanup_due(
        (now + timedelta(hours=1)).isoformat(), now=now)


def test_daily_tick_runs_when_due_and_rearms_hourly():
    app = object.__new__(P.App)
    app.settings = {"cache_cleanup_enabled": True, "last_cache_cleanup": ""}
    app._quitting = False
    app.calls = []
    app.root = SimpleNamespace(after=lambda delay, callback:
                               app.calls.append((delay, callback)))
    app._rensa_cache = lambda manual: app.calls.append(("clean", manual))

    P.App._cache_cleanup_tick(app)

    assert ("clean", False) in app.calls
    assert app.calls[-1][0] == 3600000
    assert app.calls[-1][1].__func__ is P.App._cache_cleanup_tick


def test_daily_tick_respects_disabled_setting():
    app = object.__new__(P.App)
    app.settings = {"cache_cleanup_enabled": False, "last_cache_cleanup": ""}
    app._quitting = False
    app.calls = []
    app.root = SimpleNamespace(after=lambda delay, callback:
                               app.calls.append((delay, callback)))
    app._rensa_cache = lambda manual: app.calls.append(("clean", manual))

    P.App._cache_cleanup_tick(app)

    assert not any(call[0] == "clean" for call in app.calls)
    assert app.calls[-1][0] == 3600000


def test_smart_cleanup_removes_expired_entries_and_preserves_recent_and_other_files(
        tmp_path):
    cache = _cache(tmp_path)
    now = time.time()
    old = _entry(cache, 1, age=31 * 86400)
    recent = _entry(cache, 2, age=3 * 86400)
    other = cache.dir / "pip-cache-marker.txt"
    other.write_text("keep", encoding="utf-8")

    result = cache.cleanup(now=now)

    assert not old.exists()
    assert recent.exists()
    assert other.read_text(encoding="utf-8") == "keep"
    assert result["removed_age"] == 1
    assert result["removed_limit"] == 0
    assert result["remaining"] == 1


def test_smart_cleanup_trims_oldest_until_entry_limit(tmp_path, monkeypatch):
    cache = _cache(tmp_path)
    monkeypatch.setattr(cache, "MAX_ENTRIES", 2)
    oldest = _entry(cache, 10, age=300)
    _entry(cache, 11, age=200)
    _entry(cache, 12, age=100)

    result = cache.cleanup(now=time.time())

    assert not oldest.exists()
    assert result["removed_limit"] == 1
    assert result["remaining"] == 2


def test_smart_cleanup_trims_oldest_until_byte_limit(tmp_path, monkeypatch):
    cache = _cache(tmp_path)
    monkeypatch.setattr(cache, "MAX_BYTES", 10)
    oldest = _entry(cache, 20, age=200, size=8)
    _entry(cache, 21, age=100, size=8)

    result = cache.cleanup(now=time.time())

    assert not oldest.exists()
    assert result["removed_limit"] == 1
    assert result["remaining_bytes"] == 8


def test_cache_hit_refreshes_activity_time_so_smart_filter_keeps_it(tmp_path):
    cache = _cache(tmp_path)
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"pdf")
    extraction = P.Extraction(path=source, text="cache text")
    cache.put(source, extraction)
    cache_file = cache.dir / (cache._hash(source) + ".json")
    old = time.time() - 40 * 86400
    os.utime(cache_file, (old, old))

    assert cache.get(source) is not None
    result = cache.cleanup(now=time.time())

    assert cache_file.exists()
    assert result["removed_age"] == 0


def test_corrupt_cache_entry_is_removed_on_read(tmp_path):
    cache = _cache(tmp_path)
    source = tmp_path / "bad.pdf"
    source.write_bytes(b"pdf")
    cache_file = cache.dir / (cache._hash(source) + ".json")
    cache.dir.mkdir(parents=True)
    cache_file.write_text("not JSON", encoding="utf-8")

    assert cache.get(source) is None
    assert not cache_file.exists()


def test_settings_card_exposes_daily_toggle_and_manual_smart_clean_button():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    app = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "App")
    init = next(node for node in app.body
                if isinstance(node, ast.FunctionDef) and node.name == "__init__")
    build = next(node for node in app.body
                 if isinstance(node, ast.FunctionDef) and node.name == "_build_sort_tab")
    collect = next(node for node in app.body
                   if isinstance(node, ast.FunctionDef)
                   and node.name == "_collect_settings")
    assert "_cache_cleanup_tick" in ast.unparse(init)
    build_text = ast.unparse(build)
    assert "cache_cleanup_enabled" in build_text
    assert "Rensa cache nu" in build_text
    assert "_rensa_cache" in build_text
    assert "cache_cleanup_enabled" in ast.unparse(collect)


def test_daily_tick_uses_persisted_time_and_respects_setting():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    app = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "App")
    tick = next(node for node in app.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "_cache_cleanup_tick")
    text = ast.unparse(tick)
    assert "cache_cleanup_enabled" in text
    assert "last_cache_cleanup" in text
    assert "disk_cache_cleanup_due" in text
    assert "_rensa_cache" in text
