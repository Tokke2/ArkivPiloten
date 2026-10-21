#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Engångsuppgradering till versionen som kan autouppdatera sig.

Bakgrund
--------
1.0.0 och 1.1.0 letade efter uppdateringar i main-grenen i stället för i
GitHub Releases. En sådan installation ser därför aldrig de nya
releaserna - den jämför sig med main, som ligger kvar på 1.1.0, och
tycker att allt är uppdaterat. Från och med 1.4.x läses i stället
/releases/latest, med kontrollsumma och backup.

Det här skriptet byter en gammal installation till den nya koden en enda
gång. Efter det sköter appens egen uppdatering resten. Skriptet rör
aldrig användardata (json/, logs/, backups/ eller egna filer) - bara de
programfiler som releasen innehåller.

    python3 tools/install_latest.py              # hittar appmappen själv
    python3 tools/install_latest.py --root .      # eller ange den
    python3 tools/install_latest.py --dry-run     # visa bara vad som händer

Kräver bara Python 3.8+ och nätverk till github.com.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = "Tokke2/ArkivPiloten"

#: Standardadress: senaste releasen, alltid samma URL oavsett version.
URL_BASE = f"https://github.com/{REPO}/releases/latest/download"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
TAG_ZIP = f"https://codeload.github.com/{REPO}/zip/refs/tags/{{tag}}"

ASSET = "ArkivPiloten.zip"
SUMS = "SHA256SUMS.txt"

#: Exakt de filer en uppdatering får röra. Samma lista som appens
#: autouppdatering använder - allt annat i mappen lämnas i fred.
FILES = (
    "pdfsorter.py", "pdfsorter.pyw", "pdfsorter_data.py",
    "pdfsorter_read.py", "pdfsorter_system.py", "pdfsorter_theme.py",
    "requirements.txt", "install.sh",
    "uppgradera-arkivpiloten.bat", "uppgradera-arkivpiloten.sh",
    "ArkivPiloten.png", "ArkivPiloten.ico",
    "ArkivPiloten - Installera senaste Python och starta.bat",
    "README.md", "PDFSORTER_SPEC.md", "Stöd ArkivPiloten.html",
    "swish_qr.png", "desktop.ini",
)

_VERSION_RE = re.compile(r'(?:APP_)?VERSION\s*=\s*"([0-9][0-9A-Za-z.\-]*)"')


def _log(msg: str) -> None:
    print(msg, flush=True)


def version_tuple(text: str) -> Tuple[int, ...]:
    out: List[int] = []
    for del_ in str(text or "").strip().split("."):
        siffror = "".join(c for c in del_ if c.isdigit())
        out.append(int(siffror) if siffror else 0)
    return tuple(out or [0])


