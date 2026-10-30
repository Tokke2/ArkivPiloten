#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bygg releasepaketet som appens autouppdatering hämtar.

Paketet innehåller exakt filerna i pdfsorter_system.UPDATE_FILES, med
pdfsorter.py i roten, plus en SHA256SUMS.txt. GitHub-arbetsflödet
(.github/workflows/release.yml) publicerar paketet som en release så
fort main uppdateras, så att "Sök efter uppdateringar" alltid hittar
den senaste koden.

    python tools/build_release.py                 # -> dist/
    python tools/build_release.py --bump patch    # höj versionen först
    python tools/build_release.py --bump minor

Bumpen ändrar versionen i alla sex modulerna och i README, men gör
ingen commit - granska och committa själv.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdfsorter_system import (  # noqa: E402
    UPDATE_ASSET_NAME,
    UPDATE_CONTENT_FILES,
    UPDATE_FILES,
    UPDATE_MANIFEST_NAME,
    UPDATE_SUMS_NAME,
)

MODULES = ("pdfsorter.py", "pdfsorter_data.py", "pdfsorter_read.py",
           "pdfsorter_system.py", "pdfsorter_theme.py", "pdfsorter_diag.py")
_VERSION_RE = re.compile(r'((?:APP_)?VERSION\s*=\s*")(\d+\.\d+\.\d+)(")')


def read_versions(root: pathlib.Path = ROOT) -> dict:
    """Läs versionssträngen ur varje modul (APP_VERSION eller VERSION)."""
    versions = {}
    for namn in MODULES:
        text = (root / namn).read_text(encoding="utf-8")
        m = _VERSION_RE.search(text)
        if not m:
            raise SystemExit(f"Hittar ingen version i {namn}")
        versions[namn] = m.group(2)
    return versions


def app_version(root: pathlib.Path = ROOT) -> str:
    versions = read_versions(root)
    unika = set(versions.values())
    if len(unika) != 1:
        raise SystemExit("Modulerna har olika version: " + ", ".join(
            f"{k}={v}" for k, v in versions.items()))
    return unika.pop()


def bump_version(part: str = "patch", root: pathlib.Path = ROOT) -> str:
    """Höj versionen i alla moduler + README och returnera den nya."""
    nu = app_version(root)
    major, minor, patch = (int(x) for x in nu.split("."))
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    ny = f"{major}.{minor}.{patch}"
    for namn in MODULES:
        p = root / namn
        text = p.read_text(encoding="utf-8")
        text, antal = _VERSION_RE.subn(rf"\g<1>{ny}\g<3>", text, count=1)
        if not antal:
            raise SystemExit(f"Kunde inte höja versionen i {namn}")
        p.write_text(text, encoding="utf-8")
    readme = root / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        text = re.sub(r"(PDF Sorter\s+)\d+\.\d+\.\d+", rf"\g<1>{ny}", text)
        text = re.sub(r"(ArkivPiloten\s+)\d+\.\d+\.\d+", rf"\g<1>{ny}", text)
        readme.write_text(text, encoding="utf-8")
    return ny


def build(outdir: pathlib.Path = ROOT / "dist",
          root: pathlib.Path = ROOT) -> dict:
    """Skapa zip + SHA256SUMS.txt och returnera metadata."""
    version = app_version(root)
    outdir.mkdir(parents=True, exist_ok=True)
    zip_path = outdir / UPDATE_ASSET_NAME
    saknade = [n for n in UPDATE_CONTENT_FILES if not (root / n).is_file()]
    if saknade:
        raise SystemExit("Saknade filer: " + ", ".join(saknade))

    file_hashes = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in UPDATE_CONTENT_FILES
    }
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = ""
    manifest = {
        "schema": 1,
        "version": version,
        "tag": f"v{version}",
        "commit": commit,
        "files": file_hashes,
    }
    manifest_path = outdir / UPDATE_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for namn in UPDATE_CONTENT_FILES:
            zf.write(root / namn, arcname=namn)
        zf.write(manifest_path, arcname=UPDATE_MANIFEST_NAME)

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sums = outdir / UPDATE_SUMS_NAME
    sums.write_text(f"{digest}  {UPDATE_ASSET_NAME}\n", encoding="utf-8")
    meta = {
        "version": version,
        "tag": f"v{version}",
        "asset": zip_path.name,
        "zip": str(zip_path),
        "sums": str(sums),
        "sha256": digest,
        "commit": commit,
        "manifest": str(manifest_path),
        "manifest_data": manifest,
        "files": list(UPDATE_FILES),
    }
    (outdir / "release.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "dist"),
                        help="mapp för zip + SHA256SUMS.txt (standard: dist/)")
    parser.add_argument("--bump", choices=("patch", "minor", "major"),
                        help="höj versionen i alla moduler före bygget")
    args = parser.parse_args(argv)

    if args.bump:
        ny = bump_version(args.bump)
        print(f"Version höjd till {ny} - committa ändringen och publicera.")
    meta = build(pathlib.Path(args.out))
    print(f"Byggt: {meta['zip']}  ({meta['version']})")
    print(f"SHA-256: {meta['sha256']}")
    print(f"Summor: {meta['sums']}")
    print("\nPublicera (görs automatiskt av .github/workflows/release.yml "
          "när main uppdateras):")
    print(f"  gh release create {meta['tag']} {meta['zip']} "
          f"{meta['sums']} --title 'ArkivPiloten {meta['version']}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
