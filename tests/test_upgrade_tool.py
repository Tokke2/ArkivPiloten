# -*- coding: utf-8 -*-
"""Engångsuppgraderingen (tools/install_latest.py), utan nätverk.

Skriptet är vägen från 1.0.0/1.1.0 (som bara tittade i main-grenen) till
den version som autouppdaterar via Releases. Här prövas hela flödet mot
en lokal "release" på file:// - samma kod som körs hos användaren:

* bara kända filer skrivs (zip-slip och okända filer ignoreras),
* kontrollsumman måste stämma, annars ändras ingenting,
* användardata (json/, logs/) och egna filer rörs aldrig,
* backup tas före, och en trasig release installeras aldrig.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "install_latest", ROOT / "tools" / "install_latest.py")
U = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(U)


@pytest.fixture(autouse=True)
def _ingen_natverk(monkeypatch):
    """Reservvägen (tagg-arkivet) pekas om till en fil som inte finns.

    Testerna ska aldrig nå nätet: en trasig summa ska vara ett fel, inte
    en anledning att hämta något annat.
    """
    monkeypatch.setattr(U, "TAG_ZIP",
                        "file:///finns/inte/{tag}/ArkivPiloten.zip")
    monkeypatch.setattr(U, "latest_tag", lambda timeout=30.0: "")


def _zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for namn, data in files.items():
            zf.writestr(namn, data)
    return buf.getvalue()


def _release(tmp_path, version="1.4.7", extra=None, prefix=""):
    """Bygg en lokal 'release': zip + SHA256SUMS.txt på en file://-adress."""
    filer = {
        "pdfsorter.py": f'APP_VERSION = "{version}"\n',
        "pdfsorter_system.py": f'APP_VERSION = "{version}"\n',
        "pdfsorter_data.py": f'VERSION = "{version}"\n',
        "pdfsorter_read.py": f'VERSION = "{version}"\n',
        "pdfsorter_theme.py": f'VERSION = "{version}"\n',
        "pdfsorter.pyw": "print('start')\n",
        "README.md": "# ArkivPiloten\n",
        "requirements.txt": "PyMuPDF\n",
    }
    filer.update(extra or {})
    data = _zip_bytes({prefix + n: d for n, d in filer.items()})
    zip_path = tmp_path / "release" / U.ASSET
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    (zip_path.parent / U.SUMS).write_text(
        f"{sha}  {U.ASSET}\n", encoding="utf-8")
    return zip_path.parent.as_uri()


