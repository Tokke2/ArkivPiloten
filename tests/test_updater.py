# -*- coding: utf-8 -*-
"""Autouppdateringen: GitHub Releases, SHA-256, zip-slip och rollback.

Inga nätverksanrop görs - _http_get/_ladda_ner byts ut mot fixturer.
"""
from __future__ import annotations

import hashlib
import io
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


def _same_version_manifest(tmp_path, monkeypatch, commit="a" * 40):
    import hashlib

    root = tmp_path / "same-version-app"
    root.mkdir()
    main = root / "pdfsorter.py"
    monkeypatch.setattr(S, "_main_script", main)
    hashes = {}
    for name in S.UPDATE_CONTENT_FILES:
        path = root / name
        if name == "pdfsorter.py":
            data = f'APP_VERSION = "{S.APP_VERSION}"\nOLD = True\n'.encode()
        elif name.endswith(".py"):
            data = f"# local test content: {name}\n".encode()
        else:
            data = f"local test content: {name}\n".encode()
        path.write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    manifest = {"schema": 1, "version": S.APP_VERSION,
                "tag": f"v{S.APP_VERSION}", "commit": commit,
                "files": hashes}
    (root / S.UPDATE_MANIFEST_NAME).write_text(
        json.dumps(manifest), encoding="utf-8")
    return manifest


def _payload_with_manifest(manifest):
    payload = _release_payload(version=manifest["version"])
    payload["body"] = (
        "Paket byggt från `" + manifest["commit"][:12] + "`.\n"
        "<!-- ARKIVPILOTEN_BUILD_MANIFEST_BEGIN\n"
        + json.dumps(manifest)
        + "\nARKIVPILOTEN_BUILD_MANIFEST_END -->")
    return payload


def test_same_version_release_with_identical_commit_and_files_is_current(
        tmp_path, monkeypatch):
    manifest = _same_version_manifest(tmp_path, monkeypatch)
    payload = json.dumps(_payload_with_manifest(manifest)).encode()
    monkeypatch.setattr(S, "_http_get", lambda *a, **k: payload)

    info = S.check_for_update()
    assert info["ok"]
    assert info["remote"] == S.APP_VERSION
    assert info["available"] is False
    assert info["changed_files"] == []


def test_same_version_release_detects_changed_files_and_commit(
        tmp_path, monkeypatch):
    manifest = _same_version_manifest(tmp_path, monkeypatch)
    remote = json.loads(json.dumps(manifest))
    remote["commit"] = "b" * 40
    remote["files"]["README.md"] = hashlib.sha256(
        b"changed on release\n").hexdigest()
    payload = json.dumps(_payload_with_manifest(remote)).encode()
    monkeypatch.setattr(S, "_http_get", lambda *a, **k: payload)

    info = S.check_for_update()
    assert info["ok"]
    assert info["available"]
    assert info["build_update"]
    assert info["changed_files"] == ["README.md"]
    assert info["release_commit"] == "b" * 40


def test_legacy_same_version_release_is_compared_from_verified_zip(
        tmp_path, monkeypatch):
    _same_version_manifest(tmp_path, monkeypatch)
    root = tmp_path / "same-version-app"
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in S.UPDATE_CONTENT_FILES:
            zf.write(root / name, arcname=name)
    package = archive_bytes.getvalue()
    digest = hashlib.sha256(package).hexdigest()
    payload = _release_payload(version=S.APP_VERSION)
    payload["body"] = "Paket byggt från `" + ("b" * 12) + "`."
    payload["assets"][0]["digest"] = "sha256:" + digest
    payload_bytes = json.dumps(payload).encode()
    calls = []
    monkeypatch.setattr(S, "_config_dir_fn", lambda: tmp_path / "config")

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        if url == S.UPDATE_RELEASES_LATEST:
            return payload_bytes
        if url.endswith(S.UPDATE_ASSET_NAME):
            return package
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(S, "_http_get", fake_get)
    first = S.check_for_update()
    assert first["ok"] and first["available"]
    assert first["build_update"]
    assert first["changed_files"] == []
    assert first["release_commit"] == "b" * 12

    second = S.check_for_update()
    assert second["available"]
    assert calls.count(payload["assets"][0]["browser_download_url"]) == 1


