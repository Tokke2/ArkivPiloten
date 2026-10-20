# -*- coding: utf-8 -*-
"""Autouppdateringen: GitHub Releases, SHA-256, zip-slip och rollback.

Inga nätverksanrop görs - _http_get/_ladda_ner byts ut mot fixturer.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import zipfile

import pdfsorter_data as D
import pdfsorter_system as S


def test_autoupdate_is_on_by_default():
    assert D.DEFAULT_SETTINGS["auto_update"] is True
    assert D.DEFAULT_SETTINGS["check_updates"] is True


def _release_payload(version="9.9.9", with_sums=True):
    assets = [{
        "name": S.UPDATE_ASSET_NAME,
        "browser_download_url": f"https://example.test/{S.UPDATE_ASSET_NAME}",
    }]
    if with_sums:
        assets.append({
            "name": S.UPDATE_SUMS_NAME,
            "browser_download_url": f"https://example.test/{S.UPDATE_SUMS_NAME}",
        })
    return {
        "tag_name": f"v{version}",
        "draft": False,
        "prerelease": False,
        "html_url": f"https://github.com/{S.UPDATE_REPO}/releases/tag/v{version}",
        "body": "noter",
        "assets": assets,
    }


def test_check_for_update_uses_releases(monkeypatch):
    payload = json.dumps(_release_payload()).encode()
    monkeypatch.setattr(S, "_http_get", lambda *a, **k: payload)
    info = S.check_for_update()
    assert info["ok"] and info["available"]
    assert (info["current"], info["remote"]) == (S.APP_VERSION, "9.9.9")
    assert info["source"] == "release"
    assert info["zip_url"].endswith(S.UPDATE_ASSET_NAME)
    assert info["sha256_url"].endswith(S.UPDATE_SUMS_NAME)


def test_release_without_checksum_is_reported(monkeypatch):
    payload = json.dumps(_release_payload(with_sums=False)).encode()
    monkeypatch.setattr(S, "_http_get", lambda *a, **k: payload)
    info = S.check_for_update()
    assert info["source"] == "release"
    assert info["sha256_url"] == ""


def test_branch_is_the_fallback(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, *a, **k):
        calls["n"] += 1
        if "releases/latest" in url:
            raise OSError("API nere")
        return b'APP_VERSION = "9.9.9"\n'

    monkeypatch.setattr(S, "_http_get", fake_get)
    info = S.check_for_update()
    assert info["source"] == "branch"
    assert info["remote"] == "9.9.9"
    assert info["zip_url"] == S.UPDATE_ZIP_URL


def test_sha_from_sums():
    digest = "a" * 64
    text = (f"{'b'*64}  other.zip\n"
            f"{digest} *ArkivPiloten.zip\n")
    assert S._sha_from_sums(text, ["ArkivPiloten.zip"]) == digest
    assert S._sha_from_sums(text, ["missing.zip"]) is None


def test_safe_extract_blocks_zip_slip(tmp_path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../outside.txt", "x")
        zf.writestr("ok.txt", "x")
    ok, msg = S._safe_extract(evil, tmp_path / "staging")
    assert ok is False
    assert "utanför" in msg
    assert not (tmp_path / "outside.txt").exists()


def _make_zip(path, version="9.9.9", extra=None):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("pdfsorter.py", f'APP_VERSION = "{version}"\n')
        zf.writestr("requirements.txt", "pypdf\n")
        for namn, text in (extra or {}).items():
            zf.writestr(namn, text)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _root(tmp_path, version="1.0.0"):
    root = tmp_path / "app"
    root.mkdir()
    (root / "pdfsorter.py").write_text(f'APP_VERSION = "{version}"\n',
                                      encoding="utf-8")
    return root


def _install_with_checksum(monkeypatch, root, tmp_path, digest=None):
    zippath = tmp_path / "ArkivPiloten.zip"
    real = _make_zip(zippath)
    monkeypatch.setattr(S, "_ladda_ner",
                        lambda url, dest, timeout=900: zippath.replace(dest))
    sums = f"{digest or real}  {S.UPDATE_ASSET_NAME}\n".encode()
    monkeypatch.setattr(S, "_http_get", lambda *a, **k: sums)
    monkeypatch.setattr(S, "check_for_update", lambda timeout=15: {
        "ok": True, "current": S.APP_VERSION, "remote": "9.9.9",
        "available": True, "source": "release",
        "zip_url": f"https://example.test/{S.UPDATE_ASSET_NAME}",
        "sha256_url": "https://example.test/SHA256SUMS.txt",
        "tag": "v9.9.9", "release_url": "", "notes": "",
    })
    return S.perform_update(root=root)


def test_update_installs_verified_package(monkeypatch, tmp_path):
    root = _root(tmp_path)
    ok, msg = _install_with_checksum(monkeypatch, root, tmp_path)
    assert ok, msg
    assert 'APP_VERSION = "9.9.9"' in (
        root / "pdfsorter.py").read_text(encoding="utf-8")
    assert (root / "updates" / "last_update.json").is_file()
    assert list((root / "backups").glob("update_*"))
    assert not (root / "pdfsorter.py.update-tmp").exists()


def test_update_refuses_wrong_checksum(monkeypatch, tmp_path):
    root = _root(tmp_path)
    ok, msg = _install_with_checksum(monkeypatch, root, tmp_path,
                                     digest="0" * 64)
    assert ok is False
    assert "Kontrollsumman" in msg
    assert 'APP_VERSION = "1.0.0"' in (
        root / "pdfsorter.py").read_text(encoding="utf-8")


def test_update_refuses_missing_checksum_entry(monkeypatch, tmp_path):
    root = _root(tmp_path)
    ok, msg = _install_with_checksum(monkeypatch, root, tmp_path)
    assert ok  # kontrollväg: rätt summa installeras

    (tmp_path / "andra").mkdir()
    root2 = _root(tmp_path / "andra", "1.1.0")
    zippath = tmp_path / "x.zip"
    _make_zip(zippath)
    monkeypatch.setattr(
        S, "_http_get",
        lambda *a, **k: f"{'a'*64}  annan.zip\n".encode())
    monkeypatch.setattr(S, "_ladda_ner",
                        lambda url, dest, timeout=900: zippath.replace(dest))
    ok, msg = S.perform_update(root=root2)
    assert ok is False
    assert "saknar paketet" in msg


def test_failed_install_rolls_back(monkeypatch, tmp_path):
    """Går en fil inte att ersätta ska ALLA filer återställas."""
    root = _root(tmp_path)
    (root / "requirements.txt").mkdir()
    (root / "requirements.txt" / "blocker").write_text("x", encoding="utf-8")
    ok, msg = _install_with_checksum(monkeypatch, root, tmp_path)
    assert ok is False
    assert "återställdes" in msg
    assert 'APP_VERSION = "1.0.0"' in (
        root / "pdfsorter.py").read_text(encoding="utf-8")
    assert not list(root.glob("*.update-tmp"))


def test_build_release_matches_zip(tmp_path, monkeypatch):
    from tools import build_release

    meta = build_release.build(outdir=tmp_path, root=build_release.ROOT)
    zippath = pathlib.Path(meta["zip"])
    ver = build_release.app_version()
    assert meta["version"] == ver
    with zipfile.ZipFile(zippath) as zf:
        namn = set(zf.namelist())
        assert set(S.UPDATE_FILES) <= namn
        assert zf.read("pdfsorter.py").decode("utf-8").count(
            f'APP_VERSION = "{ver}"') == 1
    digest = hashlib.sha256(zippath.read_bytes()).hexdigest()
    assert digest in pathlib.Path(meta["sums"]).read_text(encoding="utf-8")
