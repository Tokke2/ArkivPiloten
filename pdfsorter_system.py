#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdfsorter_system.py — systemintegration för ArkivPiloten.
=======================================================

Hjälpmodul till pdfsorter.py. Här ligger allt som handlar om att appen ska
uppföra sig som ett riktigt skrivbordsprogram, snarare än om själva
sorteringen:

    * Appikonen, ritad i kod så inga bildfiler behövs
    * Autostart med operativsystemet (Windows, macOS, Linux)
    * Skrivbordsgenvägar och starthjälp för dubbelklick
    * Ikonen i systemfältet med snabbmeny
    * Hela användarhjälpen som visas i fliken Hjälp
    * Kraschrapport när appen startas utan terminal

Modulen är fristående och känner inte till sorteringslogiken. Den behöver
bara två saker från huvudfilen, som skickas in via `configure()`:
konfigurationskatalogen och appens namn. Därför kan den importeras och
testas för sig:

    python pdfsorter_system.py --icon ut.png
    python pdfsorter_system.py --help-text
    python pdfsorter_system.py --autostart on

Saknas filen fungerar pdfsorter.py ändå — den faller tillbaka på enkla
ersättare utan ikon och systemfält.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

__all__ = [
    "configure",
    # ikon
    "make_icon_image", "icon_photoimage", "write_icon_file", "ensure_icon_file",
    "brand_window", "set_app_user_model_id",
    # autostart och genvägar
    "autostart_supported", "autostart_enabled", "set_autostart",
    "sync_autostart", "autostart_up_to_date", "autostart_status",
    "effective_autostart",
    "autostart_session_available", "icon_file_path",
    # uppdatering från Git + Python-paket (2026-10-16)
    "check_for_update", "perform_update", "update_python_packages",
    "UPDATE_REPO", "UPDATE_BRANCH", "UPDATE_RELEASES_LATEST",
    "create_desktop_shortcut", "install_helpers",
    # systemfält
    "tray_available", "tray_backend_name", "tray_hidden_start_safe", "TrayIcon",
    # autostart v2.0 + loggverktyg (L3/L5/L7, 2026-09-10)
    "classify_autostart", "get_autostart_conflicts", "LogContext",
    "migrate_legacy_logs", "set_process_dpi_aware",
    "auto_install_tesseract", "TESSERACT_WINGET_ID", "TESSERACT_SETUP_URL",
    "svenska_saknas", "search_tesseract",
    "qr_matrix", "qr_png_bytes", "swish_payload",
    # hjälp
    "HELP_CONTENT", "help_as_text",
    # fel
    "crash_report",
    # sessionslogg (logga allt, REQ-N1)
    "SESSION_ID", "start_session", "session_log", "session_error",
    "session_path", "session_dir", "latest_session_log",
    "install_excepthooks", "close_session",
]

APP_NAME = "ArkivPiloten"
APP_VERSION = "1.4.10"

def _mod_versions_line() -> str:
    """Versioner för alla fem modulerna (felsökning/support)."""
    import importlib
    delar = []
    for namn in ("pdfsorter", "pdfsorter_data", "pdfsorter_read",
                 "pdfsorter_system", "pdfsorter_theme"):
        mod = sys.modules.get(namn)
        if mod is None:
            try:
                mod = importlib.import_module(namn)
            except Exception:
                delar.append(f"{namn}=?")
                continue
        delar.append(f"{namn}={getattr(mod, 'APP_VERSION', getattr(mod, 'VERSION', '?'))}")
    return " ".join(delar)


def _default_config_dir() -> Path:
    """Samma regel som datamodulen: PDFSORTER_HOME vinner, annars appmappen.

    Är appmappen skrivskyddad (t.ex. /Applications, /opt eller en
    paketerad .app) används användarens data-mapp i stället - annars
    kunde appen inte spara regler eller loggar alls på en vanlig
    systeminstallation. Portabel användning är fortfarande förstahandsval.
    """
    env = os.environ.get("PDFSORTER_HOME")
    if env:
        return Path(env).expanduser()
    app = Path(__file__).resolve().parent
    try:
        t = app / ".pdfsorter_write_test"
        t.write_text("ok", encoding="utf-8")
        t.unlink()
        return app
    except OSError:
        pass
    if sys.platform.startswith("win"):
        bas = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(bas) / "ArkivPiloten"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ArkivPiloten"
    bas = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(bas) / "pdfsorter"


#: Sätts av huvudfilen via configure(). Innan dess används en rimlig
#: standard, så att modulen går att köra fristående.
_config_dir_fn: Callable[[], Path] = _default_config_dir
_now_iso_fn: Callable[[], str] = lambda: __import__("datetime").datetime.now(
).astimezone().isoformat(timespec="seconds")

def _guess_main_script() -> Path:
    """Hitta pdfsorter.py, normalt granne med den här filen.

    Autostart och genvägar måste peka på huvudprogrammet, aldrig på
    modulen. configure() skriver över värdet när appen startar på riktigt.
    """
    here = Path(__file__).resolve()
    main = here.with_name("pdfsorter.py")
    return main if main.exists() else here


#: Sökvägen till huvudprogrammet.
_main_script: Path = _guess_main_script()


def configure(config_dir: Callable[[], Path],
              now_iso: Optional[Callable[[], str]] = None,
              main_script: Optional[Path] = None,
              app_name: str = APP_NAME,
              app_version: str = APP_VERSION) -> None:
    """Koppla ihop modulen med huvudprogrammet.

    Anropas en gång vid import från pdfsorter.py. Utan detta använder
    modulen standardvärden, vilket räcker för att köra den fristående.
    """
    global _config_dir_fn, _now_iso_fn, _main_script, APP_NAME, APP_VERSION
    _config_dir_fn = config_dir
    if now_iso:
        _now_iso_fn = now_iso
    if main_script:
        _main_script = Path(main_script).resolve()
    APP_NAME = app_name
    APP_VERSION = app_version


def config_dir() -> Path:
    return _config_dir_fn()


def now_iso() -> str:
    return _now_iso_fn()


# ==========================================================================
# IKON
# ==========================================================================

#: Färgtema för ikonen. Samma blå accent som gränssnittet använder, så att
#: ikonen i systemfältet hör ihop med fönstret den öppnar.
ICON_BG_TOP = (37, 99, 199)        # accent      #2563c7
ICON_BG_BOTTOM = (27, 74, 156)     # accent_dark #1b4a9c
ICON_PAPER = (255, 255, 255)
ICON_INK = (150, 165, 186)         # textrader på bladet
ICON_ACCENT = (214, 60, 55)        # röd PDF-markering
#: De tre målmapparna. Olika kulör betyder olika kategori - det är hela
#: poängen med appen, och det som gör ikonen läsbar när den är 16 punkter.
ICON_TARGETS = ((245, 165, 36), (34, 170, 84), (214, 60, 55))
ICON_ACTIVE = (34, 170, 84)        # grön prick när bevakningen är på

#: Memo-cache: ikonen renderas en gång per (storlek, aktiv, badge) och
#: kopieras sedan - tray-refresh och dialoger slipper rita om i onödan.
#: Tak så att cachen aldrig växer obundet (minimal minnesanvändning).
_ICON_CACHE: Dict[Tuple[int, bool, int], Any] = {}
_ICON_CACHE_MAX = 32


def _rounded_mask(size: int, radius_ratio: float = 0.225):
    from PIL import Image, ImageDraw
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    r = int(size * radius_ratio)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    return mask


def _icon_plate(S: int):
    """Rundad platta med lodrät toning - ikonens botten."""
    from PIL import Image, ImageDraw
    p = Image.new("RGB", (S, S), ICON_BG_TOP)
    d = ImageDraw.Draw(p)
    for y in range(S):
        t = y / (S - 1)
        d.line([(0, y), (S, y)], fill=tuple(
            int(ICON_BG_TOP[i] + (ICON_BG_BOTTOM[i] - ICON_BG_TOP[i]) * t)
            for i in range(3)))
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(p, (0, 0), _rounded_mask(S))
    return img


def _icon_detailed(S: int = 256):
    """Full version: ett PDF-blad som förgrenar sig till tre färgade mappar.

    Motivet är sorteringen själv - ett dokument kommer in, och delas upp i
    kategorier. Det säger mer om vad appen gör än en generisk mapp, och
    de tre kulörerna gör silhuetten igenkännbar även mycket liten.
    """
    from PIL import ImageDraw
    img = _icon_plate(S)
    d = ImageDraw.Draw(img)
    k = S / 256.0                      # allt ritat i 256-koordinater

    def r(x0, y0, x1, y1, radius, fill):
        d.rounded_rectangle([x0 * k, y0 * k, x1 * k, y1 * k],
                            radius=max(1, int(radius * k)), fill=fill)

    # Dokumentet högst upp (samma motiv som master-ikonen ArkivPiloten.png:
    # PDF-blad -> pil -> tre färgade mappar)
    r(92, 18, 164, 104, 12, ICON_PAPER)
    # Vikt hörn uppe till höger
    d.polygon([(140, 18), (164, 42), (140, 42)], fill=(206, 216, 232))
    r(104, 44, 152, 66, 6, ICON_ACCENT)      # rött PDF-band
    r(106, 76, 146, 86, 5, ICON_INK)         # en textrad

    # Nedåtpil: dokumentet delas ut till mapparna
    d.polygon([(120, 104), (136, 104), (136, 122), (146, 122),
               (128, 142), (110, 122), (120, 122)], fill=ICON_PAPER)

    # Förgrening
    r(40, 140, 216, 158, 11, ICON_PAPER)
    for x in (40, 118, 196):
        r(x, 150, x + 20, 178, 9, ICON_PAPER)

    # De tre målmapparna (med mapptungor, som i master-ikonen)
    for x, col in zip((20, 98, 176), ICON_TARGETS):
        r(x + 4, 172, x + 34, 188, 6, col)   # mapptunga
        r(x, 182, x + 60, 236, 14, col)
    return img


def _icon_simple(S: int = 64):
    """Förenklad version för små storlekar.

    Att krympa den detaljerade ikonen till 16 punkter ger gröt: strecken
    blir tunnare än en bildpunkt och textraderna smetar ihop. Under 32
    punkter ritas därför ett grövre motiv med färre element - samma
    silhuett, men bara det som faktiskt syns.
    """
    from PIL import ImageDraw
    img = _icon_plate(S)
    d = ImageDraw.Draw(img)
    k = S / 256.0

    def r(x0, y0, x1, y1, radius, fill):
        d.rounded_rectangle([x0 * k, y0 * k, x1 * k, y1 * k],
                            radius=max(1, int(radius * k)), fill=fill)

    # Bladet: bredare, utan textrader
    r(88, 20, 168, 104, 14, ICON_PAPER)
    r(104, 40, 152, 66, 8, ICON_ACCENT)
    # Kraftig nedåtpil + balk, ingen stam (den försvinner ändå)
    d.polygon([(116, 104), (140, 104), (140, 118), (150, 118),
               (128, 140), (106, 118), (116, 118)], fill=ICON_PAPER)
    r(32, 134, 224, 158, 13, ICON_PAPER)
    for x in (32, 114, 196):
        r(x, 152, x + 28, 180, 11, ICON_PAPER)
    # Tre feta mål
    for x, col in zip((14, 96, 178), ICON_TARGETS):
        r(x, 178, x + 64, 238, 15, col)
    return img


#: Master-ikonen som levereras bredvid programfilerna. EN ikon överallt
#: (2026-10-16): samma ArkivPiloten.png används i fönster, systemfält,
#: genvägar, autostart, Utforskaren (via ArkivPiloten.ico), README och
#: donationssidan. Cachen håller den inladdade 512px-bilden per körning.
_MASTER_ICON: Any = None
_MASTER_ICON_TRIED = False


def _master_icon():
    """Ladda master-ikonen ArkivPiloten.png bredvid den här filen.

    Returnerar en PIL-bild eller None - saknas filen (t.ex. om bara
    .py-filerna kopierats) ritas ikonen i kod i stället, med samma motiv.
    """
    global _MASTER_ICON, _MASTER_ICON_TRIED
    if _MASTER_ICON_TRIED:
        return _MASTER_ICON
    _MASTER_ICON_TRIED = True
    try:
        from PIL import Image
        path = Path(__file__).resolve().parent / "ArkivPiloten.png"
        with Image.open(path) as im:
            im.load()
            _MASTER_ICON = im.convert("RGBA")
    except Exception:
        _MASTER_ICON = None
    return _MASTER_ICON