def test_same_version_build_is_installed_when_file_hashes_change(
        tmp_path, monkeypatch):
    local_manifest = _same_version_manifest(tmp_path, monkeypatch)
    root = tmp_path / "same-version-app"
    remote_manifest = json.loads(json.dumps(local_manifest))
    remote_manifest["commit"] = "c" * 40
    files = dict(remote_manifest["files"])
    contents = {}
    for name in S.UPDATE_CONTENT_FILES:
        data = (root / name).read_bytes()
        if name == "README.md":
            data = b"updated README on same version\n"
        contents[name] = data
        files[name] = hashlib.sha256(data).hexdigest()
    remote_manifest["files"] = files

    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in contents.items():
            zf.writestr(name, data)
        zf.writestr(S.UPDATE_MANIFEST_NAME, json.dumps(remote_manifest))
    package = archive_bytes.getvalue()
    digest = hashlib.sha256(package).hexdigest()
    payload = _payload_with_manifest(remote_manifest)
    payload["assets"][0]["digest"] = "sha256:" + digest
    payload_bytes = json.dumps(payload).encode()
    sums_text = f"{digest}  {S.UPDATE_ASSET_NAME}\n".encode()

    def fake_get(url, *args, **kwargs):
        if url == S.UPDATE_RELEASES_LATEST:
            return payload_bytes
        if url.endswith(S.UPDATE_SUMS_NAME):
            return sums_text
        if url.endswith(S.UPDATE_ASSET_NAME):
            return package
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(S, "_http_get", fake_get)
    monkeypatch.setattr(
        S, "_ladda_ner", lambda url, dest, timeout=180: pathlib.Path(dest).write_bytes(package))
    ok, msg = S.perform_update(root=root)
    assert ok, msg
    assert "Uppdaterat bygge" in msg
    assert (root / "README.md").read_bytes() == contents["README.md"]
    installed = json.loads((root / S.UPDATE_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert installed["commit"] == "c" * 40


def test_release_without_checksum_is_reported(monkeypatch):
    payload = json.dumps(_release_payload(with_sums=False)).encode()
    monkeypatch.setattr(S, "_http_get", lambda *a, **k: payload)
    info = S.check_for_update()
    assert info["source"] == "release"
    assert info["sha256_url"] == ""
    assert info["sha256"] == ""
    # Utan kontrollsumma får release-paketet inte installeras.
    ok, msg = S.perform_update(root=pathlib.Path("/tmp"))
    assert ok is False
    assert "kontrollsumma" in msg.lower()


def test_checksum_in_release_notes_uses_tag_archive(monkeypatch):
    """Release utan bifogade filer: tagg-arkivet + SHA-256 i texten."""
    digest = "c" * 64
    payload = _release_payload(with_sums=False)
    payload["assets"] = []
    payload["body"] = f"Paketet verifieras.\nSHA256 (ArkivPiloten-1.4.1.zip): {digest}\n"
    monkeypatch.setattr(S, "_http_get", lambda *a, **k: json.dumps(payload).encode())
    info = S.check_for_update()
    assert info["source"] == "release"
    assert info["sha256"] == digest
    assert info["zip_url"] == (
        f"https://codeload.github.com/{S.UPDATE_REPO}/zip/refs/tags/v9.9.9")


def test_no_branch_fallback(monkeypatch):
    """Svarar GitHub Releases inte ska INGEN gren användas.

    Tidigare föll appen tillbaka på main och laddade ner grenens zip. Det
    gjorde uppdateringen omöjlig att verifiera (ingen publicerad summa)
    och band appen till main. Nu: ok=False, inget erbjuds, och ingen
    begäran får gå till raw.githubusercontent eller codeload/main.
    """
    anropade = []

    def fake_get(url, *a, **k):
        anropade.append(url)
        raise OSError("API nere")

    monkeypatch.setattr(S, "_http_get", fake_get)
    info = S.check_for_update()
    assert info["ok"] is False
    assert info["available"] is False
    assert info["source"] == "release"
    assert "error" in info
    assert anropade == [S.UPDATE_RELEASES_LATEST], anropade
    assert not any("codeload" in u or "raw.githubusercontent" in u
                   for u in anropade)


def test_update_without_release_packet_is_refused(monkeypatch):
    """Release utan paket och utan tagg-arkiv ska inte installeras."""
    payload = _release_payload(with_sums=True)
    payload["assets"] = []
    payload["body"] = ""
    monkeypatch.setattr(S, "_http_get",
                        lambda *a, **k: json.dumps(payload).encode())
    info = S.check_for_update()
    # Taggen finns, så zip_url blir tagg-arkivet - men summan saknas.
    assert info["ok"] is True
    assert info["sha256"] == ""
    ok, msg = S.perform_update(root=pathlib.Path("/tmp"))
    assert ok is False
    assert "kontrollsumma" in msg.lower()


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


def test_update_accepts_checksum_from_release_notes(monkeypatch, tmp_path):
    """Release utan bifogad sums: SHA-256 ur release-texten används."""
    root = _root(tmp_path)
    zippath = tmp_path / "tag.zip"
    digest = _make_zip(zippath)
    monkeypatch.setattr(S, "_ladda_ner",
                        lambda url, dest, timeout=900: zippath.replace(dest))
    monkeypatch.setattr(S, "_http_get", lambda *a, **k: b"")
    monkeypatch.setattr(S, "check_for_update", lambda timeout=15: {
        "ok": True, "current": "1.0.0", "remote": "9.9.9", "available": True,
        "source": "release", "tag": "v9.9.9", "sha256_url": "",
        "sha256": digest,
        "zip_url": "https://codeload.github.com/x/y/zip/refs/tags/v9.9.9",
        "release_url": "", "notes": "",
    })
    ok, msg = S.perform_update(root=root)
    assert ok, msg
    assert 'APP_VERSION = "9.9.9"' in (
        root / "pdfsorter.py").read_text(encoding="utf-8")


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


def test_installer_allows_same_version_only_when_build_change_is_verified(tmp_path):
    root = tmp_path / "app"
    staging = tmp_path / "staging"
    root.mkdir(); staging.mkdir()
    (root / "pdfsorter.py").write_text(
        f'APP_VERSION = "{S.APP_VERSION}"\nOLD = True\n', encoding="utf-8")
    (staging / "pdfsorter.py").write_text(
        f'APP_VERSION = "{S.APP_VERSION}"\nNEW = True\n', encoding="utf-8")
    (staging / "README.md").write_text("new build\n", encoding="utf-8")

    ok, msg = S._install_from_folder(staging, root, expected=S.APP_VERSION)
    assert not ok
    assert "inte nyare" in msg

    ok, msg = S._install_from_folder(
        staging, root, expected=S.APP_VERSION, allow_same_version=True)
    assert ok, msg
    assert "Uppdaterat bygge" in msg
    assert "NEW = True" in (root / "pdfsorter.py").read_text(encoding="utf-8")
    assert (root / "README.md").read_text(encoding="utf-8") == "new build\n"


def test_build_release_matches_zip(tmp_path, monkeypatch):
    from tools import build_release

    meta = build_release.build(outdir=tmp_path, root=build_release.ROOT)
    zippath = pathlib.Path(meta["zip"])
    ver = build_release.app_version()
    assert meta["version"] == ver
    with zipfile.ZipFile(zippath) as zf:
        namn = set(zf.namelist())
        assert set(S.UPDATE_FILES) <= namn
        manifest = json.loads(zf.read(S.UPDATE_MANIFEST_NAME))
        assert manifest["version"] == ver
        assert manifest["commit"]
        assert set(manifest["files"]) == set(S.UPDATE_CONTENT_FILES)
        assert zf.read("pdfsorter.py").decode("utf-8").count(
            f'APP_VERSION = "{ver}"') == 1
    digest = hashlib.sha256(zippath.read_bytes()).hexdigest()
    assert digest in pathlib.Path(meta["sums"]).read_text(encoding="utf-8")