def version_in(root: Path) -> str:
    """Läs versionsnumret ur pdfsorter.py i en mapp ("" om det saknas)."""
    try:
        text = (Path(root) / "pdfsorter.py").read_text(
            encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    m = _VERSION_RE.search(text)
    return m.group(1) if m else ""


def looks_like_app(path: Path) -> bool:
    """Är det här appmappen? Både huvudfilen och systemmodulen ska finnas."""
    p = Path(path)
    return ((p / "pdfsorter.py").is_file()
            and (p / "pdfsorter_system.py").is_file())


def _candidate_bases() -> List[Path]:
    home = Path.home()
    bases = [
        home / "Desktop", home / "Skrivbord",
        home / "Documents", home / "Dokument",
        home / "Downloads", home / "Nedladdningar",
        home / "Applications", home / "Program",
        Path("/Applications"), Path("/opt"),
    ]
    for vara in ("LOCALAPPDATA", "APPDATA"):
        v = os.environ.get(vara)
        if v:
            bases += [Path(v), Path(v) / "Programs", Path(v) / "Program"]
    # Windows: skrivbordet kan ligga i OneDrive
    for vara in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        v = os.environ.get(vara)
        if v:
            bases += [Path(v) / "Desktop", Path(v) / "Skrivbord",
                      Path(v) / "Documents", Path(v) / "Dokument"]
    out, seen = [], set()
    for b in bases:
        try:
            key = str(b.resolve())
        except OSError:
            key = str(b)
        if key not in seen:
            seen.add(key)
            out.append(b)
    return out


def _direct_bases() -> List[Path]:
    """Mappar som prövas först: cwd och skriptets egen mapp (och dess förälder)."""
    return [Path.cwd(), Path(__file__).resolve().parent,
            Path(__file__).resolve().parent.parent]


def find_root(explicit: Optional[str] = None) -> Optional[Path]:
    """Hitta appmappen: given sökväg, skriptets mapp, cwd eller vanliga platser.

    En given sökväg som inte är en appmapp är inget hinder: launchern skickar
    med sin egen mapp (t.ex. Hämtade filer), och då letar vi vidare i stället
    för att ge upp. Ett fel här vore särskilt retligt eftersom hela poängen
    är att det ska gå att dubbelklicka på en nedladdad fil.
    """
    if explicit:
        p = Path(explicit).expanduser()
        if looks_like_app(p):
            return p
        _log(f"Ingen ArkivPiloten-mapp i {p} - letar vidare ...")

    direkta = _direct_bases()
    for d in direkta:
        if looks_like_app(d):
            return d

    # Vanliga platser, högst tre nivåer ned och utan att gå in i tunga
    # systemmappar. Bara exakta appmappar godtas.
    hoppa = {"node_modules", ".git", "venv", ".venv", "__pycache__",
             "site-packages", "Windows", "$Recycle.Bin"}
    for bas in _candidate_bases():
        if not bas.is_dir():
            continue
        if looks_like_app(bas):
            return bas
        for namn in ("ArkivPiloten", "PDF Sorter", "pdfsorter"):
            if looks_like_app(bas / namn):
                return bas / namn
        try:
            barn = [d for d in bas.iterdir()
                    if d.is_dir() and d.name not in hoppa]
        except OSError:
            continue
        for d in barn[:400]:
            if looks_like_app(d):
                return d
            try:
                for d2 in list(d.iterdir())[:200]:
                    if d2.is_dir() and looks_like_app(d2):
                        return d2
            except OSError:
                continue
    return None


def fetch(url: str, timeout: float = 90.0) -> bytes:
    """Hämta en URL. Följer omdirigeringar (GitHub -> release-assets)."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "ArkivPiloten-uppgradering",
                      "Accept": "application/vnd.github+json, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as svar:
        return svar.read()


def latest_tag(timeout: float = 30.0) -> str:
    """Senaste taggen enligt GitHub API ("" om det inte går att läsa)."""
    try:
        import json
        data = json.loads(fetch(API_LATEST, timeout).decode("utf-8", "ignore"))
        return str(data.get("tag_name") or "")
    except Exception:
        return ""


def expected_sha(sums_text: str) -> str:
    """Plocka ut kontrollsumman för paketet ur SHA256SUMS.txt."""
    for rad in str(sums_text or "").splitlines():
        delar = rad.split()
        if len(delar) >= 2 and delar[-1].lstrip("*") == ASSET:
            kandidat = delar[0].lower()
            if re.fullmatch(r"[0-9a-f]{64}", kandidat):
                return kandidat
    return ""


def safe_members(zf: zipfile.ZipFile) -> Dict[str, zipfile.ZipInfo]:
    """Bara kända filer, oavsett om zip:en har en toppmapp eller inte.

    Namnen jämförs mot vitlistan, så en zip kan aldrig skriva utanför
    appmappen (zip-slip) eller lägga dit nya filer.
    """
    out: Dict[str, zipfile.ZipInfo] = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        namn = info.filename.replace("\\", "/")
        bas = namn.rsplit("/", 1)[-1]
        if bas in FILES and bas not in out:
            out[bas] = info
    return out


def extract(zip_bytes: bytes, dest: Path) -> List[str]:
    """Packa upp vitlistade filer till dest. Returnerar namnen."""
    dest.mkdir(parents=True, exist_ok=True)
    skrivna: List[str] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for namn, info in safe_members(zf).items():
            data = zf.read(info)
            if not data:
                continue
            mal = dest / namn
            # Sista skyddsnätet: målet MÅSTE ligga i dest.
            if Path(os.path.abspath(mal)).parent != Path(os.path.abspath(dest)):
                continue
            mal.write_bytes(data)
            skrivna.append(namn)
    return skrivna


def compile_check(folder: Path) -> str:
    """Kompilera alla .py i staging. Returnerar feltext eller "".

    Görs innan något rör appmappen: en trasig release ska aldrig kunna
    installeras.
    """
    for py in sorted(Path(folder).glob("*.py")):
        try:
            compile(py.read_text(encoding="utf-8", errors="replace"),
                    str(py), "exec")
        except (SyntaxError, ValueError) as exc:
            return f"{py.name}: {exc}"
    return ""


def backup(root: Path, stamp: Optional[str] = None) -> Path:
    """Kopiera nuvarande programfiler till backups/upgrade_<tid>/."""
    namn = stamp or time.strftime("%Y%m%d-%H%M%S")
    mal = Path(root) / "backups" / f"upgrade_{namn}"
    mal.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        källa = Path(root) / f
        if källa.is_file():
            shutil.copy2(källa, mal / f)
    return mal


def install(staging: Path, root: Path) -> List[str]:
    """Lägg filerna på plats atomiskt (temp + os.replace)."""
    bytta: List[str] = []
    for namn in FILES:
        källa = Path(staging) / namn
        if not källa.is_file():
            continue
        mal = Path(root) / namn
        tmp = mal.with_name(f".{mal.name}.upgrade-tmp")
        shutil.copy2(källa, tmp)
        os.replace(tmp, mal)
        bytta.append(namn)
    return bytta


def _sha_from_release_body(tag: str) -> str:
    """Reservsumman som release-texten publicerar för tagg-arkivet."""
    try:
        import json
        data = json.loads(fetch(API_LATEST).decode("utf-8", "ignore"))
        body = str(data.get("body") or "")
        m = re.search(r"SHA256 \(ArkivPiloten-[^)]*\.zip\): ([0-9a-f]{64})",
                      body)
        return m.group(1) if m else ""
    except Exception:
        return ""


def _verify(zip_bytes: bytes, väntad: str) -> None:
    faktisk = hashlib.sha256(zip_bytes).hexdigest()
    if faktisk != väntad:
        raise ValueError(f"kontrollsumman stämmer inte (väntade {väntad}, "
                         f"fick {faktisk}) - avbryter")


def _download_release(url_base: str, tag: str) -> Tuple[bytes, str, str]:
    """Hämta paketet och verifiera det. Reserv: GitHubs tagg-arkiv.

    Returnerar (zip-bytes, tagg, källa). Summan är ett krav i båda
    vägarna - utan den installeras ingenting.
    """
    try:
        zip_bytes = fetch(f"{url_base}/{ASSET}")
        sums = fetch(f"{url_base}/{SUMS}").decode("utf-8", "ignore")
    except Exception as exc:
        # Bara när filerna INTE GÅR ATT HÄMTA (brandvägg/proxy) används
        # samma reserv som appen själv: tagg-arkivet, med summan ur
        # release-texten. En fil som hämtats men har fel summa är något
        # annat - då avbryts allt, utan reserv.
        _log(f"  release-filerna gick inte att hämta ({exc}) - "
             "prövar tagg-arkivet")
        if not tag or tag == "senaste":
            tag = latest_tag()
        if not tag:
            raise
        väntad = _sha_from_release_body(tag)
        if not väntad:
            raise ValueError("hittar ingen publicerad kontrollsumma - "
                             "avbryter")
        zip_bytes = fetch(TAG_ZIP.format(tag=tag))
        _verify(zip_bytes, väntad)
        return zip_bytes, tag, "tagg-arkiv"

    väntad = expected_sha(sums)
    if not väntad:
        raise ValueError(f"SHA256SUMS.txt saknar summa för {ASSET} - "
                         "avbryter")
    _verify(zip_bytes, väntad)
    return zip_bytes, tag, "release-fil"


def run(root: Optional[Path], dry_run: bool = False,
        url_base: str = URL_BASE, force: bool = False,
        backup_dir: bool = True, tag: Optional[str] = None) -> int:
    """Hela flödet. Returnerar processens slutkod."""
    if root is None or not looks_like_app(root):
        _log("Hittar ingen ArkivPiloten-mapp (pdfsorter.py + "
             "pdfsorter_system.py).")
        _log("Starta filen från appmappen, eller ange den: "
             "--root \"C:\\sökväg\\ArkivPiloten\"")
        _log("Du kan också dra appmappen till filen och släppa den där.")
        return 1

    root = Path(root)
    nuvarande = version_in(root)
    _log(f"Appmapp: {root}")
    _log(f"Installerad version: {nuvarande or '(okänd)'}")

    tag = tag or latest_tag() or "senaste"
    _log(f"Senaste release på GitHub: {tag}")
    _log("Hämtar paketet ...")
    try:
        zip_bytes, tag, källa = _download_release(url_base, tag)
    except Exception as exc:
        _log(f"Kunde inte hämta ett verifierat paket: {exc}")
        _log("Ingen fil ändrades. Appmappen är orörd.")
        return 1
    _log(f"  {len(zip_bytes)} byte från {källa}, kontrollsumman stämmer")

    with tempfile.TemporaryDirectory(prefix="arkivpiloten-uppg-") as tmp:
        staging = Path(tmp) / "staging"
        filer = extract(zip_bytes, staging)
        if "pdfsorter.py" not in filer:
            _log("Paketet innehåller ingen pdfsorter.py - avbryter.")
            return 1
        ny = version_in(staging)
        _log(f"Ny version: {ny or '(okänd)'}")
        fel = compile_check(staging)
        if fel:
            _log(f"Paketet går inte att köra ({fel}) - avbryter.")
            return 1
        if (nuvarande and ny and not force
                and version_tuple(ny) <= version_tuple(nuvarande)):
            _log(f"Du har redan {nuvarande} - inget att göra.")
            return 2
        if dry_run:
            _log("Torrkörning: inget skrivs. Filerna som skulle bytas:")
            for f in filer:
                _log(f"  {f}")
            return 0

        if backup_dir:
            mal = backup(root)
            _log(f"Backup: {mal}")
        try:
            bytta = install(staging, root)
        except PermissionError as exc:
            _log(f"Kunde inte skriva: {exc}")
            _log("Stäng ArkivPiloten (högerklicka ikonen i systemfältet -> "
                 "Avsluta) och kör igen.")
            return 1
        _log(f"Uppdaterade {len(bytta)} filer.")
        kontroll = version_in(root)
        if kontroll != ny:
            _log(f"Varning: pdfsorter.py anger {kontroll or '?'} efter "
                 f"kopieringen (väntade {ny}).")
            return 1
        _log("")
        _log(f"Klart - ArkivPiloten är nu {ny} och uppdaterar sig själv "
             "via GitHub Releases från och med nu.")
        _log("Starta appen igen. Eventuella extra Python-paket installeras "
             "vid start om de behövs.")
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Uppgradera en gammal ArkivPiloten till versionen som "
                    "autouppdaterar via GitHub Releases.")
    p.add_argument("--root", help="mappen där pdfsorter.py ligger")
    p.add_argument("--dry-run", action="store_true",
                   help="visa vad som skulle göras, ändra inget")
    p.add_argument("--force", action="store_true",
                   help="installera även om versionen inte är nyare")
    p.add_argument("--url-base", default=URL_BASE,
                   help=argparse.SUPPRESS)
    p.add_argument("--tag", default=None, help=argparse.SUPPRESS)
    p.add_argument("--no-backup", action="store_true",
                   help="hoppa över backup (inte rekommenderat)")
    args = p.parse_args(argv)
    try:
        return run(find_root(args.root), dry_run=args.dry_run,
                   url_base=args.url_base, force=args.force,
                   backup_dir=not args.no_backup, tag=args.tag)
    except Exception as exc:
        _log(f"Fel: {type(exc).__name__}: {exc}")
        _log("Ingen fil ändrades. Appmappen är orörd.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