def make_icon_image(size: int = 256, active: bool = False,
                    badge: int = 0) -> Any:
    """Appikonen i valfri storlek.

    Master-ikonen (ArkivPiloten.png) är primär så att exakt samma ikon
    syns överallt; den kodritade ikonen är reserv med samma motiv.
    Under 32 punkter används ett förenklat motiv - se `_icon_simple()`.
    `active=True` lägger till en grön prick (bevakning på); `badge>0`
    ritar köantalet som en liten bricka (design: synlig kö utan att öppna).
    """
    try:
        from PIL import Image, ImageDraw, ImageEnhance
    except Exception:
        return None

    key = (int(size), bool(active), int(min(badge, 99)))
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached.copy()

    master = _master_icon()
    if master is not None:
        img = master.resize((size, size), Image.LANCZOS)
        if size <= 32:
            # Små storlekar: lite extra skärpa så att PDF-bandet och
            # mapparna fortfarande går att urskilja i systemfältet.
            img = ImageEnhance.Sharpness(img).enhance(1.6)
            img = ImageEnhance.Contrast(img).enhance(1.05)
    else:
        # 32 punkter och under: den detaljerade stammen blir tunnare än
        # en bildpunkt och textraden smetar ihop med PDF-fliken.
        liten = size <= 32
        # Rita alltid stort och skala ned: kantutjämningen blir mycket
        # bättre än att rita direkt i målstorleken.
        bas = 128 if liten else 256
        img = _icon_simple(bas) if liten else _icon_detailed(bas)
        if size != bas:
            img = img.resize((size, size), Image.LANCZOS)

    # Tunn ljus kant så att ikonen inte försvinner mot mörka aktivitetsfält
    # och titelrader (design: synlig i både ljust och mörkt läge).
    if size >= 20:
        d2 = ImageDraw.Draw(img)
        d2.rounded_rectangle([0.5, 0.5, size - 1.5, size - 1.5],
                             radius=max(1, int(size * 0.225)),
                             outline=(240, 244, 255, 110),
                             width=max(1, size // 64))

    # Pricken ritas EFTER nedskalningen, i målstorleken. Ritas den före
    # krymper den med resten och blir en grumlig fläck; ritas den efter
    # behåller den skarp kant och rimlig andel av ytan vid alla storlekar.
    if active:
        d = ImageDraw.Draw(img)
        r_ = max(2.0, size * 0.17)
        pad = max(1.0, size * 0.06)
        cx = cy = size - pad - r_
        kant = max(1, int(size * 0.035))
        d.ellipse([cx - r_, cy - r_, cx + r_, cy + r_],
                  fill=ICON_ACTIVE,
                  outline=ICON_PAPER if size >= 20 else None,
                  width=kant)
    # Köbricka: liten varningsfärgad cirkel med siffran, nere till vänster.
    if badge > 0 and size >= 32:
        d3 = ImageDraw.Draw(img)
        r_ = max(6.0, size * 0.16)
        pad_b = max(1.0, size * 0.05)
        cx, cy = pad_b + r_, size - pad_b - r_
        d3.ellipse([cx - r_, cy - r_, cx + r_, cy + r_],
                   fill=(224, 166, 63, 255), outline=(255, 255, 255, 255),
                   width=max(1, size // 48))
        d3.text((cx - r_ * 0.5, cy - r_ * 0.6), str(min(badge, 99)),
                fill=(255, 255, 255, 255))
    _ICON_CACHE[key] = img
    if len(_ICON_CACHE) > _ICON_CACHE_MAX:
        _ICON_CACHE.pop(next(iter(_ICON_CACHE)))
    return img.copy()


def icon_photoimage(size: int = 64, active: bool = False):
    """Ikonen som Tkinter-PhotoImage (för fönstrets titelrad)."""
    img = make_icon_image(size, active)
    if img is None:
        return None
    try:
        from PIL import ImageTk
        return ImageTk.PhotoImage(img)
    except Exception:
        pass
    # Fallback utan ImageTk: skicka PNG-data via base64
    try:
        import base64
        import tkinter as tk
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode("ascii"))
    except Exception:
        return None


def write_icon_file(path: Path, size: int = 256,
                    sizes: Tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)
                    ) -> Optional[Path]:
    """Spara ikonen som .ico (Windows) eller .png. Returnerar sökvägen.

    `size` styr PNG-storleken. En .ico får alla storlekar i `sizes` som
    separata lager, så att Utforskaren kan välja rätt - och varje lager
    ritas i sin egen storlek, vilket gör att de små får det förenklade
    motivet i stället för en nedskalad grötig variant.
    """
    if make_icon_image(16) is None:
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".ico":
            # Rita varje lager för sig: append_images låter Pillow lagra
            # våra egna bilder i stället för att skala ned den största.
            lager = [make_icon_image(s) for s in sorted(sizes, reverse=True)]
            lager = [b for b in lager if b is not None]
            if not lager:
                return None
            lager[0].save(path, format="ICO",
                          sizes=[(b.width, b.height) for b in lager],
                          append_images=lager[1:])
        else:
            img = make_icon_image(size)
            if img is None:
                return None
            img.save(path, format="PNG")
        return path
    except Exception:
        return None


_ICON_FILE_OK: Optional[Path] = None


def ensure_icon_file() -> Optional[Path]:
    """Se till att en ikonfil finns i konfigurationsmappen och returnera den.

    Validerar att filen verkligen går att läsa som bild - en trasig eller
    avkapad fil ritas om i stället för att ge en svart/rutig ikon i
    aktivitetsfältet. Resultatet memoiseras per körning (snabbhet).
    """
    global _ICON_FILE_OK
    if _ICON_FILE_OK is not None:
        return _ICON_FILE_OK
    path = icon_file_path()
    ok = path.exists() and path.stat().st_size > 0
    if ok:
        # Lätt validering: kan Pillow öppna filen? Nej = rita om.
        try:
            from PIL import Image
            with Image.open(path) as img:
                img.verify()
        except Exception:
            ok = False
    if not ok:
        path = write_icon_file(path) or path
    _ICON_FILE_OK = path if path.exists() else None
    return _ICON_FILE_OK


def icon_file_path() -> Path:
    """Genererad ikonfil bor i appmappens icons/-undermapp
    (2026-10-16: allt som skapas hamnar i undermappar)."""
    name = "arkivpiloten.ico" if sys.platform.startswith("win") else "arkivpiloten.png"
    return config_dir() / "icons" / name


#: Eget program-ID för Windows. Sätts före första fönstret så att
#: aktivitetsfältet visar vår ikon i stället för Pythons fjäder.
APP_USER_MODEL_ID = "ArkivPiloten.App.1"


# --------------------------------------------------------------------------
# AUTOINSTALLATION AV TESSERACT (ANVÄNDARORDER 2026-09-28: "funkar det att
# installera som tillägg?" - JA, på Windows i ett klick.)
# --------------------------------------------------------------------------
TESSERACT_WINGET_ID = "UB-Mannheim.TesseractOCR"
#: Känd stabil release (NSIS, tyst /S). Används bara om winget saknas.
TESSERACT_SETUP_URL = ("https://github.com/UB-Mannheim/tesseract/releases/"
                       "download/v5.4.0.20240606/"
                       "tesseract-ocr-w64-setup-5.4.0.20240606.exe")
#: Svenskt språkdata från officiella tessdata-katalogen.
TESSDATA_SWE_URL = ("https://github.com/tesseract-ocr/tessdata/raw/main/"
                    "swe.traineddata")


def _tesseract_kandidatmappar() -> List[Path]:
    ut = [Path("C:/Program Files/Tesseract-OCR"),
          Path("C:/Program Files (x86)/Tesseract-OCR")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        ut.append(Path(local) / "Programs" / "Tesseract-OCR")
    return ut


def _hitta_tesseract_mapp() -> Optional[Path]:
    for m in _tesseract_kandidatmappar():
        if (m / "tesseract.exe").exists():
            return m
    return None


def _ladda_ner(url: str, dest: Path, timeout: int = 900) -> None:
    """Strömmande nedladdning till temp + atomisk ersättning."""
    import urllib.request
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    req = urllib.request.Request(url, headers={"User-Agent": APP_NAME})
    with urllib.request.urlopen(req, timeout=timeout) as svar, \
            open(tmp, "wb") as ut:
        while True:
            bit = svar.read(1 << 20)
            if not bit:
                break
            ut.write(bit)
    os.replace(tmp, dest)


def search_tesseract() -> Optional[str]:
    """Genomsök sannolika installationsställen efter tesseract.exe.

    Begränsat djup (rot -> Program* -> undermapp -> undermapp), aldrig
    hela disken - tar normalt under sekunder. Returnerar första träffen
    eller None. Bara Windows; andra plattformar har pakethanterare.
    """
    if not sys.platform.startswith("win"):
        return None
    import string
    rotter = [Path(f"{b}:/") for b in string.ascii_uppercase
              if Path(f"{b}:/").exists()]
    baser: List[Path] = []
    for rot in rotter:
        baser += [rot, rot / "Program Files", rot / "Program Files (x86)",
                  rot / "Program", rot / "Programs", rot / "tools",
                  rot / "app", rot / "opt"]
    for var in ("LOCALAPPDATA", "APPDATA", "USERPROFILE"):
        v = os.environ.get(var)
        if v:
            hem = Path(v)
            baser += [hem / "Programs", hem / "Program Files", hem / "App"]
    for bas in baser:
        if (bas / "tesseract.exe").is_file():
            return str(bas / "tesseract.exe")
        try:
            niv1 = [d for d in bas.iterdir() if d.is_dir()]
        except OSError:
            continue
        for d1 in niv1:
            if (d1 / "tesseract.exe").is_file():
                return str(d1 / "tesseract.exe")
            if "tesseract" not in d1.name.lower():
                continue          # hoppa över orelaterade mappar (snabbt)
            try:
                for d2 in d1.iterdir():
                    if d2.is_dir() and (d2 / "tesseract.exe").is_file():
                        return str(d2 / "tesseract.exe")
            except OSError:
                continue
    return None


def auto_install_tesseract() -> Tuple[bool, str]:
    """Installera Tesseract OCR + svenska, i ett anrop (Windows).

    Ordning: 1) winget (renast), 2) ladda ner UB Mannheims installer och
    kör tyst (/S). Därefter läggs swe.traineddata i tessdata-katalogen om
    den saknas. Loggar varje steg till sessionsloggen. Returnerar
    (lyckades, meddelande). Aldrig kastande - nätverksfel blir meddelanden.
    """
    if not sys.platform.startswith("win"):
        return False, ("Automatisk installation stöds bara på Windows. "
                       "Linux: sudo apt install tesseract-ocr tesseract-ocr-swe | "
                       "macOS: brew install tesseract tesseract-lang")
    session_log("tillägg", "Autoinstallation av Tesseract startad")

    # 1) winget
    if shutil.which("winget"):
        try:
            session_log("tillägg", "Försöker winget install "
                        f"{TESSERACT_WINGET_ID}")
            r = subprocess.run(
                ["winget", "install", "--id", TESSERACT_WINGET_ID, "-e",
                 "--silent", "--accept-package-agreements",
                 "--accept-source-agreements"],
                capture_output=True, text=True, timeout=900, **_win_dold())
            session_log("tillägg", f"winget slutkod {r.returncode}: "
                        f"{(r.stdout or r.stderr or '').strip().splitlines()[-1:]}",
                        "ok" if r.returncode == 0 else "warn")
            if r.returncode == 0 and _hitta_tesseract_mapp():
                _se_till_svenska()
                return True, "Tesseract installerad via winget (+ svenska)"
        except Exception as exc:
            session_log("tillägg", f"winget misslyckades: {exc}", "warn")

    # 2) tyst installer som fallback
    if not _hitta_tesseract_mapp():
        try:
            session_log("tillägg", f"Laddar ner {TESSERACT_SETUP_URL}")
            # Nedladdning till appmappens temp/ (2026-10-16: inget
            # utanför appmappen) i stället för systemets temp-mapp.
            tmpdir = config_dir() / "temp"
            tmpdir.mkdir(parents=True, exist_ok=True)
            setup = tmpdir / "tesseract-setup.exe"
            _ladda_ner(TESSERACT_SETUP_URL, setup)
            session_log("tillägg", "Kör tyst installation (/S) - eventuellt "
                        "UAC-fönster dyker upp")
            r = subprocess.run([str(setup), "/S"], capture_output=True,
                               timeout=900, **_win_dold())
            session_log("tillägg", f"installer slutkod {r.returncode}",
                        "ok" if r.returncode == 0 else "warn")
            try:
                setup.unlink(missing_ok=True)
            except OSError:
                pass
        except Exception as exc:
            session_error("tillägg", exc)
            return False, f"Nedladdning/installation misslyckades: {exc}"

    if not _hitta_tesseract_mapp():
        return False, ("Installationen hittades inte i standardsökvägarna. "
                       "Installera manuellt via 'Hämta Tesseract…'.")
    _se_till_svenska()
    return True, "Tesseract installerad (+ svenska)"


def svenska_saknas() -> bool:
    """Finns Tesseract men utan swe.traineddata? (Manuella installer
    bockar ofta bara i engelska - svenska skanningar läses märkbart
    sämre utan språkpaketet.)"""
    m = _hitta_tesseract_mapp()
    if not m:
        return False
    swe = m / "tessdata" / "swe.traineddata"
    return not (swe.exists() and swe.stat().st_size > 1000)


def _se_till_svenska() -> None:
    """Lägg in swe.traineddata om den saknas (liten, officiell källa)."""
    mapp = _hitta_tesseract_mapp()
    if not mapp:
        return
    swe = mapp / "tessdata" / "swe.traineddata"
    if swe.exists() and swe.stat().st_size > 1000:
        return
    try:
        session_log("tillägg", f"Hämtar svenskt språkdata till {swe}")
        _ladda_ner(TESSDATA_SWE_URL, swe)
        session_log("tillägg", "Svenska installerad", "ok")
    except Exception as exc:
        session_log("tillägg", f"Kunde inte hämta svenska: {exc}", "warn")


def set_process_dpi_aware() -> None:
    """Windows: deklarera processen som DPI-medveten FÖRE första fönstret.

    Utan detta skalar Windows själv fönstret på HiDPI-skärmar - typsnitt
    och färger blir grötiga och temamodulens ui_scale ser fel pixeltäthet.
    Med anropet får Tkinter den riktiga tätheten och allt ritas skarpt.
    Kedjan prövar modernast först och ger sig aldrig - andra plattformar
    är no-op.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        try:                              # Per-monitor (Win 8.1+)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass
        try:                              # systemnivå
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            return
        except Exception:
            pass
        ctypes.windll.user32.SetProcessDPIAware()   # klassisk fallback
    except Exception:
        pass


def set_app_user_model_id(app_id: str = APP_USER_MODEL_ID) -> None:
    """Ge processen ett eget program-ID på Windows (aktivitetsfältets ikon).

    Utan detta grupperas fönstret under python(w).exe och visar Pythons
    generiska ikon, oavsett vad fönstret självt sätter. Ofarligt på andra
    plattformar och kan aldrig kasta.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def brand_window(root: Any, size: int = 64) -> Any:
    """Sätt appikonen på ett Tk-fönster - och på ALLA framtida fönster.

    `iconphoto(True, ...)` gäller som standard för varje nytt toplevel
    (dialoger, felrutor m.m.), och på Windows sätts dessutom iconbitmap
    med `default=`, vilket är det aktivitetsfältet/titelraden faktiskt
    ritar. Returnerar PhotoImage så att anroparen kan hålla kvar
    referensen (annars skräpsamlas ikonen och titelraden blir tom).
    """
    photo = None
    try:
        photo = icon_photoimage(size)
        if photo is not None:
            root.iconphoto(True, photo)
    except Exception:
        photo = None
    if sys.platform.startswith("win"):
        try:
            ico = ensure_icon_file()
            if ico:
                root.iconbitmap(default=str(ico))
        except Exception:
            pass
    return photo


# --------------------------------------------------------------------------
# Autostart med operativsystemet
# --------------------------------------------------------------------------
#: Klassificeringar av OS-posten (autostart v3.0, multi-OS):
#:   missing        -> posten finns inte alls
#:   correct        -> rätt kommando, rätt argument
#:   startup_folder -> Windows: posten finns bara som genväg i Startup-mappen
#:                     (registret nekade). Räknas som fungerande.
#:   duplicate      -> Windows: både registervärde och Startup-genväg finns.
#:                     Två kopior startar vid inloggning - synken städar.
#:   stale_console  -> Windows: pekar på python.exe (KONSOL-BLINK vid
#:                     inloggning) i stället för pythonw.exe
#:   stale_path     -> pekar på en gammal sökväg (flyttad mapp/ny python)
#:   stale_args     -> rätt program men gamla argument (t.ex. --tray saknas)
#:   different      -> något annat skiljer (okänt ursprung)
AUTOSTART_OK = frozenset({"correct", "startup_folder"})
AUTOSTART_LABEL = "com.arkivpiloten.autostart"
_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def _launch_argv() -> Tuple[List[str], str]:
    """Returnerar (argv, arbetskatalog) som startar appen minimerad.

    En lista i stället för en färdig kommandosträng: Windows, macOS och
    Linux citerar argument olika, och .desktop/plist ska få argumenten
    var för sig. Då slipper vi escape-fel i sökvägar med mellanslag,
    citattecken eller procenttecken.
    """
    if _frozen_app():                       # paketerad med PyInstaller
        exe = str(Path(sys.executable).resolve())
        return [exe, "--tray"], str(Path(exe).parent)
    script = Path(_main_script).resolve()
    workdir = str(script.parent)
    exe = sys.executable or ("python.exe" if sys.platform.startswith("win")
                             else "python3")
    if sys.platform.startswith("win"):
        # pythonw.exe kör helt utan konsolfönster
        exe_w = Path(exe).with_name("pythonw.exe")
        if exe_w.exists():
            exe = str(exe_w)
    return [str(exe), str(script), "--tray"], workdir


def _launch_target() -> Tuple[str, str]:
    """Kommandosträng + arbetskatalog (Windows-registret/status)."""
    argv, workdir = _launch_argv()
    if sys.platform.startswith("win"):
        cmd = subprocess.list2cmdline(argv)
    else:
        import shlex
        cmd = shlex.join(argv)
    return cmd, workdir


def autostart_supported() -> bool:
    return (sys.platform.startswith("win") or sys.platform == "darwin"
            or sys.platform.startswith("linux"))


def autostart_session_available() -> bool:
    """Finns en grafisk inloggningssession just nu?

    På Linux kan autostarten skrivas även från SSH (den aktiveras vid
    nästa inloggning), men statusraden ska inte påstå att den är igång
    i en session som saknar skrivbord.
    """
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY")
                    or os.environ.get("WAYLAND_DISPLAY"))
    return True


def _win_run_key(access: Optional[int] = None):
    """Öppna HKCU\\...\\Run med minsta möjliga rättighet.

    Tidigare användes KEY_ALL_ACCESS även för läsning. Grupprinciper och
    antivirus nekar ofta den bredare rättigheten, vilket fick appen att
    tro att autostarten saknades trots att den fanns.
    """
    import winreg
    if access is None:
        access = getattr(winreg, "KEY_ALL_ACCESS", 0x20019)
    try:
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0, access)
    except FileNotFoundError:
        if access & getattr(winreg, "KEY_SET_VALUE", 0x0002):
            return winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY,
                                      0, access)
        raise


def _win_registry_read() -> Tuple[Optional[str], bool]:
    """(värde, kunde_läsas). Skiljer "finns inte" från "nekad åtkomst"."""
    try:
        import winreg
        with _win_run_key(getattr(winreg, "KEY_READ", 0x20019)) as key:
            try:
                return str(winreg.QueryValueEx(key, APP_NAME)[0]), True
            except FileNotFoundError:
                return None, True
    except FileNotFoundError:
        return None, True
    except Exception:
        return None, False


def _win_registry_write(value: Optional[str]) -> Tuple[bool, str]:
    """Sätt/ta bort Run-värdet. value=None betyder ta bort."""
    try:
        import winreg
        with _win_run_key(getattr(winreg, "KEY_SET_VALUE", 0x0002)) as key:
            if value is None:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, value)
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _win_startup_lnk() -> Path:
    """Windows reservväg: genväg i Startup-mappen (om registret nekar)."""
    appdata = os.environ.get("APPDATA") or str(
        Path.home() / "AppData" / "Roaming")
    return (Path(appdata) / "Microsoft" / "Windows" / "Start Menu"
            / "Programs" / "Startup" / f"{APP_NAME}.lnk")


def _win_remove_startup_lnk() -> Tuple[bool, str]:
    lnk = _win_startup_lnk()
    if not lnk.exists():
        return True, ""
    try:
        lnk.unlink()
        return True, ""
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _mac_plist_file() -> Path:
    return (Path.home() / "Library" / "LaunchAgents"
            / f"{AUTOSTART_LABEL}.plist")


def _linux_autostart_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / "arkivpiloten.desktop"