def _install(tmp_path, version="1.1.0"):
    """En gammal installation med användardata och egna filer."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "pdfsorter.py").write_text(
        f'APP_VERSION = "{version}"\n', encoding="utf-8")
    (app / "pdfsorter_system.py").write_text(
        f'APP_VERSION = "{version}"\n', encoding="utf-8")
    (app / "min-egen-fil.txt").write_text("rör inte mig\n", encoding="utf-8")
    (app / "json").mkdir()
    (app / "json" / "rules.json").write_text('{"categories": []}',
                                             encoding="utf-8")
    (app / "logs").mkdir()
    (app / "logs" / "senaste.log").write_text("rad\n", encoding="utf-8")
    return app


# -- enkla delar ----------------------------------------------------------
def test_version_in_reads_the_version(tmp_path):
    app = _install(tmp_path, "1.1.0")
    assert U.version_in(app) == "1.1.0"
    assert U.version_in(tmp_path / "finns-inte") == ""


def test_find_root_accepts_a_real_app_folder_and_rejects_others(tmp_path):
    app = _install(tmp_path)
    assert U.find_root(str(app)) == app
    tom = tmp_path / "tom"
    tom.mkdir()
    assert U.find_root(str(tom)) is None


def test_expected_sha_parses_the_sums_file():
    sha = "a" * 64
    assert U.expected_sha(f"{sha}  ArkivPiloten.zip\n") == sha
    assert U.expected_sha(f"{sha} *ArkivPiloten.zip\n") == sha
    assert U.expected_sha("") == ""
    assert U.expected_sha(f"{sha}  något-annat.zip\n") == ""
    assert U.expected_sha("skräp  ArkivPiloten.zip\n") == ""


def test_safe_members_only_returns_known_files():
    data = _zip_bytes({
        "pdfsorter.py": "x",
        "../../ondska.py": "x",
        "okänd.txt": "x",
        "mapp/pdfking.py": "x",
        "ArkivPiloten-1.4.7/pdfsorter.py": "x",
        "ArkivPiloten-1.4.7/README.md": "x",
    })
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        namn = set(U.safe_members(zf))
    assert namn == {"pdfsorter.py", "README.md"}


# -- hela flödet ----------------------------------------------------------
def test_upgrade_replaces_program_files_and_keeps_user_data(tmp_path):
    app = _install(tmp_path)
    url = _release(tmp_path, "1.4.7")
    assert U.run(app, url_base=url, tag="v1.4.7") == 0
    assert U.version_in(app) == "1.4.7"
    # Användardata och egna filer är orörda.
    assert (app / "json" / "rules.json").read_text() == '{"categories": []}'
    assert (app / "logs" / "senaste.log").read_text() == "rad\n"
    assert (app / "min-egen-fil.txt").exists()
    # Backup på den gamla versionen finns.
    backuper = list((app / "backups").glob("upgrade_*"))
    assert backuper, "ingen backup skapades"
    assert U.version_in(backuper[0]) == "1.1.0"


def test_upgrade_ignores_unknown_files_in_the_package(tmp_path):
    app = _install(tmp_path)
    url = _release(tmp_path, "1.4.7", extra={"ondska.py": "print('nej')\n"})
    assert U.run(app, url_base=url, tag="v1.4.7") == 0
    assert not (app / "ondska.py").exists()


def test_upgrade_handles_tag_archive_layout(tmp_path):
    """Tagg-arkivet har en toppmapp - filerna ska ändå hamna rätt."""
    app = _install(tmp_path)
    url = _release(tmp_path, "1.4.7", prefix="ArkivPiloten-1.4.7/")
    assert U.run(app, url_base=url, tag="v1.4.7") == 0
    assert U.version_in(app) == "1.4.7"


def test_same_version_is_a_no_op(tmp_path):
    app = _install(tmp_path, "1.4.7")
    url = _release(tmp_path, "1.4.7")
    assert U.run(app, url_base=url, tag="v1.4.7") == 2
    assert not (app / "backups").exists()


def test_broken_checksum_changes_nothing(tmp_path):
    app = _install(tmp_path)
    url = _release(tmp_path, "1.4.7")
    sums = Path(url[7:]) / U.SUMS
    sums.write_text("0" * 64 + f"  {U.ASSET}\n", encoding="utf-8")
    assert U.run(app, url_base=url, tag="v1.4.7") == 1
    assert U.version_in(app) == "1.1.0"          # orörd
    assert not (app / "backups").exists()


def test_uncompilable_package_is_rejected(tmp_path):
    app = _install(tmp_path)
    url = _release(tmp_path, "1.4.7",
                   extra={"pdfsorter_data.py": "def trasig(:\n"})
    assert U.run(app, url_base=url, tag="v1.4.7") == 1
    assert U.version_in(app) == "1.1.0"


def test_dry_run_changes_nothing(tmp_path):
    app = _install(tmp_path)
    url = _release(tmp_path, "1.4.7")
    assert U.run(app, url_base=url, tag="v1.4.7", dry_run=True) == 0
    assert U.version_in(app) == "1.1.0"
    assert not (app / "backups").exists()


def test_package_without_pdfsorter_py_is_rejected(tmp_path):
    app = _install(tmp_path)
    data = _zip_bytes({"README.md": "# tomt\n"})
    rel = tmp_path / "release"
    rel.mkdir(parents=True, exist_ok=True)
    (rel / U.ASSET).write_bytes(data)
    (rel / U.SUMS).write_text(
        f"{hashlib.sha256(data).hexdigest()}  {U.ASSET}\n", encoding="utf-8")
    assert U.run(app, url_base=rel.as_uri(), tag="v1.4.7") == 1
    assert U.version_in(app) == "1.1.0"


def test_missing_release_files_fall_back_to_tag_archive(tmp_path, monkeypatch):
    """Går filerna inte att hämta används tagg-arkivet - med summa."""
    app = _install(tmp_path)
    arkiv = _release(tmp_path, "1.4.7", prefix="ArkivPiloten-1.4.7/")
    tom = tmp_path / "tom-release"
    tom.mkdir()
    monkeypatch.setattr(U, "TAG_ZIP", arkiv + "/ArkivPiloten.zip")
    monkeypatch.setattr(U, "_sha_from_release_body",
                        lambda tag: U.expected_sha(
                            (tmp_path / "release" / U.SUMS).read_text()))
    assert U.run(app, url_base=tom.as_uri(), tag="v1.4.7") == 0
    assert U.version_in(app) == "1.4.7"


def test_missing_app_folder_gives_a_clear_error(tmp_path, capsys):
    assert U.run(tmp_path / "finns-inte") == 1
    assert "Hittar ingen ArkivPiloten-mapp" in capsys.readouterr().out


@pytest.mark.parametrize("gammal,ny,byter", [
    ("1.1.0", "1.4.7", True),
    ("1.4.7", "1.4.7", False),
    ("1.4.7", "1.4.6", False),
    ("1.10.0", "1.9.9", False),
    ("1.9.9", "1.10.0", True),
])
def test_version_comparison(gammal, ny, byter):
    assert (U.version_tuple(ny) > U.version_tuple(gammal)) is byter