def _linux_legacy_autostart_file() -> Path:
    """Gamla namnet från PDF Sorter-tiden - känns igen och städas bort
    så att inte två poster startar appen (2026-10-16)."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / "pdfsorter.desktop"


def _desktop_escape(value: str) -> str:
    """Escapa en sträng enligt Desktop Entry Specification (utan citattecken)."""
    text = str(value)
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("`", "\\`").replace("$", "\\$")
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return text


def _desktop_quote(value: str, field_codes: bool = False) -> str:
    """Citera ett värde. field_codes=True för Exec (där % är fältkod)."""
    text = _desktop_escape(value)
    if field_codes:
        # Procenttecknet är alltid en fältkod i Exec; literaltecknet
        # skrivs som %%. Utan detta blev en sökväg som /tmp/100% en
        # ogiltig post som GNOME/KDE vägrade starta (2026-10-20).
        text = text.replace("%", "%%")
    return f'"{text}"'


def _desktop_exec(argv: List[str]) -> str:
    return " ".join(_desktop_quote(a, field_codes=True) for a in argv)


def _desktop_env_line() -> str:
    """PDFSORTER_HOME måste följa med in i autostarten.

    Utan Environment= startar autostarten med appmappens data i stället
    för den valda datamappen - användaren får då två separata regler.
    """
    home = os.environ.get("PDFSORTER_HOME", "").strip()
    if not home:
        return ""
    verdi = str(Path(home).expanduser())
    return "Environment=PDFSORTER_HOME=" + _desktop_quote(verdi) + "\n"


def _desktop_path(value: str) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")


def _linux_desktop_entry(tray: bool = True, menu: bool = False) -> str:
    """Bygg en giltig .desktop-post för autostart eller appmeny."""
    argv, workdir = _launch_argv()
    if not tray:
        argv = [a for a in argv if a != "--tray"]
    icon = ensure_icon_file()
    rader = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        f"Name={APP_NAME}",
        "Comment=Sorterar PDF-filer till undermappar",
        f"Exec={_desktop_exec(argv)}",
        f"Path={_desktop_path(workdir)}",
        "Terminal=false",
        "StartupNotify=false",
    ]
    if icon:
        rader.append(f"Icon={icon}")
    if menu:
        rader += ["Categories=Office;Utility;", "Keywords=PDF;arkiv;sortering;"]
    rader.append(_desktop_env_line().rstrip("\n"))
    if tray:
        rader += ["X-GNOME-Autostart-enabled=true", "X-GNOME-Autostart-Delay=3"]
    return "\n".join(r for r in rader if r != "") + "\n"


def _desktop_value(text: str, key: str) -> Optional[str]:
    """Läs ett nyckel=värde ur en .desktop-fil (utan interpolation)."""
    for rad in text.splitlines():
        if rad.startswith(key + "="):
            return rad.split("=", 1)[1]
    return None


def _autostart_source() -> str:
    if sys.platform.startswith("win"):
        value, _ = _win_registry_read()
        if value is not None:
            return "registry"
        return "startup_folder" if _win_startup_lnk().exists() else ""
    if sys.platform == "darwin":
        return "launchagent"
    if sys.platform.startswith("linux"):
        if _linux_autostart_file().exists():
            return "xdg"
        if _linux_legacy_autostart_file().exists():
            return "xdg_legacy"
    return ""


def autostart_enabled() -> bool:
    """Är autostart påslagen just nu?"""
    try:
        if sys.platform.startswith("win"):
            value, _läsbar = _win_registry_read()
            if value is not None:
                return True
            # Reservvägen måste räknas även när registret är otillgängligt
            # (policy/antivirus) - annars visade GUI:t "av" trots att
            # genvägen i Startup-mappen startade appen varje inloggning.
            return _win_startup_lnk().exists()
        if sys.platform == "darwin":
            return _mac_plist_file().exists()
        return (_linux_autostart_file().exists()
                or _linux_legacy_autostart_file().exists())
    except Exception:
        return False


def _autostart_current() -> Optional[str]:
    """Råinnehållet i OS-posten (registervärde / .desktop / plist)."""
    try:
        if sys.platform.startswith("win"):
            value, _läsbar = _win_registry_read()
            if value is not None:
                return value
            lnk = _win_startup_lnk()
            return f"startup-folder: {lnk}" if lnk.exists() else None
        if sys.platform == "darwin":
            p = _mac_plist_file()
            return p.read_text(encoding="utf-8") if p.exists() else None
        p = _linux_autostart_file()
        if not p.exists():
            p = _linux_legacy_autostart_file()
        return p.read_text(encoding="utf-8") if p.exists() else None
    except Exception:
        return None


def autostart_up_to_date() -> bool:
    """Pekar OS-posten på *aktuella* programmet?

    Efter att mappen flyttats eller python bytt plats pekar gamla poster
    fel - autostarten "fungerar" men startar ingenting. Det är den tysta
    varianten av trasig autostart som synken ska laga.
    """
    return classify_autostart() in AUTOSTART_OK


def classify_autostart() -> str:
    """Klassificera OS-posten exakt - så att synken kan laga RÄTT sak."""
    try:
        if sys.platform.startswith("win"):
            value, _läsbar = _win_registry_read()
            lnk_exists = _win_startup_lnk().exists()
            if value is None and not lnk_exists:
                return "missing"
            if value is None:
                return "startup_folder"
            if lnk_exists:
                return "duplicate"
            cmd, _workdir = _launch_target()
            n_cur, n_cmd = value.casefold().replace("\\", "/"), \
                cmd.casefold().replace("\\", "/")
            if n_cmd in n_cur:
                return "correct"
            mål = (str(sys.executable) if _frozen_app()
                   else str(_main_script)).casefold().replace("\\", "/")
            if mål not in n_cur:
                return "stale_path"
            if "pythonw.exe" not in n_cur and "python.exe" in n_cur:
                return "stale_console"
            if "--tray" in n_cmd and "--tray" not in n_cur:
                return "stale_args"
            return "different"

        if sys.platform == "darwin":
            p = _mac_plist_file()
            if not p.exists():
                return "missing"
            try:
                import plistlib
                data = plistlib.loads(p.read_bytes())
                args = data.get("ProgramArguments")
                if not isinstance(args, list):
                    return "different"
                args = [str(a) for a in args]
                expected, workdir = _launch_argv()
                if args == expected:
                    if str(data.get("WorkingDirectory", workdir)) != workdir:
                        return "different"
                    home = os.environ.get("PDFSORTER_HOME", "").strip()
                    if home:
                        env = data.get("EnvironmentVariables") or {}
                        if str(env.get("PDFSORTER_HOME", "")) != str(
                                Path(home).expanduser()):
                            return "different"
                    return "correct"
                if not any(str(_main_script) == a for a in args):
                    if not _frozen_app():
                        return "stale_path"
                if "--tray" not in args:
                    return "stale_args"
                return "different"
            except Exception:
                return "different"

        if not sys.platform.startswith("linux"):
            return "missing"
        desktop = _linux_autostart_file()
        legacy = _linux_legacy_autostart_file()
        if not desktop.exists():
            return "stale_path" if legacy.exists() else "missing"
        if legacy.exists():
            return "duplicate"
        try:
            text = desktop.read_text(encoding="utf-8")
        except OSError:
            return "different"
        argv, workdir = _launch_argv()
        exec_rad = _desktop_value(text, "Exec")
        if exec_rad is None:
            return "different"
        if exec_rad.strip() != _desktop_exec(argv):
            if "--tray" not in exec_rad:
                return "stale_args"
            if str(_main_script) not in exec_rad:
                return "stale_path"
            return "different"
        path_rad = _desktop_value(text, "Path")
        if path_rad is not None and path_rad.strip() != _desktop_path(workdir):
            return "stale_path"
        home = os.environ.get("PDFSORTER_HOME", "").strip()
        if home:
            env_rad = _desktop_value(text, "Environment") or ""
            if str(Path(home).expanduser()) not in env_rad:
                return "different"
        return "correct"
    except Exception:
        return "different"


def autostart_status() -> dict:
    """Samlad autostart-status för alla OS (statusrader/diagnostik)."""
    entry = ""
    try:
        if sys.platform.startswith("win"):
            entry = (r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
                     f"\\{APP_NAME} (reserv: {_win_startup_lnk()})")
        elif sys.platform == "darwin":
            entry = str(_mac_plist_file())
        else:
            entry = str(_linux_autostart_file())
    except Exception:
        pass
    return {"platform": sys.platform,
            "supported": autostart_supported(),
            "session": autostart_session_available(),
            "enabled": autostart_enabled(),
            "klass": classify_autostart(),
            "source": _autostart_source(),
            "entry": entry}


def effective_autostart(settings: dict) -> Tuple[bool, bool]:
    """Vill appen ha autostart - och ärvs posten i så fall från OS:et?

    Returnerar (vill, ärvd). Regeln: en fungerande OS-post får aldrig
    tas bort bara för att settings.json säger av. Det kan hända när
    autostarten slagits på av install.sh, av en annan användare eller
    när settings återställts - och då är det bättre att ÄRVA posten än
    att tyst radera användarens val. Borttagning ska alltid vara ett
    uttryckligt val (kryssrutan eller --remove-autostart).
    """
    vill = bool((settings or {}).get("autostart", False))
    if vill:
        return True, False
    try:
        if autostart_enabled():
            return True, True
    except Exception:
        pass
    return False, False


def get_autostart_conflicts() -> List[Tuple[str, str]]:
    """Andra autostartposter som nämner appen (bara Windows).

    Läs-only: andras poster rörs ALDRIG. Gamla dubletter från flyttade
    installationer syns här, så att användaren kan städa manuellt.
    """
    if not sys.platform.startswith("win"):
        return []
    try:
        import winreg
        ut: List[Tuple[str, str]] = []
        with _win_run_key(getattr(winreg, "KEY_READ", 0x20019)) as key:
            i = 0
            while True:
                try:
                    name, data, _typ = winreg.EnumValue(key, i)
                except OSError:
                    break
                i += 1
                if name == APP_NAME:
                    continue
                if "pdfsorter" in str(data).casefold() or "arkivpiloten" in str(
                        data).casefold():
                    ut.append((name, str(data)))
        return ut
    except Exception:
        return []


def _backup_autostart_entry() -> Optional[Path]:
    """Roterad backup av OS-posten före ändring/borttagning (max 10 st).

    Om något går snett vid en registry-skrivning finns det senaste
    värdet kvar som JSON - ingen autostart försvinner spårlöst.
    """
    cur = _autostart_current()
    if cur is None:
        return None
    try:
        mapp = config_dir() / "backups"
        mapp.mkdir(parents=True, exist_ok=True)
        # Mikrosekunder i namnet: två säkerhetskopior inom samma sekund
        # (t.ex. snabb på/av i testen) får aldrig skriva över varandra.
        stamp = _dt.now().strftime("%Y%m%d_%H%M%S_%f")
        fil = mapp / f"autostart_{stamp}.json"
        import json as _json
        data = _json.dumps({"time": now_iso(), "platform": sys.platform,
                            "entry": cur}, ensure_ascii=False, indent=1)
        # Atomiskt enligt låst regel: mkstemp -> fdopen -> fsync -> replace
        import tempfile
        fd, tmp = tempfile.mkstemp(dir=str(mapp), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, fil)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        # Rotation: behåll de 10 nyaste
        gamla = sorted(mapp.glob("autostart_*.json"))
        for g in gamla[:-10]:
            try:
                g.unlink()
            except OSError:
                pass
        return fil
    except Exception:
        return None


def _verify_autostart() -> bool:
    """Verify-after-write (L3): läs tillbaka posten och jämför normaliserat."""
    try:
        return classify_autostart() in AUTOSTART_OK
    except Exception:
        return False


def _atomic_text(path: Path, text: str) -> None:
    """Atomisk textskrivning enligt låst regel: mkstemp -> fdopen ->
    fsync -> os.replace. Används för autostartfiler (.plist/.desktop) -
    en krasch mitt i skrivningen får aldrig lämna en halv post."""
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent),
                               prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _ps_quote(s: str) -> str:
    """Sträng som är säker inuti PowerShell-citationstecken.

    En sökväg med apostrof (C:\\Users\\O'Brien\\...) sprängde tidigare
    hela genvägskommandot - nu fördubblas apostrofen, vilket är rätt
    escape i PowerShell-citerade strängar.
    """
    return str(s).replace("'", "''")


def _win_dold() -> Dict[str, Any]:
    """Windows: underprocesser utan konsolfönster (pythonw blinkar inte)."""
    if not sys.platform.startswith("win"):
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {"startupinfo": si, "creationflags": 0x08000000}


def _win_make_lnk(target: Path) -> Tuple[bool, str]:
    """Skapa en .lnk-genväg till appen (delas av skrivbord + Startup)."""
    try:
        icon = ensure_icon_file()
        argv, workdir = _launch_argv()
        exe = argv[0]
        args = subprocess.list2cmdline(argv[1:])
        target.parent.mkdir(parents=True, exist_ok=True)
        ps = (
            f"$s=(New-Object -COM WScript.Shell).CreateShortcut("
            f"'{_ps_quote(target)}');"
            f"$s.TargetPath='{_ps_quote(exe)}';"
            f"$s.Arguments='{_ps_quote(args)}';"
            f"$s.WorkingDirectory='{_ps_quote(workdir)}';"
            f"$s.Description='{_ps_quote(APP_NAME)}';"
            + (f"$s.IconLocation='{_ps_quote(icon)}';" if icon else "") +
            "$s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       check=True, capture_output=True, timeout=30,
                       **_win_dold())
        if not target.is_file():
            return False, f"PowerShell skapade ingen genväg: {target}"
        return True, str(target)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _retry_io(fn, tries: int = 2):
    """Transienta skrivfel (syncad disk, antivirus) prövas igen -
    autostart-skrivningar får varken krascha eller hänga."""
    for i in range(tries):
        try:
            return fn()
        except OSError:
            if i == tries - 1:
                raise
            time.sleep(0.1)


# -- macOS: launchctl ------------------------------------------------------
def _launchctl(*args: str, timeout: float = 10.0) -> Tuple[bool, str]:
    try:
        r = subprocess.run(["launchctl", *args], capture_output=True,
                           text=True, timeout=timeout)
    except FileNotFoundError:
        return False, "launchctl saknas"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if r.returncode == 0:
        return True, (r.stdout or "").strip()
    fel = (r.stderr or r.stdout or "").strip()
    return False, fel or f"slutkod {r.returncode}"


def _launchctl_domain() -> str:
    return f"gui/{getattr(os, 'getuid', lambda: 0)()}"


def _mac_job_loaded() -> bool:
    ok, _ = _launchctl("print", f"{_launchctl_domain()}/{AUTOSTART_LABEL}")
    return ok


def _mac_bootstrap(plist: Path) -> Tuple[bool, str]:
    """Ladda om LaunchAgenten nu, så att den inte väntar till nästa inloggning."""
    if _mac_job_loaded():
        _launchctl("bootout", f"{_launchctl_domain()}/{AUTOSTART_LABEL}")
    ok, msg = _launchctl("bootstrap", _launchctl_domain(), str(plist))
    if not ok:
        # macOS 10.9 och äldre saknar bootstrap/bootout.
        ok, msg = _launchctl("load", "-w", str(plist))
    if ok:
        ok2, msg2 = _launchctl("print",
                               f"{_launchctl_domain()}/{AUTOSTART_LABEL}")
        return (True, "") if ok2 else (False, msg2 or "okänd status")
    return False, msg


def _mac_bootout(plist: Path) -> Tuple[bool, str]:
    ok, msg = _launchctl("bootout",
                         f"{_launchctl_domain()}/{AUTOSTART_LABEL}")
    if not ok:
        ok, msg = _launchctl("unload", "-w", str(plist))
    return ok, msg


def _mac_plist_bytes() -> bytes:
    """Bygg plist med plistlib i stället för strängmall.

    XML måste escapas: en sökväg med & eller < gav tidigare en trasig
    plist som launchd vägrade läsa - men appen påstod "(verifierad)".
    """
    import plistlib
    argv, workdir = _launch_argv()
    data: Dict[str, Any] = {
        "Label": AUTOSTART_LABEL,
        "ProgramArguments": argv,
        "RunAtLoad": True,
        "WorkingDirectory": workdir,
        "StandardOutPath": str(config_dir() / "logs" / "autostart.log"),
        "StandardErrorPath": str(config_dir() / "logs" / "autostart.log"),
        "ProcessType": "Interactive",
        "LimitLoadToSessionType": "Aqua",
    }
    home = os.environ.get("PDFSORTER_HOME", "").strip()
    if home:
        data["EnvironmentVariables"] = {
            "PDFSORTER_HOME": str(Path(home).expanduser())}
    return plistlib.dumps(data)


def set_autostart(enabled: bool) -> Tuple[bool, str]:
    """Slå på eller av autostart. Returnerar (lyckades, meddelande).

    Skrivningen prövas två gånger (transienta I/O-fel), så att varken
    registret eller filsystemet kan få autostarten att krascha/hänga.
    """
    cmd, workdir = _launch_target()
    _backup_autostart_entry()      # säkerhetskopia före varje ändring

    def _do():
        if sys.platform.startswith("win"):
            if enabled:
                ok, err = _win_registry_write(cmd)
                if ok:
                    # Dubbelpost: registret räcker. Städa en gammal
                    # Startup-genväg från reservvägen, annars startar
                    # appen två gånger vid varje inloggning.
                    lnk_ok, lnk_err = _win_remove_startup_lnk()
                    if not lnk_ok:
                        return False, (f"Registret uppdaterat men kunde inte "
                                       f"ta bort Startup-genvägen: {lnk_err}")
                    return True, "Registret uppdaterat"
                ok, msg = _win_make_lnk(_win_startup_lnk())
                if ok:
                    return True, f"Startup-mappen (registerreserv): {msg}"
                return False, (f"Kunde inte slå på autostart "
                               f"(register: {err}; genväg: {msg})")
            ok_reg, err_reg = _win_registry_write(None)
            ok_lnk, err_lnk = _win_remove_startup_lnk()
            if autostart_enabled():
                detalj = "; ".join(x for x in (err_reg, err_lnk) if x)
                return False, ("Kunde inte stänga av autostart - posten "
                               f"finns kvar ({detalj or 'okänt fel'})")
            # Autostart är av - även om en läsning/skrivning nekades på
            # vägen. Det som räknas är att ingen post startar appen.
            return True, "Borttagen"

        if sys.platform == "darwin":
            plist = _mac_plist_file()
            if not enabled:
                _mac_bootout(plist)
                plist.unlink(missing_ok=True)
                return True, "Borttagen"
            plist.parent.mkdir(parents=True, exist_ok=True)
            try:
                (config_dir() / "logs").mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            _atomic_text(plist, _mac_plist_bytes().decode("utf-8"))
            laddad, lmsg = _mac_bootstrap(plist)
            if laddad:
                return True, f"{plist} (laddad och verifierad)"
            return True, (f"{plist} (installerad - aktiveras vid nästa "
                          f"inloggning: {lmsg})")

        # Linux: XDG autostart (fungerar i GNOME/KDE/Xfce m.fl.)
        desktop = _linux_autostart_file()
        legacy = _linux_legacy_autostart_file()
        if not enabled:
            desktop.unlink(missing_ok=True)
            legacy.unlink(missing_ok=True)
            return True, "Borttagen"
        _atomic_text(desktop, _linux_desktop_entry(tray=True))
        legacy.unlink(missing_ok=True)   # gamla namnet får inte dubbelstarta
        return True, str(desktop)

    try:
        ok, msg = _retry_io(_do)
        if ok and enabled:
            # Verify-after-write: bekräfta att skrivningen verkligen bet.
            if _verify_autostart():
                if "aktiveras" not in msg:
                    msg += " (posten verifierad)"
            else:
                # Säg aldrig "klart" när posten inte kan läsas tillbaka:
                # användaren ska få veta att autostarten inte är pålitlig.
                session_log("autostart",
                            f"Kunde inte verifiera autostarten: {msg}", "err")
                return False, f"{msg} (KUNDE INTE VERIFIERAS)"
        session_log("autostart",
                    f"{'Påslagen' if enabled else 'Avstängd'}: {msg}",
                    "ok" if ok else "err")
        return ok, msg
    except Exception as exc:
        session_error("autostart", exc)
        return False, f"{type(exc).__name__}: {exc}"


def sync_autostart(want: bool) -> Tuple[bool, str]:
    """Självläkande autostart (ANVÄNDARORDER 2026-08-26: bättre autostart).

    Settings säger på men OS-posten saknas -> skapa den; säger av men posten
    finns -> ta bort den; redan rätt -> gör inget. Autostarten ska inte
    tyst sluta fungera efter t.ex. en OS-uppdatering eller att programmet
    flyttats till ny mapp.
    """
    try:
        enabled = autostart_enabled()
        klass = classify_autostart()
    except Exception:
        return False, "kunde inte läsas"
    if want and klass not in AUTOSTART_OK:
        # Alla avvikelser lagas: saknas, fel sökväg, konsol-python
        # (stale_console), dubbelpost eller gamla argument.
        session_log("autostart", f"Synk lagar posten (klass: {klass})")
        ok, msg = set_autostart(True)
        return ok, f"{klass} -> {msg}"
    if not want and enabled:
        return set_autostart(False)
    return True, "synk"


def tray_backend_name() -> str:
    """Namnet på den pystray-backend som valdes (t.ex. pystray._xorg)."""
    try:
        import pystray
        return str(getattr(pystray.Icon, "__module__", "") or "")
    except Exception:
        return ""


def tray_hidden_start_safe() -> Tuple[bool, str]:
    """Kan appen starta dold i systemfältet och ändå gå att nå?

    På Linux är pystrays X11-backend osynlig i GNOME utan
    AppIndicator-tillägget. Att då starta med --tray gav en app som
    varken hade fönster eller ikon - särskilt illa vid autostart.
    """
    if not tray_available():
        return False, "pystray/Pillow saknas"
    if sys.platform.startswith("linux"):
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return False, "ingen grafisk session (DISPLAY/WAYLAND_DISPLAY saknas)"
        backend = tray_backend_name()
        if "appindicator" not in backend:
            desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
            if "gnome" in desktop:
                return False, ("GNOME visar inte X11-systemfält "
                               f"(backend: {backend or 'okänd'}) - "
                               "installera AppIndicator-tillägget")
    return True, ""


def create_desktop_shortcut() -> Tuple[bool, str]:
    """Lägg en genväg på skrivbordet - Windows, macOS och Linux.

    Windows: .lnk via PowerShell. Linux: .desktop i appmenyn
    (~/.local/share/applications) och, när en skrivbordsmapp finns, även
    på skrivbordet - med trust-flaggan satt så att GNOME/Nautilus inte
    kallar den "otrovärdig". macOS: ett .command-skal (dubbelklick); en
    riktig .app med Dock-ikon skapas av install.sh.
    """
    desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        desktop = Path.home() / "Skrivbord"
    try:
        if sys.platform.startswith("win"):
            if not desktop.is_dir():
                return False, "Hittade ingen skrivbordsmapp"
            return _win_make_lnk(desktop / f"{APP_NAME}.lnk")

        if sys.platform.startswith("linux"):
            skrivna = []
            # Appmenyn först: den fungerar även på GNOME/Ubuntu där
            # skrivbordsikoner inte visas alls.
            data_home = os.environ.get("XDG_DATA_HOME") or str(
                Path.home() / ".local" / "share")
            menu = Path(data_home) / "applications" / "arkivpiloten.desktop"
            try:
                _atomic_text(menu, _linux_desktop_entry(tray=False, menu=True))
                menu.chmod(0o644)
                skrivna.append(str(menu))
            except OSError as exc:
                skrivna.append(f"(appmenyn kunde inte skrivas: {exc})")
            if desktop.is_dir():
                target = desktop / "arkivpiloten.desktop"
                _atomic_text(target, _linux_desktop_entry(tray=False, menu=True))
                target.chmod(0o755)
                skrivna.append(str(target))
                # GNOME/Nautilus kräver trust-flaggan för att starta en
                # .desktop-fil från skrivbordet med dubbelklick.
                if shutil.which("gio"):
                    try:
                        subprocess.run(["gio", "set", str(target),
                                        "metadata::trusted", "true"],
                                       capture_output=True, timeout=5)
                    except Exception:
                        pass
            if not any(str(x).startswith("/") for x in skrivna):
                return False, "\n".join(skrivna) or "Kunde inte skriva genvägen"
            return True, "\n".join(skrivna)

        if sys.platform == "darwin":
            if not desktop.is_dir():
                return False, "Hittade ingen skrivbordsmapp"
            import shlex
            argv, workdir = _launch_argv()
            argv = [a for a in argv if a != "--tray"]
            target = desktop / "Starta ArkivPiloten.command"
            text = ("#!/bin/sh\n"
                    f"cd {shlex.quote(workdir)}\n"
                    "exec " + " ".join(shlex.quote(a) for a in argv)
                    + ' "$@"\n')
            _atomic_text(target, text)
            target.chmod(0o755)
            return True, (f"{target}\n\nDubbelklick öppnar Terminal och "
                          "startar appen. Kör install.sh för en riktig "
                          "ArkivPiloten.app med Dock-ikon.")

        return False, "Stöds inte på den här plattformen"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------
# Systemfältsikon
# --------------------------------------------------------------------------
def tray_available() -> bool:
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except Exception:
        return False


class TrayIcon:
    """Ikon i systemfältet med snabbmeny.

    Windows/Linux: pystray-loop i en egen tråd. macOS: pystray kräver att
    NSApplication-loopens ägare är huvudtråden, så där används
    run_detached() och Tk:s mainloop får driva händelserna. All
    gränssnittsinteraktion skickas tillbaka till Tk-tråden via App._post,
    eftersom Tk inte är trådsäkert.
    """

    def __init__(self, app: Any):
        # `app` är App-instansen från pdfsorter.py. Modulen använder bara
        # dess publika delar (queue, watcher och _post), så någon import
        # tillbaka till huvudfilen behövs inte.
        self.app = app
        self.icon = None
        self._thread: Optional[threading.Thread] = None
        self._detached = False

    # -- meny -------------------------------------------------------------
    def _build_menu(self):
        import pystray
        Item, Menu = pystray.MenuItem, pystray.Menu

        def watching(_=None) -> bool:
            return bool(self.app.watcher and self.app.watcher.running)

        return Menu(
            Item("Visa fönster", lambda: self.app._post(self.app.show_window),
                 default=True),
            Menu.SEPARATOR,
            Item("Sortera nu", lambda: self.app._post(self.app._sort_now)),
            Item("Bevakning", lambda: self.app._post(self.app._toggle_watch),
                 checked=watching),
            Item(self._queue_label, lambda: self.app._post(self.app.show_review)),
            Menu.SEPARATOR,
            Item("Öppna utmappen", lambda: self.app._post(self.app.open_output)),
            Item("Avsluta", lambda: self.app._post(self.app.quit_app)),
        )

    def _queue_label(self, _=None) -> str:
        n = len(self.app.queue)
        return f"Granska ({n})" if n else "Granska"

    # -- livscykel --------------------------------------------------------
    def start(self) -> bool:
        if not tray_available() or self.icon is not None:
            return False
        try:
            import pystray
            image = make_icon_image(64)
            if image is None:
                return False
            self.icon = pystray.Icon("pdfsorter", image, APP_NAME, self._build_menu())
            if sys.platform == "darwin":
                # pystray/_base.py: "run() must be called from the main
                # thread". Att starta NSApplication i en bakgrundstråd
                # gjorde att menykonen aldrig dök upp, medan appen trodde
                # att den fanns och gömde fönstret (osynlig app vid
                # autostart). run_detached() låter Tk äga huvudloopen.
                self.icon.run_detached()
                self._detached = True
                return True
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="pdfsorter-tray")
            self._thread.start()
            return True
        except Exception:
            self.icon = None
            return False

    def _run(self) -> None:
        try:
            self.icon.run()
        except Exception as exc:
            # Tidigare svaldes felet tyst - användaren såg bara att
            # ikonen försvann utan förklaring. Nu syns det i loggen.
            session_error("systemfält", exc)

    def refresh(self) -> None:
        """Uppdatera ikonens utseende och meny."""
        if not self.icon:
            return
        try:
            running = bool(self.app.watcher and self.app.watcher.running)
            n = len(self.app.queue)
            img = make_icon_image(64, active=running, badge=n)
            if img is not None:
                self.icon.icon = img
            self.icon.title = (f"{APP_NAME} - {n} väntar på granskning" if n
                               else f"{APP_NAME}" + (" - bevakar" if running else ""))
            self.icon.update_menu()
        except Exception:
            pass

    def notify(self, message: str, title: str = APP_NAME) -> None:
        if not self.icon:
            return
        try:
            self.icon.notify(message[:200], title)
        except Exception:
            pass

    def stop(self) -> None:
        """Stoppa tray-ikonen med 2 s vakthund: en hängande tray-backend
        (t.ex. saknad tray-daemon på Linux) får aldrig blockera avslut."""
        if not self.icon:
            return
        icon, self.icon = self.icon, None
        if sys.platform == "darwin" and self._detached:
            # icon.stop() stoppar NSApplication - dvs även Tk:s mainloop.
            # Dölj bara statusobjektet; appen avslutas ändå via quit_app.
            self._detached = False
            try:
                icon.visible = False
            except Exception:
                pass
            return

        def _stoppa():
            try:
                icon.stop()
            except Exception:
                pass

        t = threading.Thread(target=_stoppa, daemon=True,
                             name="pdfsorter-tray-stop")
        t.start()
        t.join(2.0)



_HELP_TEXT_CACHE: Optional[str] = None

#: Hjälpen som (formatering, text). Visas i fliken Hjälp och kan sparas
#: som textfil. Ligger i koden så att appen förblir en enda fil.
HELP_CONTENT: List[Tuple[str, str]] = [
    ("h1", "ArkivPiloten — så funkar den"),
    ("body", "Appen läser PDF-filerna i dina inmappar, listar ut vad de "
             "handlar om och flyttar dem till rätt undermapp i utmappen. "
             "Allt som rör Pilkington hamnar i Utmapp/Pilkington, och så "
             "vidare. Undermapparna skapas automatiskt."),

    ("h2", "Kom igång på fem minuter"),
    ("bullet", "1.  Fliken Sortera → Lägg till… och peka ut mappen där "
               "PDF-filerna landar. Du kan lägga till flera."),
    ("bullet", "2.  Välj Utmapp — där skapas undermapparna."),
    ("bullet", "3.  Kryssa i Testkörning. Då flyttas ingenting, du ser "
               "bara vad som skulle hänt."),
    ("bullet", "4.  Klicka Sortera nu och läs loggen."),
    ("bullet", "5.  Kryssa ur Testkörning och kör igen på riktigt."),
    ("bullet", "6.  Klicka Starta bevakning så håller appen koll själv."),
    ("bullet", "7.  Undermappar läses automatiskt (kan stängas av i "
               "Inställningar). Saknar du filer i undermappar, kolla "
               "kryssrutan 'Läs även undermappar'."),
    ("note", "Första gången kan appen ingenting — den frågar om varje fil. "
             "Efter tio, femton svar känner den igen dina vanligaste "
             "leverantörer och sköter resten på egen hand."),

    ("h2", "När appen frågar"),
    ("body", "Är appen osäker hamnar filen i granskningskön och du får upp "
             "en ruta med tio förslag på stödord hämtade ur just den filen. "
             "Bocka i de ord som hör ihop med rätt leverantör och välj mapp. "
             "Nästa gång ett av orden dyker upp går filen automatiskt."),
    ("body", "Välj hellre ord som är unika för företaget:"),
    ("bullet", "Bäst:  organisationsnummer, VAT-nummer, bankgiro, domän "
               "(pilkington.se). De ändras aldrig och kan inte förväxlas."),
    ("bullet", "Bra:  firmanamnet, som appen oftast plockar ur brevhuvudet."),
    ("bullet", "Undvik:  produktnamn och orter. \"Glas\" och \"Stockholm\" "
               "finns i konkurrenternas papper också."),
    ("note", "Ett ord märkt med ⚠ används redan av en annan kategori. "
             "Bockar du i det ändå blir de två kategorierna svåra att skilja åt."),
    ("body", "Vill du att appen ska slita sig med en viss fil för gott? "
             "Klicka Ignorera filen i rutan. Filen känns igen på sitt "
             "innehåll - även om den byter namn - och lämnas orörd vid "
             "alla framtida skanningar. Ångras i Inställningar → "
             "Ignorera filer → Sluta ignorera markerad."),

    ("h2", "Ett svar räcker"),
    ("body", "När du matchat en fil mot ett ord skannas allt osorterat om "
             "automatiskt i bakgrunden. Lär du appen att \"offert\" betyder "
             "Offerter flyttas alla väntande offerter dit på en gång — även "
             "de som redan hamnat i _Osorterat."),
    ("bullet", "Kön töms från allt som den nya regeln täcker."),
    ("bullet", "Inmapparna gås igenom på nytt."),
    ("bullet", "_Osorterat plockas upp igen."),
    ("bullet", "Redan sorterade filer rörs aldrig."),
    ("note", "Har du redigerat stödord under Matchningar eller i JSON-fliken "
             "kan du klicka \"Skanna om alla\" på fliken Granska. Vill du "
             "hellre ta en fil i taget: kryssa ur \"Skanna om allt när ett "
             "nytt stödord lärts in\" under Inställningar."),

    ("h2", "Kräv flera stödord för en kategori"),
    ("body",
     "Har en kategori breda ord som lätt ger falska träffar kan du kräva "
     "att flera stödord matchar innan en fil flyttas dit. Under "
     "Matchningar finns fältet Kräver — sätt det till 3 så måste tre "
     "olika stödord finnas i dokumentet."),
    ("body",
     "Siffran 0 betyder att kategorin följer den vanliga strikthetsnivån. "
     "Kolumnen REGEL i kategorilistan visar vilka kategorier som har egna "
     "krav."),
    ("note",
     "Ett bevisat organisationsnummer, VAT-nummer, bankgiro eller en domän "
     "i brevhuvudet räcker ändå ensamt. Ett dokument som redan är bevisat "
     "stoppas inte av en räkneregel."),

    ("h2", "Årsmappar - sortera efter datum"),
    ("body",
     "Har du hundratals filer i en kategorimapp blir den snabbt oöverskådlig. "
     "Appen kan läsa dokumentets datum och lägga filen i en undermapp per år: "
     "Pilkington/2024/, Pilkington/2025/ och så vidare."),
    ("body",
     "Slå på det under Inställningar, kortet \"Datum och undermappar\". "
     "Där väljer du också standardmall - år, år och månad, eller kvartal. "
     "Varje kategori kan ha en egen mall under Matchningar."),
    ("note",
     "Appen väljer fakturadatum före förfallodatum. Ett förfallodatum ligger "
     "en månad fram och skulle lägga decemberfakturor i fel år."),
    ("body",
     "Hittas inget datum i filen väljer du vad som ska hända: lägga den "
     "direkt i kategorimappen (standard), i en mapp som heter \"Utan datum\", "
     "eller använda filens egen tidsstämpel."),
    ("note",
     "Redan sorterade filer flyttas inte när du slår på funktionen. Den "
     "gäller nya filer."),

    ("h2", "Sortera på projektnummer"),
    ("body", "Har du ett projekt- eller objektnummer, till exempel IF26, "
             "räcker det att lära appen det en enda gång. Alla filer som "
             "innehåller numret hamnar sedan i samma mapp."),
    ("body", "Numret hittas var som helst i dokumentet - i brevhuvudet, mitt "
             "i en mening, i en tabell eller på sista sidan. Appen läser hela "
             "filen, inte bara första sidan."),
    ("bullet", "IF26 matchar även IF26-2024, IF26_bilaga, IF26:1 och (IF26)."),
    ("bullet", "IF26 matchar däremot inte IF260 eller IF26A - det är andra "
               "projekt och ska inte blandas ihop."),
    ("bullet", "Stora och små bokstäver spelar ingen roll."),
    ("note", "Koder som blandar bokstäver och siffror räknas som säkra bevis. "
             "Ingen skriver \"IF26\" av en slump, så numret räcker ensamt även "
             "om inget annat i filen matchar."),
    ("body", "När du lärt appen numret skannas allt osorterat om automatiskt, "
             "så filer som redan ligger i granskningskön eller i _Osorterat "
             "flyttas med på en gång. Du behöver inte göra om något."),

    ("h2", "Bevisade nummer går före allt annat"),
    ("body", "Ett organisationsnummer med giltig kontrollsiffra, eller "
             "företagets egen domän, är ett bevis. Sådana nummer nämns inte "
             "i förbigående — de står där för att de tillhör avsändaren."),
    ("body", "Hittar appen ett sådant bevis på avsändarens plats sorteras "
             "filen även om inget annat matchar. Ett leveransbesked utan "
             "firmanamn, men med org.nr i sidfoten, hamnar alltså rätt."),
    ("note", "Kontrollsiffran räknas verkligen efter. Ett tiosiffrigt "
             "kundnummer som liknar ett org.nr ger ingen genväg — det "
             "behandlas som ett vanligt referensnummer."),
    ("body", "Undantaget är när två företag har varsitt bevisat nummer, som "
             "i ett avtal mellan parter. Då frågar appen, för då är "
             "dokumentet genuint tvetydigt."),

    ("h2", "Se och ändra dina matchningar"),
    ("body", "Fliken Matchningar visar allt appen har lärt sig. Till vänster "
             "ligger kategorierna, till höger stödorden för den kategori du "
             "markerat. Du behöver aldrig öppna en JSON-fil för att ändra "
             "något."),
    ("bullet", "TRÄFFAR visar hur många filer ordet har fångat. Ett ord med "
               "många träffar är ett bra ord."),
    ("bullet", "TYP berättar vad appen anser att ordet är. Organisationsnummer, "
               "domäner, VAT-nummer och bankgiro räknas som starka bevis och "
               "visas i grönt."),
    ("bullet", "VIKT styr hur tungt ordet väger. Dubbelklicka på en rad för att "
               "ändra: 1 för vanliga ord, 2 för företagsnamn, 3 för org.nr."),
    ("bullet", "Sökfältet högst upp letar igenom alla kategorier samtidigt. "
               "Bra när du undrar vilken kategori ett visst ord hamnade i."),
    ("bullet", "Markera ett ord och tryck Delete, eller använd knappen Ta bort. "
               "Du får alltid en fråga först."),
    ("bullet", "Ändra ord rättar en felstavning utan att nollställa "
               "träffräknaren — det är samma ord, bara rättstavat."),
    ("bullet", "Flytta… flyttar ordet till en annan kategori med vikt och "
               "statistik intakt."),
    ("bullet", "Högerklick på ett stödord samlar alla val på ett ställe."),
    ("body", "Knappen Rensa oanvända plockar bort alla stödord som aldrig gett "
             "en enda träff. Efter en tids användning samlas sådana ord — de "
             "gör ingen skada, men de skräpar ned listan och kan i värsta fall "
             "krocka med en annan kategori."),
    ("note", "Ta bort ett stödord påverkar inte filer som redan är sorterade. "
             "Det ändrar bara vad som händer med nya filer."),

    ("h2", "Vad appen läser i en PDF"),
    ("body", "Hela dokumentet gås igenom, inte bara första sidan:"),
    ("bullet", "All brödtext på alla sidor."),
    ("bullet", "Sidhuvud och sidfot — där står ofta org.nr och bankgiro."),
    ("bullet", "Anteckningar, stämplar och ifyllda formulärfält."),
    ("bullet", "Filnamnet och dokumentets egenskaper."),
    ("bullet", "Logotypbilder i brevhuvudet, via OCR."),
    ("note", "Sidfoten är särskilt värdefull på svenska fakturor: "
             "organisationsnummer och bankgiro står nästan alltid där, och "
             "de tillhör alltid avsändaren."),

    ("h2", "Avsändare, inte mottagare"),
    ("body", "Appen tittar på VAR i dokumentet ett stödord står, inte bara "
             "om det finns någonstans. Ett företagsnamn högst upp betyder "
             "att de skickat pappret. Samma namn under Fakturaadress "
             "betyder tvärtom att de är kund."),
    ("bullet", "I brevhuvudet eller filnamnet — räknas fullt ut."),
    ("bullet", "På en rad med org.nr eller bankgiro — räknas fullt ut."),
    ("bullet", "Mitt i löptexten — räknas som vanligt, men ett ensamt "
               "sådant ord räcker inte för att avgöra avsändare."),
    ("bullet", "I mottagarblocket — räknas till knappt en tredjedel, och "
               "filen hoppas över om alla träffar ligger där."),
    ("note", "Därför hamnar en faktura från transportbolaget till "
             "Pilkington inte längre i Pilkingtons mapp. I "
             "granskningsrutan står det var träffarna hittades."),

    ("h2", "Hur säker måste appen vara?"),
    ("body", "Nivån på fliken Inställningar styr hur mycket bevis som krävs innan "
             "en fil flyttas utan att fråga. Allt som inte når upp hamnar i "
             "granskningskön i stället — filer försvinner aldrig."),
    ("bullet", "Lös — ett svagt ord räcker. Sorterar mest, men fler hamnar fel."),
    ("bullet", "Normal — två olika stödord räcker, så länge ingen annan "
               "kategori också träffar. Passar de flesta."),
    ("bullet", "Strikt — kräver två stödord, dubbelt så hög poäng som "
               "tvåan, och att minst ett ord står i brevhuvudet eller "
               "filnamnet. Bra när det är viktigt att det blir rätt."),
    ("bullet", "Mycket strikt — kräver dessutom ett org.nr, VAT-nummer, "
               "bankgiro eller en domän. Nästan inga fel, men fler frågor."),
    ("bullet", "Egen — du ställer in de fem värdena själv."),
    ("note", "Börja på Normal. Ser du filer i fel mapp, höj till Strikt. "
             "Får du för många frågor, sänk igen. Redan sorterade filer "
             "påverkas inte när du byter nivå."),

    ("h2", "Bevakning"),
    ("body", "Med bevakning påslagen svepar appen igenom mapparna var femte "
             "sekund och tar hand om nya filer direkt. En fil rörs inte "
             "förrän den legat stilla i tre sekunder och är färdigskriven — "
             "därför kan appen inte råka ta en PDF mitt i en skanning."),
    ("body", "Osäkra filer samlas i kön i stället för att avbryta dig. "
             "Siffran på fliken Granska visar hur många som väntar."),

    ("h2", "Ikonen i systemfältet"),
    ("body", "Appen lägger sig vid klockan i stället för att stängas när du "
             "klickar på krysset. Högerklicka på ikonen för snabbmenyn: visa "
             "fönstret, sortera nu, slå på bevakning, öppna granskningskön "
             "eller avsluta."),
    ("body", "Att minimera fönstret är en egen sak: det stannar i "
             "aktivitetsfältet som vanliga program. Vill du hellre att även "
             "minimering ska gömma fönstret vid klockan, kryssa i "
             "\"Minimera till systemfältet\" under Inställningar."),
    ("body", "Ikonen visar ett dokument som delas upp i tre färgade mappar — "
             "precis vad appen gör. En grön prick betyder att bevakningen är "
             "igång, så du ser det även när fönstret är gömt."),
    ("note", "Under Inställningar finns knappen Spara ikonfil, om du vill "
             "använda ikonen till en egen genväg."),
    ("body", "Vill du att appen ska starta med datorn: kryssa i \"Starta "
             "automatiskt med datorn\" och gärna även \"Starta minimerad\" "
             "och \"Starta bevakningen direkt\". Då sköter den sig helt själv."),

    ("h2", "Om något blir fel"),
    ("bullet", "Fil i fel mapp?  Gå till Historik, markera raden och klicka "
               "Ångra valda. Filen flyttas tillbaka."),
    ("bullet", "Fortsätter det bli fel?  Fliken Matchningar → sortera på "
               "Träffar och ta bort stödord som är för allmänna."),
    ("bullet", "Hittar den ingenting?  Filen kan vara inskannad. Kryssa i "
               "OCR och kontrollera att Tesseract är installerat "
               "(statusraden längst ned visar det)."),
    ("bullet", "Är skanningen blek eller sned?  Kryssa i \"Bättre OCR\" under "
               "Inställningar - då rätas sidan upp, trösklas och körs genom "
               "flera OCR-lägen, och det bästa resultatet vinns."),
    ("bullet", "Sorterar den efter kunden i stället för leverantören?  Ta "
               "bort kundens stödord under Matchningar — appen väger redan "
               "ned allt som står under Leveransadress och Kundnr."),

    ("h2", "Var sparas allt?"),
    ("body", "Tre JSON-filer, som du kan läsa och redigera direkt under "
             "fliken JSON:"),
    ("bullet", "rules.json — alla kategorier och stödord. Det här är "
               "hjärtat. Exportera den som säkerhetskopia."),
    ("bullet", "settings.json — mappar och inställningar."),
    ("bullet", "history.json — varje flyttad fil, underlaget för Ångra."),
    ("note", "Knappen Kontrollera säger till om något är fel i JSON-koden "
             "innan du sparar, så du inte kan råka förstöra regelfilen."),

    ("h2", "Bra att veta"),
    ("bullet", "Ingenting lämnar datorn. Inga nätverksanrop, ingen molntjänst."),
    ("bullet", "Filer skrivs aldrig över. Krockar döps om till \"faktura (2).pdf\"."),
    ("bullet", "Trasiga och lösenordsskyddade PDF:er lämnas orörda och loggas."),
    ("bullet", "Filer som är öppna i Acrobat hoppas över och tas nästa svep."),
    ("bullet", "Flytt mellan olika diskar sker med kopiera, verifiera, radera."),

    ("h2", "Kommandorad"),
    ("body", "Frivilligt — allt går att göra i fönstret. Praktiskt för "
             "schemaläggning:"),
    ("code", "python pdfsorter.py --status\n"
             "python pdfsorter.py -i INMAPP -o UTMAPP --no-ask\n"
             "python pdfsorter.py -i INMAPP -o UTMAPP --dry-run --verbose\n"
             "python pdfsorter.py --watch\n"
             "python pdfsorter.py --install-autostart\n"
             "python pdfsorter.py --make-shortcut"),

    ("h2", "Felsöka en enskild fil"),
    ("body", "Hamnade en PDF i fel mapp? Kör läsmodulen mot den i ett "
             "terminalfönster så ser du exakt vad appen ser:"),
    ("code", "python pdfsorter_read.py \"C:\\sokvag\\filen.pdf\""),
    ("body", "Utskriften visar antal sidor, om OCR användes, vad som stod i "
             "sidhuvud och sidfot, vilken mapp appen gissar på och alla tio "
             "ordförslagen med poäng. Lägg till --text för hela texten."),

    ("h2", "Appen körs bara en gång"),
    ("body",
     "Startar du appen medan den redan kör — till exempel genom att "
     "dubbelklicka på ikonen när autostart redan öppnat den — startas ingen "
     "andra kopia. I stället visas det fönster som redan finns."),
    ("note",
     "Det är med flit. Två appar som kör samtidigt skriver över varandras "
     "matchningar, och den som sparar sist vinner. Då kan stödord du lagt "
     "in försvinna utan att du märkt något."),
    ("body",
     "Kraschar appen ligger en låsfil kvar, men den hindrar inget: appen "
     "ser att processen inte längre finns och tar över låset vid nästa "
     "start."),

    ("h2", "Om appen inte startar"),
    ("body", "Kraschar den skrivs felet till krasch.log i inställningsmappen, "
             "och en ruta visar vad som hände. Saknas ett tillägg installeras "
             "de så här:"),
    ("code", "pip install pymupdf pypdf pdfminer.six pystray pillow pytesseract"),
    ("note", "Alla är valfria — appen startar ändå och talar om i statusraden "
             "vad som saknas. OCR kräver dessutom programmet Tesseract."),
]


def help_as_text() -> str:
    """Hjälpen som ren text, för att sparas till fil. Memo-cachad
    (snabbhet): strängen byggs en gång per körning."""
    global _HELP_TEXT_CACHE
    if _HELP_TEXT_CACHE is not None:
        return _HELP_TEXT_CACHE
    lines = [f"{APP_NAME} {APP_VERSION} - hjälp", "=" * 46, ""]
    for kind, text in HELP_CONTENT:
        if kind == "h1":
            continue
        if kind == "h2":
            lines += ["", text.upper(), "-" * len(text)]
        elif kind == "bullet":
            lines.append("  " + text)
        elif kind == "code":
            lines += ["    " + ln for ln in text.splitlines()]
        elif kind == "note":
            lines.append("  OBS: " + text)
        else:
            lines.append(text)
        lines.append("")
    _HELP_TEXT_CACHE = "\n".join(lines)
    return _HELP_TEXT_CACHE


#: Innehållet i pdfsorter.pyw, exakt som det ska skrivas. Startfilen
#: är flyttbar (hittar pdfsorter.py bredvid sig själv) och måste därför
#: inte innehålla några absoluta sökvägar. install_helpers() skriver om
#: filen bara när innehållet skiljer sig - aldrig i onödan.
LAUNCHER_PYW = r"""# -*- coding: utf-8 -*-
# Startar ArkivPiloten utan konsolfönster - dubbelklicka mig.
#
# Robust startfil (v1.4.0):
#   * Flyttbar: hittar pdfsorter.py bredvid sig själv i stället för en
#     hårdkodad sökväg - hela mappen kan flyttas utan att startfilen dör.
#   * Rätt ikon i aktivitetsfältet: AppUserModelID sätts före första
#     fönstret, så Windows visar vår ikon i stället för Pythons fjäder.
#   * Tyst felhantering: pythonw har ingen konsol, så stdout/stderr styrs
#     om och startfel visas i en dialog + skrivs till logg.
#   * Snål med minne: inget annat än standardbiblioteket laddas här;
#     allt tungt händer först inne i huvudprogrammet.
#   * Argument skickas vidare: pdfsorter.pyw --tray fungerar.

import os
import sys
from pathlib import Path

#: Eget program-ID för Windows. Utan detta grupperar Windows fönstret
#: under pythonw.exe och visar Pythons ikon i aktivitetsfältet.
_APP_ID = "ArkivPiloten.App.1"


def _config_dir():
    # Portabel (2026-10-05): appmappen först (fungerar på USB/varsom),
    # PDFSORTER_HOME styr om satt. Är appmappen skrivskyddad (t.ex.
    # /Applications eller /opt) används användarens data-mapp, annars
    # kunde startaren inte ens skriva sin kraschlogg.
    env = os.environ.get("PDFSORTER_HOME")
    if env:
        return Path(env).expanduser()
    hem = Path(__file__).resolve().parent
    try:
        t = hem / ".pdfsorter_write_test"
        t.write_text("ok", encoding="utf-8")
        t.unlink()
        return hem
    except OSError:
        pass
    if sys.platform.startswith("win"):
        bas = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(bas) / "ArkivPiloten"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ArkivPiloten"
    return Path.home() / ".config" / "pdfsorter"


def _fixa_stdio():
    # pythonw har ingen konsol: sys.stdout/sys.stderr är None, vilket får
    # print() och felrapporter att själva krascha. Styr om dem.
    try:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            logg = _config_dir() / "logs" / "startare.log"
            logg.parent.mkdir(parents=True, exist_ok=True)
            sys.stderr = open(logg, "a", encoding="utf-8", buffering=1)
    except OSError:
        pass


def _fel_dialog(text):
    # Sista utvägen utan konsol: en dialog som stänger sig själv efter
    # två minuter så att inget kan hänga sig i oändlighet.
    try:
        import tkinter as tk
        from tkinter import messagebox
        rot = tk.Tk()
        rot.withdraw()
        try:
            rot.after(120_000, rot.destroy)
            messagebox.showerror("ArkivPiloten", text)
        finally:
            rot.destroy()
    except Exception:
        pass


def main():
    _fixa_stdio()

    huvud = Path(__file__).resolve().with_suffix(".py")
    if not huvud.is_file():
        _fel_dialog("Hittade inte pdfsorter.py bredvid startfilen.\n\n"
                    "Lägg pdfsorter.pyw i samma mapp som pdfsorter.py.")
        return 1

    # Stabila förhållanden för huvudprogrammet: rätt arbetskatalog,
    # rätt sys.argv[0] och möjlighet att importera grannmodulerna.
    try:
        os.chdir(huvud.parent)
    except OSError:
        pass
    sys.argv = [str(huvud)] + list(sys.argv[1:])
    if str(huvud.parent) not in sys.path:
        sys.path.insert(0, str(huvud.parent))

    if sys.platform.startswith("win"):
        # Måste ske före det första fönstret skapas för att ge vår ikon
        # i aktivitetsfältet. Kan aldrig få starten att misslyckas.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_APP_ID)
        except Exception:
            pass

    import runpy
    try:
        runpy.run_path(str(huvud), run_name="__main__")
        return 0
    except SystemExit as exc:
        kod = exc.code
        if kod is None:
            return 0
        return kod if isinstance(kod, int) else 1
    except BaseException:
        # Försök appens egen felrapport (logg + dialog med ikon). Finns
        # inte systemmodulen skrivs felet direkt till krasch.loggen.
        exc = sys.exc_info()[1]
        try:
            import pdfsorter_system
            pdfsorter_system.crash_report(exc)
        except Exception:
            import traceback
            text = traceback.format_exc()
            try:
                # Alla loggar bor i log-mappen (användarorder).
                logg = _config_dir() / "logs" / "krasch.log"
                logg.parent.mkdir(parents=True, exist_ok=True)
                with open(logg, "a", encoding="utf-8") as fh:
                    fh.write("\n===== startare =====\n" + text)
            except Exception:
                pass
            _fel_dialog(f"ArkivPiloten kunde inte starta.\n\n{text[:1500]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
"""


def install_helpers() -> List[str]:
    """Skapa hjälpfiler för start utan terminal, bredvid pdfsorter.py.

    Windows:  pdfsorter.pyw  - dubbelklick startar utan svart konsolfönster
    macOS/Linux: start-pdfsorter.command / .sh - körbara startfiler
    """
    made: List[str] = []
    here = _main_script

    def _skriv(path: Path, content: str, exe: bool = False) -> None:
        # Självläkande: gamla starthjälpare (flyttad mapp, ny python)
        # skrivs om i stället för att peka fel i all evighet.
        if path.exists():
            try:
                if path.read_text(encoding="utf-8") == content:
                    return
            except OSError:
                return
        path.write_text(content, encoding="utf-8")
        if exe:
            path.chmod(0o755)
        made.append(str(path))

    try:
        if sys.platform.startswith("win"):
            _skriv(here.with_suffix(".pyw"), LAUNCHER_PYW)
        elif sys.platform == "darwin":
            _skriv(here.parent / "Starta ArkivPiloten.command",
                   f'#!/bin/sh\ncd "{here.parent}"\n'
                   f'exec "{sys.executable}" "{here}" "$@"\n', exe=True)
        else:
            _skriv(here.parent / "starta-pdfsorter.sh",
                   f'#!/bin/sh\ncd "{here.parent}"\n'
                   f'exec "{sys.executable}" "{here}" "$@"\n', exe=True)
    except OSError:
        pass
    return made


def crash_report(exc: BaseException) -> None:
    """Visa fel i en ruta i stället för att bara försvinna.

    Vid dubbelklick finns ingen terminal som kan visa ett spårningsmeddelande,
    så felet skrivs till loggfiler och visas i en dialogruta. ALLA loggar
    bor i log-mappen (användarorder 2026-09-07): krasch.log flyttad dit,
    och felet skrivs även till månadens errors.log och till pågående
    sessionslogg, så att allt hamnar på ett ställe.
    """
    import traceback
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    # Felsökningsdesign: kraschloggen får versionsbanner, så att en support-
    # person direkt ser vilka modulversioner som körde.
    text = (f"{APP_NAME} {APP_VERSION} | Python {sys.version.split()[0]} | "
            f"{_mod_versions_line()}\n" + text)
    # Även i den löpande sessionsloggen, om en körning redan pågår -
    # då syns kraschen i sitt sammanhang (vad hände precis innan).
    session_log("krasch", text.rstrip(), level="err")
    log = None
    for target in (session_dir() / "krasch.log", _month_log_path("errors")):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(f"\n===== {now_iso()} =====\n{text}")
            log = log or target
        except Exception:
            pass
    # pythonw har ingen konsol: sys.stderr kan vara None - då får inte
    # själva felrapporten krascha.
    try:
        sys.stderr.write(text)
    except Exception:
        pass
    # VIKTIGT (buggfix 2026-10-15): ett ANDRA Tk-fönster i samma
    # process (t.ex. från tray-tråden) kan vid destroy() riva med
    # huvudfönstret ("application has been destroyed") och lämna en
    # zombie som håller instanslåset - appen gick inte att öppna igen.
    # Därför: dialog ENDAST från huvudtråden och ENDAST när inget
    # Tk-fönster redan lever; annars bara logg.
    try:
        import tkinter as tk
        from tkinter import messagebox
        i_huvudtrad = threading.current_thread() is threading.main_thread()
        levande_rot = None
        try:
            levande_rot = tk._default_root
            if levande_rot is not None and not levande_rot.winfo_exists():
                levande_rot = None
        except Exception:
            levande_rot = None
        if not i_huvudtrad or levande_rot is not None:
            session_log("krasch", "Felrapport utan dialog (tråd/fönster-läge)",
                        "warn")
            return
        set_app_user_model_id()
        root = tk.Tk()
        root.withdraw()
        brand_window(root)
        # Hängningsskydd: rutan stänger sig själv efter 2 minuter, så att
        # en kraschdialog aldrig kan blockera t.ex. en schemalagd start
        # i oändlighet.
        try:
            root.after(120_000, root.destroy)
        except Exception:
            pass
        try:
            messagebox.showerror(
                APP_NAME,
                f"{APP_NAME} kunde inte starta.\n\n{type(exc).__name__}: {exc}\n\n"
                + (f"Detaljer sparade i:\n{log}" if log else ""))
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass
    except Exception:
        pass


def _month_log_path(name: str) -> Path:
    """Månadens loggfil: logs/<ÅÅÅÅ-MM>/<name>.log (REQ-N1)."""
    from datetime import datetime
    return config_dir() / "logs" / datetime.now().strftime("%Y-%m") / f"{name}.log"


# --------------------------------------------------------------------------
# Sessionslogg: logga ALLT till en egen log-mapp (ANVÄNDARORDER 2026-09-07)
# --------------------------------------------------------------------------
# Varje körning får en egen loggfil i logs/<ÅÅÅÅ-MM>/:
#     app_<datum>_<tid>_<session>.log
# Dit skrivs allt: starter, inställningar, varje knapptryck, varför
# fönstret visas eller inte visas, varje matchningsbeslut med poäng och
# zoner, flyttar, fel och avslut. Tanken är att användaren ska kunna
# kopiera filens innehåll och klistra in det i en felanmälan - och att
# den som läser direkt ska se vad som hände och varför.

import uuid as _uuid
from datetime import datetime as _dt

#: Unikt id för körningen. Sätts av start_session(); innan dess tomt.
SESSION_ID: str = ""

_SESSION_FH: Optional[Any] = None        # öppen filhandle (radbuffrad)
_SESSION_PATH: Optional[Path] = None
#: RLock: close_session() skriver en sista rad medan det håller låset,
#: och session_log() tar samma lås - ett vanligt Lock skulle låsa sig.
_SESSION_LOCK = threading.RLock()
_SESSION_MAX_BYTES = 8_000_000           # rotera efter 8 MB
_SESSION_PART = 1
_SESSION_BASE: Optional[Path] = None     # roteringsnamn utgår härifrån
_OLD_EXCEPTHOOK: Optional[Any] = None
_OLD_THREADHOOK: Optional[Any] = None

_LEVELS = {"info": "INFO", "ok": "OK", "warn": "VARN", "err": "FEL",
           "fel": "FEL", "debug": "DEBUG"}


def session_dir() -> Path:
    """Appens log-mapp - ALLA loggar bor här (användarorder)."""
    return config_dir() / "logs"


class LogContext:
    """Tidsmätt loggblock: ▶ START / ✔ KLART (ms) / ✗ FEL (ms) (L5).

    Används runt tunga operationer (OCR, filanalys, batchsortering) så
    att sessionsloggen visar exakt var tiden tar vägen - utan att
    anroparen behöver mäta manuellt. Undantag loggas och propagerar.
    """

    def __init__(self, category: str, label: str):
        self.category = category
        self.label = label
        self._t0 = 0.0

    def __enter__(self) -> "LogContext":
        self._t0 = time.perf_counter()
        session_log(self.category, f"▶ {self.label}")
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        ms = (time.perf_counter() - self._t0) * 1000.0
        if exc_type is not None:
            session_log(self.category,
                        f"✗ {self.label} ({ms:.0f} ms): "
                        f"{exc_type.__name__}: {exc}", level="err")
        else:
            session_log(self.category, f"✔ {self.label} ({ms:.0f} ms)",
                        level="ok")
        return False                       # undantag propagerar




# --------------------------------------------------------------------------
# QR-KODARE - beroendefri (Swish-QR m.m., ANVÄNDARORDER 2026-10-15)
# --------------------------------------------------------------------------
# Byte-läge, EC-nivå M, version 1-6, mask 0. Verifierad mot oberoende
# avkodare (OpenCV) - payloaden avkodas tecken för tecken identiskt, vilket
# är jämförelsen med "originalet": samma payload => samma betalning.
def _gf_mul(a: int, b: int) -> int:
    r = 0
    while b:
        if b & 1:
            r ^= a
        a <<= 1
        if a & 0x100:
            a ^= 0x11D
        b >>= 1
    return r


def _pow2(i: int) -> int:
    a = 1
    for _ in range(i):
        a <<= 1
        if a & 0x100:
            a ^= 0x11D
    return a


def _rs_gen(n: int) -> List[int]:
    g = [1]
    for i in range(n):
        ai = _pow2(i)
        ng = [0] * (len(g) + 1)
        for j in range(len(g) + 1):
            term = g[j] if j < len(g) else 0
            prev = g[j - 1] if j >= 1 else 0
            ng[j] = term ^ _gf_mul(ai, prev)
        g = ng
    return g


def _rs_ec(data: List[int], n: int) -> List[int]:
    g = _rs_gen(n)
    res = list(data) + [0] * n
    for i in range(len(data)):
        c = res[i]
        if c:
            for j, gc in enumerate(g):
                res[i + j] ^= _gf_mul(gc, c)
    return res[len(data):]


_QR_M_TABLE = {1: (10, [16]), 2: (16, [28]), 3: (26, [44]),
               4: (18, [32, 32]), 5: (24, [43, 43]), 6: (16, [27] * 4)}
_QR_CAP = {1: 14, 2: 26, 3: 42, 4: 62, 5: 84, 6: 106}


def _bch_format(data5: int) -> int:
    rem = data5
    for i in range(14, 9, -1):
        if (rem >> i) & 1:
            rem ^= 0x537 << (i - 10)
    return ((data5 << 10) | rem) ^ 0x5412


def qr_matrix(text: str) -> List[List[int]]:
    """QR-matris (0/1) för texten. ValueError om den är för lång (>106 B)."""
    data = text.encode("utf-8")
    ver = next((v for v in range(1, 7) if len(data) <= _QR_CAP[v]), 0)
    if not ver:
        raise ValueError("för lång payload för inbyggd QR (max 106 byte)")
    ec_n, blocks = _QR_M_TABLE[ver]
    size = 17 + ver * 4
    bits: List[int] = []

    def put(val: int, n: int) -> None:
        for i in range(n - 1, -1, -1):
            bits.append((val >> i) & 1)

    put(0b0100, 4)
    put(len(data), 8)
    for b in data:
        put(b, 8)
    total_data = sum(blocks)
    put(0, min(4, total_data * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    cw = [int("".join(map(str, bits[i:i + 8])), 2)
          for i in range(0, len(bits), 8)]
    pad = [0xEC, 0x11]
    i = 0
    while len(cw) < total_data:
        cw.append(pad[i % 2])
        i += 1
    d_blocks, e_blocks, pos = [], [], 0
    for nb in blocks:
        d = cw[pos:pos + nb]
        pos += nb
        d_blocks.append(d)
        e_blocks.append(_rs_ec(d, ec_n))
    seq: List[int] = []
    for i in range(max(len(b) for b in d_blocks)):
        for b in d_blocks:
            if i < len(b):
                seq.append(b[i])
    for i in range(ec_n):
        for b in e_blocks:
            seq.append(b[i])

    m = [[0] * size for _ in range(size)]
    fn = [[False] * size for _ in range(size)]

    def setm(r: int, c: int, v: int) -> None:
        m[r][c] = v
        fn[r][c] = True

    def finder(r0: int, c0: int) -> None:
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = r0 + dr, c0 + dc
                if 0 <= r < size and 0 <= c < size:
                    ins = 0 <= dr <= 6 and 0 <= dc <= 6
                    ring = ins and (dr in (0, 6) or dc in (0, 6)
                                    or 2 <= dr <= 4 and 2 <= dc <= 4)
                    setm(r, c, 1 if ring else 0)

    finder(0, 0)
    finder(0, size - 7)
    finder(size - 7, 0)
    for i in range(size):
        if not fn[6][i]:
            setm(6, i, i % 2 == 0)
        if not fn[i][6]:
            setm(i, 6, i % 2 == 0)
    if ver >= 2:
        a = {2: 18, 3: 22, 4: 26, 5: 30, 6: 34}[ver]
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                setm(a + dr, a + dc, 1 if max(abs(dr), abs(dc)) != 1 else 0)
    fmt = _bch_format(0b00000)                      # EC M + mask 0
    fb = [(fmt >> i) & 1 for i in range(14, -1, -1)]
    c1 = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
          (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    c2 = [(size - 1, 8), (size - 2, 8), (size - 3, 8), (size - 4, 8),
          (size - 5, 8), (size - 6, 8), (size - 7, 8), (8, size - 8),
          (8, size - 7), (8, size - 6), (8, size - 5), (8, size - 4),
          (8, size - 3), (8, size - 2), (8, size - 1)]
    for i, (r, c) in enumerate(c1):
        setm(r, c, fb[i])
    for i, (r, c) in enumerate(c2):
        setm(r, c, fb[i])
    setm(size - 8, 8, 1)
    bits = []
    for c in seq:
        for i in range(7, -1, -1):
            bits.append((c >> i) & 1)
    bi = 0
    col = size - 1
    up = True
    while col > 0:
        if col == 6:
            col -= 1
        rng = range(size - 1, -1, -1) if up else range(size)
        for r in rng:
            for c in (col, col - 1):
                if not fn[r][c]:
                    v = bits[bi] if bi < len(bits) else 0
                    bi += 1
                    if (r + c) % 2 == 0:            # mask 0
                        v ^= 1
                    m[r][c] = v
        col -= 2
        up = not up
    return m


def qr_png_bytes(text: str, scale: int = 8, border: int = 4) -> bytes:
    """QR-kod som PNG-bytes (svart/vit, inga beroenden utöver Pillow)."""
    import io
    from PIL import Image
    m = qr_matrix(text)
    n = len(m)
    s = n + border * 2
    img = Image.new("1", (s * scale, s * scale), 1)
    px = img.load()
    for r in range(n):
        for c in range(n):
            if m[r][c]:
                for dr in range(scale):
                    for cc in range(scale):
                        px[(border + c) * scale + cc,
                           (border + r) * scale + dr] = 0
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def swish_payload(number: str, amount: Optional[int] = None) -> str:
    """Swish-betalningslänk som QR-payload. Jämförelsen med originalet:
    samma payload => samma betalning öppnas vid skanning."""
    nr = "".join(ch for ch in (number or "") if ch.isdigit())
    url = f"https://swish.se/payment?swish={nr}"
    if amount:
        url += f"&amount={amount}"
    return url


def archive_old_logs(days: int = 3) -> int:
    """Arkivera sessionsloggar äldre än `days` dagar (ANVÄNDARORDER
    2026-10-15: "efter 3 dagar ska det arkiveras i årsmapp/månadsmapp").

    Flyttas till logs/arkiv/<ÅÅÅÅ>/<MM>/ - inget raderas någonsin.
    Returnerar antal flyttade filer. Körs vid varje sessionsstart.
    """
    flyttade = 0
    try:
        import time as _time
        gräns = _time.time() - days * 86400
        bas = session_dir()
        if not bas.is_dir():
            return 0
        for månadsmap in list(bas.iterdir()):
            if not månadsmap.is_dir() or månadsmap.name == "arkiv":
                continue
            for fil in list(månadsmap.glob("app_*.log")):
                try:
                    if fil.stat().st_mtime >= gräns:
                        continue
                    stamp = _dt.fromtimestamp(fil.stat().st_mtime)
                    dest = bas / "arkiv" / f"{stamp:%Y}" / f"{stamp:%m}"
                    dest.mkdir(parents=True, exist_ok=True)
                    mål = dest / (fil.name + ".gz")
                    if mål.exists():
                        mål = dest / (fil.stem + f"_{int(fil.stat().st_mtime)}"
                                      + ".log.gz")
                    import gzip
                    data = fil.read_bytes()
                    with gzip.open(mål, "wb") as fo:
                        fo.write(data)
                    fil.unlink()
                    flyttade += 1
                except Exception as exc:
                    # Tyst aldrig: arkiveringsfel syns i sessionsloggen
                    session_log("logg", f"Kunde inte arkivera {fil.name}: "
                                f"{type(exc).__name__}: {exc}", "warn")
                    continue
        if flyttade:
            session_log("logg", f"Arkiverade {flyttade} äldre loggfil(er) "
                        f"till logs/arkiv/ÅR/MÅNAD")
    except Exception:
        pass
    return flyttade


def migrate_legacy_logs() -> None:
    """Flytta gamla krasch.log från config-roten in i logs/ (L7).

    Körs en gång per session av start_session(). Nyast vinner: finns redan
    en krasch.log i logs/ parkeras den gamla som krasch-gammal.log,
    annars flyttas den. Raderas aldrig.
    """
    try:
        gammal = config_dir() / "krasch.log"
        if not gammal.exists():
            return
        ny = session_dir() / "krasch.log"
        if ny.exists():
            parkerad = config_dir() / "krasch-gammal.log"
            os.replace(gammal, parkerad)
            session_log("logg", f"Äldre krasch.log parkerad: {parkerad}")
        else:
            ny.parent.mkdir(parents=True, exist_ok=True)
            os.replace(gammal, ny)
            session_log("logg", f"Äldre krasch.log flyttad till log-mappen: {ny}")
    except OSError as exc:
        session_log("logg", f"Migrering av gammal krasch.log misslyckades: {exc}",
                    "warn")


def start_session(banner_lines: Optional[List[str]] = None) -> Optional[Path]:
    """Öppna körningens loggfil och skriv startbanderollen.

    Returnerar sökvägen (None om filen inte kan öppnas - loggning får
    aldrig sänka appen). Varje efterföljande session_log() hamnar i filen.
    """
    global SESSION_ID, _SESSION_FH, _SESSION_PATH, _SESSION_PART, _SESSION_BASE
    SESSION_ID = _uuid.uuid4().hex[:12]
    stamp = _dt.now()
    month = session_dir() / stamp.strftime("%Y-%m")
    base = f"app_{stamp.strftime('%Y%m%d_%H%M%S')}_{SESSION_ID}.log"
    try:
        month.mkdir(parents=True, exist_ok=True)
        path = month / base
        fh = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    with _SESSION_LOCK:
        _SESSION_FH, _SESSION_PATH, _SESSION_PART = fh, path, 1
        _SESSION_BASE = path
    migrate_legacy_logs()          # engångsflytt av äldre kraschlogg
    archive_old_logs(3)            # >3 dagar -> logs/arkiv/ÅR/MÅNAD
    bar = "=" * 78
    rader = [bar,
             f"{APP_NAME} {APP_VERSION} - sessionslogg  (session {SESSION_ID})",
             f"Startad: {stamp.astimezone().isoformat(timespec='seconds')}",
             f"Python:  {sys.version.split()[0]}  Plattform: {sys.platform}",
             f"Konfiguration: {config_dir()}",
             f"Moduler: {_mod_versions_line()}"]
    rader += list(banner_lines or [])
    rader.append(bar)
    for r in rader:
        session_log("start", r)
    return path


def _rotateIfNeeded() -> None:
    """Filen växer till max 8 MB, sedan fortsätter loggen i en ny del.
    Anropas under lås. Delarna får stabila namn utifrån grundfilen:
    app_..._del2.log, app_..._del3.log - aldrig kedjade _del2_del3."""
    global _SESSION_FH, _SESSION_PATH, _SESSION_PART
    if _SESSION_FH is None or _SESSION_PATH is None:
        return
    try:
        if _SESSION_PATH.stat().st_size < _SESSION_MAX_BYTES:
            return
        _SESSION_FH.close()
        _SESSION_PART += 1
        grund = _SESSION_BASE or _SESSION_PATH
        new = grund.with_name(grund.stem + f"_del{_SESSION_PART}.log")
        _SESSION_FH = open(new, "a", encoding="utf-8", buffering=1)
        _SESSION_PATH = new
        _SESSION_FH.write(f"--- fortsättning från föregående del "
                          f"(session {SESSION_ID}) ---\n")
    except OSError:
        pass


def close_session() -> None:
    """Stäng sessionsloggen (anropas vid avslut). Skrivningar efteråt
    blir no-ops - en ny start_session() kan öppna en ny session."""
    global _SESSION_FH, _SESSION_PATH
    with _SESSION_LOCK:
        if _SESSION_FH is not None:
            session_log("avslut", "Sessionsloggen stängs")
            try:
                _SESSION_FH.close()
            except Exception:
                pass
        _SESSION_FH, _SESSION_PATH = None, None


def session_log(category: str, message: str, level: str = "info") -> None:
    """Skriv en rad till sessionsloggen. Trådsäker, kastar aldrig.

    Radformat: HH:MM:SS.mmm  NIVÅ   kategori   meddelande
    Flerradiga meddelanden indenteras så att varje rad syns i klistret.
    """
    if _SESSION_FH is None:
        return
    nu = _dt.now()
    ts = nu.strftime("%H:%M:%S.") + f"{nu.microsecond // 1000:03d}"
    lvl = _LEVELS.get(level, "INFO").ljust(5)
    cat = (category or "app")[:10].ljust(10)
    try:
        with _SESSION_LOCK:
            _rotateIfNeeded()
            if _SESSION_FH is None:
                return
            lines = str(message).splitlines() or [""]
            _SESSION_FH.write(f"{ts}  {lvl} {cat} {lines[0]}\n")
            for ln in lines[1:]:
                _SESSION_FH.write(f"{'':22}{ln}\n")
    except Exception:
        pass


def session_error(category: str, exc: BaseException) -> None:
    """Logga ett undantag med fullt spårning - så att 'när och varför'
    syns direkt i loggen. Fungerar både inuti en except och när undantaget
    skickas in i efterhand (då byggs spårningen från exc.__traceback__)."""
    import traceback
    spår = traceback.format_exc()
    if not spår or spår.startswith("NoneType"):
        spår = "".join(traceback.format_exception(
            type(exc), exc, getattr(exc, "__traceback__", None)))
    session_log(category,
                f"{type(exc).__name__}: {exc}\n" + spår.rstrip(), level="err")


def session_path() -> Optional[Path]:
    """Körningens aktuella loggfil (roterad del om flera)."""
    return _SESSION_PATH


def latest_session_log() -> Optional[Path]:
    """Nyaste sessionsloggen över alla månader (för support/urklipp).

    Ordning: skrivningstid först, sedan delnummer - roterade delar heter
    ..._del2.log, ..._del10.log och måste jämföras numeriskt, inte som
    text ("del10" < "del9" alfabetiskt).
    """
    import re

    def nyckel(f: Path):
        try:
            ns = f.stat().st_mtime_ns
        except OSError:
            ns = 0
        m = re.search(r"_del(\d+)\.log$", f.name)
        return (ns, int(m.group(1)) if m else 0, f.name)

    try:
        bas = session_dir()
        if not bas.is_dir():
            return None
        for month in sorted(bas.iterdir(), reverse=True):
            try:
                filer = [f for f in month.iterdir()
                         if f.name.startswith("app_") and f.is_file()]
            except OSError:
                continue
            if filer:
                return max(filer, key=nyckel)
        return None
    except OSError:
        return None


def install_excepthooks() -> None:
    """Fånga alla ohanterade undantag till loggen (REQ-N1 AC-1.3).

    sys.excepthook fångar huvudtråden, threading.excepthook alla andra
    trådar. Felet skrivs både till sessionsloggen och till månadens
    errors.log, och appen fortsätter leva - ett fel i en tråd ska inte
    tysta hela programmet.
    """
    global _OLD_EXCEPTHOOK, _OLD_THREADHOOK
    if _OLD_EXCEPTHOOK is not None:
        return                       # redan installerad

    def _hook(exc_type, exc, tb):
        import traceback
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        session_log("oväntat", "Ohanderat undantag (huvudspåret):\n"
                    + text.rstrip(), level="err")
        _write_errors_log(text)
        try:
            _OLD_EXCEPTHOOK(exc_type, exc, tb)
        except Exception:
            pass

    def _thread_hook(args):
        import traceback
        text = "".join(traceback.format_exception(
            args.exc_type, args.exc_value, args.exc_traceback))
        session_log("oväntat",
                    f"Ohanderat undantag i tråd {args.thread.name if args.thread else '?'}:\n"
                    + text.rstrip(), level="err")
        _write_errors_log(text)

    _OLD_EXCEPTHOOK = sys.excepthook
    try:
        _OLD_THREADHOOK = getattr(threading, "excepthook", None)
        threading.excepthook = _thread_hook
    except Exception:
        pass
    sys.excepthook = _hook


def _write_errors_log(text: str) -> None:
    """Månadens errors.log - samlar alla ohanterade fel (REQ-N1)."""
    try:
        target = _month_log_path("errors")
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(f"\n===== {now_iso()} (session {SESSION_ID or '?'}) =====\n{text}")
    except Exception:
        pass


# =========================================================================
# AUTOUPPDATERING FRÅN GIT + UPPDATERING AV PYTHON-PAKET (2026-10-16)
# =========================================================================
#: Källan appen uppdaterar sig från när ny version läggs upp på GitHub.
UPDATE_REPO = "Tokke2/ArkivPiloten"
UPDATE_BRANCH = "main"
UPDATE_RAW_BASE = f"https://raw.githubusercontent.com/{UPDATE_REPO}/{UPDATE_BRANCH}"
UPDATE_ZIP_URL = f"https://codeload.github.com/{UPDATE_REPO}/zip/refs/heads/{UPDATE_BRANCH}"

#: GitHub Releases är den primära uppdateringskanalen (1.4.0). Varje
#: publicerad release har ett färdigt paket + SHA256SUMS.txt, vilket gör
#: att appen kan verifiera innehållet innan något skrivs. Grenen ovan
#: finns kvar som reserv om API:t eller releasen inte kan läsas.
UPDATE_RELEASES_LATEST = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
UPDATE_ASSET_NAME = "ArkivPiloten.zip"
UPDATE_SUMS_NAME = "SHA256SUMS.txt"

#: Bara dessa filer får ersättas av en uppdatering - allt i appmappen.
#: Användardata (json/, logs/, cache/, backups/, updates/) rörs ALDRIG,
#: och inte heller användarens egna filer i mappen.
UPDATE_FILES = (
    "pdfsorter.py", "pdfsorter.pyw", "pdfsorter_data.py",
    "pdfsorter_read.py", "pdfsorter_system.py", "pdfsorter_theme.py",
    "requirements.txt", "install.sh", "ArkivPiloten.png", "ArkivPiloten.ico",
    # Engångsuppgraderingen från 1.0.0/1.1.0. Ligger kvar i mappen så att
    # den som behöver den slipper leta.
    "uppgradera-arkivpiloten.bat", "uppgradera-arkivpiloten.sh",
    "ArkivPiloten - Installera senaste Python och starta.bat",
    "README.md", "PDFSORTER_SPEC.md", "Stöd ArkivPiloten.html",
    "swish_qr.png", "desktop.ini",
)

_PIP_PAKET_NAMN = ("PyMuPDF", "pypdf", "pdfminer.six", "Pillow",
                   "pystray", "pytesseract")
_PIP_IMPORTNAMN = {"PyMuPDF": "fitz", "pypdf": "pypdf",
                   "pdfminer.six": "pdfminer", "Pillow": "PIL",
                   "pystray": "pystray", "pytesseract": "pytesseract"}


def _version_tuple(s: str) -> Tuple[int, ...]:
    ut = []
    for del_ in str(s).strip().split("."):
        siff = "".join(ch for ch in del_ if ch.isdigit())
        ut.append(int(siff) if siff else 0)
    return tuple(ut or [0])


def _http_get(url: str, timeout: float = 15.0, accept: str = "*/*",
              limit: int = 4_000_000) -> bytes:
    """Hämta en liten resurs (JSON/text) med appens User-Agent."""
    import urllib.request
    req = urllib.request.Request(
        url, headers={"User-Agent": APP_NAME, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as svar:
        return svar.read(limit)


def _latest_release(timeout: float = 15.0) -> Optional[dict]:
    """Läs senaste publicerade GitHub-releasen (aldrig draft/förhandsvisning)."""
    try:
        raw = _http_get(UPDATE_RELEASES_LATEST, timeout,
                        "application/vnd.github+json")
        data = json.loads(raw.decode("utf-8", "ignore"))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name") or "").strip()
    version = tag[1:] if tag[:1] in ("v", "V") else tag
    if not re.match(r"^[0-9][0-9A-Za-z.\-]*$", version):
        return None
    assets: Dict[str, str] = {}
    for a in data.get("assets") or []:
        if (isinstance(a, dict) and a.get("name")
                and a.get("browser_download_url")):
            assets[str(a["name"])] = str(a["browser_download_url"])
    zip_url = assets.get(UPDATE_ASSET_NAME)
    if not zip_url:
        # Tillåt versionsnamngivna paket (ArkivPiloten-1.4.0.zip).
        for namn, url in sorted(assets.items()):
            if namn.lower().startswith("arkivpiloten") and namn.lower().endswith(".zip"):
                zip_url = url
                break
    sums_url = assets.get(UPDATE_SUMS_NAME)
    notes = str(data.get("body") or "")
    # Releases som saknar bifogade filer (t.ex. när API-uppladdningen
    # inte är tillgänglig) kan ändå användas: då hämtas GitHubs
    # tagg-arkiv och kontrollsumman läses ur release-texten.
    m_sha = re.search(r"SHA-?256[^\n]{0,80}?([0-9a-fA-F]{64})", notes)
    body_sha = m_sha.group(1).lower() if m_sha else ""
    har_paketfil = bool(zip_url)
    if not zip_url and tag:
        zip_url = (f"https://codeload.github.com/{UPDATE_REPO}/zip/"
                   f"refs/tags/{tag}")
    # Kroppens summa gäller ENDAST tagg-arkivet. Finns ett bifogat
    # paket måste summan komma från dess SHA256SUMS.txt - annars skulle
    # fel fil kunna verifieras mot fel hash.
    return {
        "tag": tag,
        "version": version,
        "zip_url": zip_url or "",
        "sums_url": sums_url or "",
        "sha256": body_sha if (body_sha and not har_paketfil) else "",
        "release_url": str(data.get("html_url") or ""),
        "notes": notes[:4000],
    }


def check_for_update(timeout: int = 15) -> dict:
    """Finns en nyare version? Läser GitHub Releases först och faller
    tillbaka på UPDATE_BRANCH om API:t inte svarar. Inget laddas ner och
    inget ändras här - bara versionsjämförelse."""
    rel = _latest_release(timeout)
    if rel:
        return {
            "ok": True,
            "current": APP_VERSION,
            "remote": rel["version"],
            "available": (_version_tuple(rel["version"])
                          > _version_tuple(APP_VERSION)),
            "source": "release",
            "tag": rel["tag"],
            "zip_url": rel["zip_url"] or (
                f"https://codeload.github.com/{UPDATE_REPO}/zip/refs/tags/"
                f"{rel['tag']}"),
            "sha256_url": rel["sums_url"],
            "sha256": rel.get("sha256", ""),
            "release_url": rel["release_url"],
            "notes": rel["notes"],
        }
    try:
        # Reserv: läs versionsnumret direkt ur pdfsorter.py på grenen.
        text = None
        for url, accept in (
                (f"https://api.github.com/repos/{UPDATE_REPO}/contents/"
                 f"pdfsorter.py?ref={UPDATE_BRANCH}",
                 "application/vnd.github.raw+json"),
                (f"{UPDATE_RAW_BASE}/pdfsorter.py", "*/*")):
            try:
                text = _http_get(url, timeout, accept, 2_000_000).decode(
                    "utf-8", "ignore")
                break
            except Exception:
                continue
        if text is None:
            raise ConnectionError("GitHub svarade inte")
        m = re.search(r'APP_VERSION\s*=\s*"([0-9][0-9A-Za-z.\-]*)"', text)
        if not m:
            return {"ok": False, "current": APP_VERSION, "remote": None,
                    "available": False,
                    "error": "kunde inte läsa versionsnumret på GitHub"}
        remote = m.group(1)
        return {"ok": True, "current": APP_VERSION, "remote": remote,
                "available": _version_tuple(remote) > _version_tuple(APP_VERSION),
                "source": "branch", "tag": "",
                "zip_url": UPDATE_ZIP_URL, "sha256_url": "",
                "sha256": "", "release_url": "", "notes": ""}
    except Exception as exc:
        return {"ok": False, "current": APP_VERSION, "remote": None,
                "available": False, "error": f"{type(exc).__name__}: {exc}"}


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            bit = fh.read(chunk)
            if not bit:
                break
            h.update(bit)
    return h.hexdigest()


def _sha_from_sums(text: str, names) -> Optional[str]:
    """Plocka ut rätt rad ur ett SHA256SUMS.txt (sha256sum-format)."""
    wanted = {str(n).strip().lstrip("*") for n in names if n}
    for rad in text.splitlines():
        delar = rad.replace("*", " ").split()
        if len(delar) >= 2 and re.fullmatch(r"[0-9a-fA-F]{64}", delar[0]):
            if delar[-1].split("/")[-1] in wanted:
                return delar[0].lower()
    return None


def _safe_extract(zippath: Path, dest: Path) -> Tuple[bool, str]:
    """Packa upp en zip utan att något hamnar utanför dest (zip-slip)."""
    import zipfile as _zip
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    dest_res = dest.resolve()
    total = 0
    try:
        with _zip.ZipFile(zippath) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                total += int(info.file_size or 0)
                if total > 300 * 1024 * 1024:
                    return False, ("uppdateringspaketet är orimligt stort "
                                   "- avbryter")
                target = (dest / info.filename).resolve()
                try:
                    target.relative_to(dest_res)
                    if target == dest_res:
                        return False, "zip-filen innehåller en ogiltig sökväg"
                except ValueError:
                    return False, ("zip-filen försöker skriva utanför "
                                   "appmappen - avbryter")
            zf.extractall(dest)
    except Exception as exc:
        return False, (f"kunde inte packa upp uppdateringen: "
                       f"{type(exc).__name__}: {exc}")
    return True, ""


def _restore_files(backup: Path, root: Path, installerade: List[str],
                   fanns_innan) -> List[str]:
    """Lägg tillbaka filerna från säkerhetskopian efter ett avbrott."""
    import shutil as _sh
    misslyckade = []
    for namn in installerade:
        mal = root / namn
        kalla = backup / namn
        try:
            if namn in fanns_innan and kalla.is_file():
                _sh.copy2(kalla, mal)
            elif namn not in fanns_innan and mal.is_file():
                mal.unlink()
        except OSError:
            misslyckade.append(namn)
    return misslyckade


def _install_from_folder(staged: Path, root: Path,
                         expected: Optional[str] = None) -> Tuple[bool, str]:
    """Installera UPDATE_FILES från en uppackad staging-mapp till root.

    Säkerhet: alla .py valideras med compile() FÖRE något rörs, staged
    version måste vara den väntade, nuvarande filer säkerhetskopieras
    till backups/update_<tid>/ och varje fil ersätts atomiskt. Går
    något fel mitt i återställs ALLA filer från kopian (rollback), och
    efteråt kontrolleras att den nya versionen verkligen ligger på plats.
    """
    import shutil as _sh
    staged = Path(staged); root = Path(root)
    src_root = staged
    if not (src_root / "pdfsorter.py").is_file():
        under = [d for d in staged.iterdir() if d.is_dir()
                 and (d / "pdfsorter.py").is_file()]
        if len(under) != 1:
            return False, "zip-filen har oväntat innehåll (ingen appmapp)"
        src_root = under[0]
    try:
        huvud = (src_root / "pdfsorter.py").read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"kunde inte läsa staged pdfsorter.py: {exc}"
    m = re.search(r'APP_VERSION\s*=\s*"([0-9][0-9A-Za-z.\-]*)"', huvud)
    staged_version = m.group(1) if m else None
    if expected and staged_version != expected:
        return False, (f"versionerna stämmer inte (väntade {expected}, "
                       f"fick {staged_version}) - avbryter")
    if staged_version and _version_tuple(staged_version) <= _version_tuple(APP_VERSION):
        return False, f"staged version {staged_version} är inte nyare än {APP_VERSION}"
    # Även mot versionen som faktiskt ligger i root just nu - så att ett
    # andra anrop i samma process (före omstart) inte installerar igen.
    try:
        aktuell = (root / "pdfsorter.py").read_text(encoding="utf-8")
        m2 = re.search(r'APP_VERSION\s*=\s*"([0-9][0-9A-Za-z.\-]*)"', aktuell)
        if (staged_version and m2
                and _version_tuple(staged_version) <= _version_tuple(m2.group(1))):
            return False, (f"version {staged_version} är redan installerad "
                           f"i appmappen (starta om appen i stället)")
    except OSError:
        pass
    for namn in UPDATE_FILES:
        kalla = src_root / namn
        if namn.endswith(".py") and kalla.is_file():
            try:
                compile(kalla.read_bytes(), namn, "exec")
            except SyntaxError as exc:
                return False, f"{namn} i uppdateringen kompilerar inte: {exc}"
    stamp = _dt.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "backups" / f"update_{stamp}"
    installerade: List[str] = []
    fanns_innan = set()
    try:
        backup.mkdir(parents=True, exist_ok=True)
        for namn in UPDATE_FILES:
            kalla = src_root / namn
            if not kalla.is_file():
                continue
            mal = root / namn
            if mal.is_file():
                _sh.copy2(mal, backup / namn)
                fanns_innan.add(namn)
            tmp = root / (namn + ".update-tmp")
            with open(kalla, "rb") as fi, open(tmp, "wb") as fo:
                _sh.copyfileobj(fi, fo)
            os.replace(tmp, mal)
            installerade.append(namn)
        # Kontrollera att den nya versionen verkligen ligger på plats.
        ny = (root / "pdfsorter.py").read_text(encoding="utf-8")
        m3 = re.search(r'APP_VERSION\s*=\s*"([0-9][0-9A-Za-z.\-]*)"', ny)
        if staged_version and (not m3 or m3.group(1) != staged_version):
            raise OSError(f"pdfsorter.py visar {m3.group(1) if m3 else '?'} "
                          f"efter uppdateringen")
        info = {"time": now_iso(), "from": APP_VERSION, "to": staged_version,
                "files": installerade, "backup": str(backup)}
        upd = root / "updates"
        upd.mkdir(parents=True, exist_ok=True)
        (upd / "last_update.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as exc:
        kvar = _restore_files(backup, root, installerade, fanns_innan)
        for tmp in root.glob("*.update-tmp"):
            try:
                tmp.unlink()
            except OSError:
                pass
        extra = (" Alla filer återställdes." if not kvar
                 else f" KUNDE INTE ÅTERSTÄLLA: {', '.join(kvar)}.")
        return False, (f"installationen avbröts ({type(exc).__name__}: {exc})."
                       f"{extra} Säkerhetskopia: {backup}")
    session_log("uppdatering",
                f"{APP_VERSION} -> {staged_version}: "
                f"{len(installerade)} filer, backup {backup}", "ok")
    return True, (f"Uppdaterad {APP_VERSION} -> {staged_version} "
                  f"({len(installerade)} filer). Säkerhetskopia: {backup}. "
                  f"Starta om appen för att köra den nya versionen.")


def perform_update(timeout: int = 180,
                   root: Optional[Path] = None) -> Tuple[bool, str]:
    """Hämta senaste versionen från GitHub Releases och installera den.

    Paketet verifieras mot release-postens SHA256SUMS.txt innan något
    packas upp. Allt mellanlager (zip, staging) bor i appmappens egna
    undermappar temp/ och updates/ - inget utanför appmappen.
    """
    import shutil as _sh
    from urllib.parse import urlparse
    root = Path(root) if root else _main_script.parent
    info = check_for_update(timeout=min(timeout, 30))
    if not info["ok"]:
        return False, f"Kunde inte söka uppdatering: {info.get('error', '?')}"
    if not info["available"]:
        return True, f"Du har redan den senaste versionen ({APP_VERSION})."
    url = info.get("zip_url") or UPDATE_ZIP_URL
    tmp = root / "temp"; tmp.mkdir(parents=True, exist_ok=True)
    staging = root / "updates" / "staging"
    zippath = tmp / "arkivpiloten-update.zip"
    try:
        # -- kontrollsumma FÖRE nedladdning: ett release-paket som inte
        #    kan verifieras ska aldrig hämtas eller installeras. -------
        forvantad = info.get("sha256") or ""
        if info.get("sha256_url"):
            try:
                sums = _http_get(info["sha256_url"], min(timeout, 30),
                                 limit=1_000_000).decode("utf-8", "ignore")
            except Exception as exc:
                return False, ("Kunde inte hämta kontrollsumman - "
                               f"uppdateringen avbröts ({type(exc).__name__}).")
            namn = [Path(urlparse(url).path).name, UPDATE_ASSET_NAME]
            forvantad = _sha_from_sums(sums, namn) or ""
            if not forvantad:
                return False, ("SHA256SUMS.txt saknar paketet - "
                               "uppdateringen avbröts.")
        if not forvantad and info.get("source") == "release":
            session_log("uppdatering",
                        "Release saknar kontrollsumma - avbröt", "warn")
            return False, ("Releasen saknar kontrollsumma (SHA256SUMS.txt "
                           "eller SHA-256 i release-texten), så paketet kan "
                           "inte verifieras. Uppdateringen avbröts - ladda "
                           "ner manuellt från releasesidan i stället.")
        session_log("uppdatering", f"Laddar ner {url}")
        _ladda_ner(url, zippath, timeout=timeout)
        if forvantad:
            faktisk = _sha256_file(zippath)
            if faktisk != forvantad.lower():
                return False, ("Kontrollsumman stämmer inte "
                               f"({faktisk[:12]}… != {forvantad[:12]}…) - "
                               "uppdateringen avbröts och inget ändrades.")
        if staging.exists():
            _sh.rmtree(staging, ignore_errors=True)
        ok, fel = _safe_extract(zippath, staging)
        if not ok:
            return False, fel
        ok, msg = _install_from_folder(staging, root, expected=info["remote"])
        return ok, msg
    except Exception as exc:
        session_error("uppdatering", exc)
        return False, f"Uppdateringen misslyckades: {type(exc).__name__}: {exc}"
    finally:
        try:
            zippath.unlink(missing_ok=True)
            if staging.exists():
                _sh.rmtree(staging, ignore_errors=True)
        except OSError:
            pass


# ==========================================================================
# 1.1.0-FUNKTIONER: PDF-taggning, årsarkiv-export (ej zippad), org.nr-uppslag
# ==========================================================================

def tag_pdf_metadata(path: Path, category: str, sender: str = "") -> bool:
    """Skriv kategori/avsändare som PDF-metadata (keywords/subject) så att
    arkivet blir sökbart även i Utforskaren/Acrobat. Tyst False vid fel -
    taggning får aldrig stoppa en sortering."""
    try:
        # Importera pymupdf FÖRST: import av det gamla namnet "fitz" skriver
        # en DeprecationWarning på stdout i PyMuPDF 1.28+, vilket gjorde
        # --json till ogiltig JSON (varningen hamnade före JSON-blocket).
        import pymupdf as fitz  # type: ignore
    except Exception:
        try:
            import fitz  # type: ignore
        except Exception:
            return False
    try:
        doc = fitz.open(str(path))
        try:
            meta = dict(doc.metadata or {})
            nyckel = ["ArkivPiloten", category]
            if sender and sender not in nyckel:
                nyckel.append(sender)
            meta["keywords"] = "; ".join(nyckel)
            meta["subject"] = category
            doc.set_metadata(meta)
            doc.saveIncr()
        finally:
            doc.close()
        return True
    except Exception:
        # saveIncr kan nekas (krypterad/udda fil): skriv om till tempfil.
        try:
            try:
                import pymupdf as fitz  # type: ignore
            except Exception:
                import fitz  # type: ignore
            doc = fitz.open(str(path))
            meta = dict(doc.metadata or {})
            meta["keywords"] = "; ".join(["ArkivPiloten", category] +
                                         ([sender] if sender else []))
            meta["subject"] = category
            doc.set_metadata(meta)
            tmp = path.with_suffix(".tagtmp.pdf")
            doc.save(str(tmp))
            doc.close()
            tmp.replace(path)
            return True
        except Exception:
            return False


def export_year_archive(output_root: Path, dest_dir: Path,
                        log: Callable[[str], None] = lambda m: None) -> Dict[str, Any]:
    """Exportera det sorterade arkivet till en ÖPPEN mappstruktur (ej zip):
    <dest>/ArkivPiloten-Export-<tid>/<år>/<relativ sökväg> + index.html
    (sökbar) + checksums.sha256. Kopierar - flyttar aldrig."""
    from datetime import datetime
    import hashlib
    import html as _html
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rot = Path(dest_dir) / f"ArkivPiloten-Export-{stamp}"
    rot.mkdir(parents=True, exist_ok=True)
    poster: List[Dict[str, Any]] = []
    sha_lines: List[str] = []
    fel = 0
    pdfs = sorted(p for p in Path(output_root).rglob("*")
                  if p.is_file() and p.suffix.lower() == ".pdf")
    for src in pdfs:
        rel = src.relative_to(Path(output_root))
        delar = rel.parts
        år = (delar[1] if len(delar) > 1 and delar[0] and
              len(delar[1]) == 4 and delar[1].isdigit() else
              (delar[0] if delar and len(delar[0]) == 4 and delar[0].isdigit()
               else str(datetime.fromtimestamp(src.stat().st_mtime).year)))
        kategori = delar[0] if delar else ""
        mål_rel = Path(år) / rel
        mål = rot / mål_rel
        try:
            mål.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(mål))
            h = hashlib.sha256()
            with open(mål, "rb") as fh:
                for block in iter(lambda: fh.read(1024 * 256), b""):
                    h.update(block)
            digest = h.hexdigest()
            sha_lines.append(f"{digest}  {mål_rel.as_posix()}")
            poster.append({"år": år, "kategori": kategori,
                           "fil": src.name, "sökväg": mål_rel.as_posix(),
                           "storlek": mål.stat().st_size, "sha": digest[:12]})
            log(f"Exporterade {mål_rel.as_posix()}")
        except OSError as exc:
            fel += 1
            log(f"Kunde inte exportera {src}: {exc}")
    (rot / "checksums.sha256").write_text("\n".join(sha_lines) + "\n",
                                          encoding="utf-8")
    rader = "\n".join(
        f'<tr><td>{_html.escape(p["år"])}</td><td>{_html.escape(p["kategori"])}</td>'
        f'<td><a href="{_html.escape(p["sökväg"])}">{_html.escape(p["fil"])}</a></td>'
        f'<td>{p["storlek"]//1024} KB</td><td><code>{p["sha"]}…</code></td></tr>'
        for p in poster)
    index = f"""<!DOCTYPE html>
<html lang="sv"><head><meta charset="utf-8">
<title>ArkivPiloten - arkivexport {stamp}</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;background:#0f172a;color:#e2e8f0}}
input{{padding:.5rem 1rem;width:24rem;border-radius:.5rem;border:1px solid #334155;background:#1e293b;color:#fff}}
table{{border-collapse:collapse;margin-top:1rem}}td,th{{padding:.35rem .8rem;border-bottom:1px solid #1e293b;text-align:left}}
a{{color:#7dd3fc}}</style></head><body>
<h1>📁 ArkivPiloten - arkivexport</h1>
<p>{len(poster)} filer · {stamp} · kontrollsummor i checksums.sha256</p>
<input id="q" type="search" placeholder="Sök fil, kategori, år…" oninput="f()">
<table id="t"><tr><th>År</th><th>Kategori</th><th>Fil</th><th>Storlek</th><th>SHA-256</th></tr>
{rader}</table>
<script>function f(){{const q=document.getElementById('q').value.toLowerCase();
document.querySelectorAll('#t tr').forEach((r,i)=>{{if(i)r.style.display=r.textContent.toLowerCase().includes(q)?'':'none'}})}}</script>
</body></html>"""
    (rot / "index.html").write_text(index, encoding="utf-8")
    return {"mapp": str(rot), "filer": len(poster), "fel": fel}


def lookup_company_name_online(orgnr: str, timeout: float = 6.0) -> Optional[str]:
    """Slå upp firmanamn för ett org.nr på webben (anropas bara när
    användaren slagit på det). Best-effort: parsar JSON-LD/<title> ur
    offentliga söksidor. Returnerar None vid varje problem."""
    ren = "".join(ch for ch in str(orgnr) if ch.isdigit())
    if len(ren) < 10:
        return None
    import urllib.request
    import urllib.error
    urls = [f"https://www.allabolag.se/{ren}",
            f"https://www.merinfo.se/foretag/{ren}"]
    for url in urls:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 ArkivPiloten"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                sida = resp.read(300_000).decode("utf-8", "replace")
        except Exception:
            continue
        m = re.search(r'"name"\s*:\s*"([^"]{2,80})"', sida)
        if m and ren not in m.group(1):
            return m.group(1).strip()
        m = re.search(r"<title>([^<]{2,90})</title>", sida, re.I)
        if m:
            namn = re.split(r"\s*[-|–]\s*", m.group(1))[0].strip()
            if namn and ren not in namn and "404" not in namn:
                return namn
    return None

def update_python_packages(root: Optional[Path] = None,
                           timeout: int = 1800) -> Tuple[bool, str]:
    """Installera/uppdatera ALLA Python-tillägg från appens
    requirements.txt (pinnade versioner) med den Python som kör appen.
    Verifierar importerna efteråt och rapporterar per paket."""
    root = Path(root) if root else _main_script.parent
    req = root / "requirements.txt"
    if req.is_file():
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade",
               "--disable-pip-version-check", "-r", str(req)]
        kalla = "requirements.txt"
    else:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade",
               "--disable-pip-version-check", *_PIP_PAKET_NAMN]
        kalla = "standardpaketen"
    session_log("tillägg", f"Paketuppdatering startad från {kalla}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, **_win_dold())
    except Exception as exc:
        return False, f"pip kunde inte köras: {exc}"
    if r.returncode != 0:
        fel = (r.stderr or r.stdout or "").strip().splitlines()
        return False, ("pip misslyckades: "
                       + (fel[-1] if fel else f"slutkod {r.returncode}"))
    import importlib.util as _iu
    saknas = [n for n in _PIP_PAKET_NAMN
              if _iu.find_spec(_PIP_IMPORTNAMN[n]) is None]
    if saknas:
        return False, ("Paket installerades men går inte att importera: "
                       + ", ".join(saknas))
    session_log("tillägg", "Alla Python-paket uppdaterade och importerbara", "ok")
    return True, "Alla Python-paket är uppdaterade: " + ", ".join(_PIP_PAKET_NAMN)



# ==========================================================================
# FRISTÅENDE KÖRNING
# ==========================================================================

def _self_test() -> int:
    """Kontrollera att modulen fungerar på den här datorn."""
    print(f"{APP_NAME} {APP_VERSION} - systemmodul")
    print(f"  Konfiguration:  {config_dir()}")
    print(f"  Huvudprogram:   {_main_script}")
    print(f"  Pillow:         {'ja' if make_icon_image(16) else 'nej'}")
    ikon = icon_file_path()
    print(f"  Ikonfil:        {ikon if ikon.exists() else 'ej skapad ännu'}")
    print(f"  Systemfält:     {'ja' if tray_available() else 'nej (pip install pystray)'}")
    print(f"  Autostart:      {'stöds' if autostart_supported() else 'stöds ej'}"
          f" - just nu {'på' if autostart_enabled() else 'av'}")
    print(f"  Loggmapp:       {config_dir() / 'logs'}")
    print(f"  Hjälptext:      {len(HELP_CONTENT)} block, "
          f"{len(help_as_text())} tecken")
    print(f"  Uppdatering:    GitHub Releases ({UPDATE_REPO}) - "
          f"paketverifiering {'ja' if callable(_safe_extract) else 'nej'}, "
          f"rollback {'ja' if callable(_restore_files) else 'nej'}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="pdfsorter_system",
        description="Systemintegration för ArkivPiloten - ikon, autostart, "
                    "systemfält och hjälptext.")
    p.add_argument("--icon", metavar="FIL",
                   help="Spara appikonen som .png eller .ico")
    p.add_argument("--size", type=int, default=256, help="Ikonstorlek i pixlar")
    p.add_argument("--help-text", action="store_true",
                   help="Skriv ut hela användarhjälpen som text")
    p.add_argument("--autostart", choices=["on", "off", "status"],
                   help="Slå på eller av autostart med operativsystemet")
    p.add_argument("--shortcut", action="store_true",
                   help="Skapa en genväg på skrivbordet")
    p.add_argument("--check", action="store_true",
                   help="Visa vad som fungerar på den här datorn")
    p.add_argument("--diag", action="store_true",
                   help="Felsökningsöversikt: autostart-status, journal, ikoner")
    args = p.parse_args(argv)

    if args.diag:
        print(f"{APP_NAME} {APP_VERSION} - diagnostik")
        print(f"  Python:          {sys.version.split()[0]}")
        print(f"  Modulversioner:  {_mod_versions_line()}")
        print(f"  Konfiguration:   {config_dir()}")
        print(f"  Huvudprogram:    {_main_script}")
        print(f"  Pillow/ikon:     {'ja' if make_icon_image(16) else 'nej'}")
        ikon = icon_file_path()
        print(f"  Ikonfil:         {ikon if ikon.exists() else 'ej skapad'}")
        print(f"  Systemfält:      {'ja' if tray_available() else 'nej'}")
        print(f"  Autostart:       {'på' if autostart_enabled() else 'av'}"
              f" / klass: {classify_autostart()}")
        konflikter = get_autostart_conflicts()
        if konflikter:
            for namn, varde in konflikter:
                print(f"  Autostartkonflikt: {namn} -> {varde[:80]}")
        j = config_dir() / "json" / "history.journal"
        print(f"  Historikjournal: {j.stat().st_size if j.exists() else 0} B")
        logg = config_dir() / "logs"
        print(f"  Loggmapp:        {logg if logg.exists() else 'tom'}")
        senaste = latest_session_log()
        print(f"  Sessionslogg:    {senaste or 'ingen än'}")
        krasch = session_dir() / "krasch.log"
        if krasch.exists():
            print(f"  Kraschlogg:      {krasch} ({krasch.stat().st_size} B)")
        # Senaste sorteringen: snabb hälsokoll av läsning/matchning utan
        # att behöva öppna appen.
        try:
            hist = json.loads((config_dir() / "json" / "history.json").read_text("utf-8"))
            evs = hist.get("events", [])
            if evs:
                sista = evs[-1]
                print(f"  Senaste flytt:   {sista.get('time', '?')} -> "
                      f"{sista.get('category', '?')} "
                      f"({sista.get('decided_by', '?')})")
            else:
                print("  Senaste flytt:   ingen")
        except Exception:
            print("  Senaste flytt:   historiken saknas/oläsbar")
        return 0

    if args.icon:
        out = write_icon_file(Path(args.icon), size=args.size)
        print(f"Ikon sparad: {out}" if out else "Kunde inte spara (kräver Pillow)")
        return 0 if out else 1
    if args.help_text:
        print(help_as_text())
        return 0
    if args.autostart:
        if args.autostart == "status":
            print("på" if autostart_enabled() else "av")
            return 0
        ok, msg = set_autostart(args.autostart == "on")
        print(("Autostart på: " if args.autostart == "on" else "Autostart av: ") + msg)
        return 0 if ok else 1
    if args.shortcut:
        ok, msg = create_desktop_shortcut()
        print(("Genväg skapad: " if ok else "Misslyckades: ") + msg)
        return 0 if ok else 1

    return _self_test()


if __name__ == "__main__":
    sys.exit(main())
