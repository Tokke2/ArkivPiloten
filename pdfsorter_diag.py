# -*- coding: utf-8 -*-
"""Feldiagnostik: allt som går fel, fångat och samlat - på noll sekunder.

Varför modulen finns
--------------------
Två saker gjorde tidigare att fel var osynliga:

1. Undantag i en Tk-callback skrevs bara till ``stderr``. Startas appen med
   ``pythonw`` (dubbelklick) finns ingen konsol, så spårningen försvann -
   exakt det som hände med ``application has been destroyed``.
2. Felen låg utspridda i sessionsloggar, ``errors.log`` och ``krasch.log``,
   och diagnostikpaketet läste hela filerna. Med stora loggar tog det tid
   och gav ändå ingen samlad bild.

Här samlas i stället allt på ett ställe:

* ``install_hooks()`` fångar ``sys.excepthook`` och ``threading.excepthook``.
* ``install_tk_hooks(root)`` fångar ``report_callback_exception`` - alla
  fel i knappar, ``after``-jobb och bindningar.
* Varje fel hamnar i en ringbuffert i minnet (överlever att loggfilen inte
  kan skrivas) med tid, område, spårning och ett fingeravtryck.
* ``build_ai_report()`` läser bara **svansen** av varje loggfil (bounded),
  slår ihop dubbletter till en rad med antal och tidsintervall, och skriver
  ett kompakt block som går att klistra in i en AI-chatt eller felanmälan.

Rapporten innehåller alltid: miljö, versionsläge, unika fel med spårning,
varningar, senaste händelserna före felen och hur mycket som lästes (så att
"inga fel" går att lita på). Användarnamn och hemkatalog avidentifieras som
standard - rapporten ska kunna klistras in var som helst.
"""
from __future__ import annotations

import hashlib
import os
import platform
import re
import sys
import threading
import time
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

VERSION = "1.4.13"

#: Max antal fel som hålls i minnet. Nog för en hel dag, litet nog att vara billigt.
RING_SIZE = 250

#: Standard: filer under den här storleken läses i sin helhet (alla fel hittas),
#: större läses bara i svansen - och rapporten säger det högt.
FULL_READ_MAX = 8_000_000

#: Svansen som läses ur en stor fil (när hela inte läses).
DEFAULT_TAIL_BYTES = 200_000

#: Hårt tak även med --djup: en halv gigabyte logg får inte äta minnet.
HARD_READ_MAX = 64_000_000

#: Hur många loggfiler som genomsöks (nyaste först).
DEFAULT_MAX_FILES = 8

#: Radlängd som rapporten kapar till, så att en trasig rad inte spränger den.
MAX_LINE = 400


class _State:
    """Allt muterbart på ett ställe - lätt att nollställa i tester."""

    lock = threading.RLock()
    ring: deque = deque(maxlen=RING_SIZE)
    seen: Dict[str, Dict[str, Any]] = {}
    app_name = "ArkivPiloten"
    version = ""
    logs_dir: Optional[Path] = None
    #: Extra rader (uppdateringsstatus, beroenden ...) som appen bidrar med.
    extra: Optional[Callable[[], Sequence[str]]] = None
    #: Sessionsloggens skrivare, om appen vill att fel även hamnar där.
    logger: Optional[Callable[[str, str, str], None]] = None
    tk_installed = False
    last_dump = 0.0
    dump_path: Optional[Path] = None


_NIVÅER = {"FEL", "VARN", "INFO", "OK", "DEBUG"}
_RE_SESSION = re.compile(
    r"^(?P<tid>\d{2}:\d{2}:\d{2}\.\d{3})\s{1,3}(?P<nivå>FEL|VARN|INFO|OK|DEBUG)"
    r"\s+(?P<kat>\S+)\s?(?P<msg>.*)$")
_RE_FORTS = re.compile(r"^ {20,}(?P<rad>.*)$")
_RE_BLOCK = re.compile(r"^=+\s*(?P<ts>\S[^=]*?)\s*=+\s*$")


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
def configure(app_name: Optional[str] = None, version: Optional[str] = None,
              logs_dir: Optional[Path] = None,
              extra: Optional[Callable[[], Sequence[str]]] = None,
              logger: Optional[Callable[[str, str, str], None]] = None) -> None:
    """Koppla modulen till appen. Anropas en gång vid start."""
    with _State.lock:
        if app_name:
            _State.app_name = app_name
        if version:
            _State.version = version
        if logs_dir is not None:
            _State.logs_dir = Path(logs_dir)
        if extra is not None:
            _State.extra = extra
        if logger is not None:
            _State.logger = logger


def reset() -> None:
    """Nollställ minnet (tester, och när appen startar om i samma process)."""
    with _State.lock:
        _State.ring.clear()
        _State.seen.clear()
        _State.last_dump = 0.0


# ---------------------------------------------------------------------------
# Fingeravtryck och notering
# ---------------------------------------------------------------------------
def _kort(text: str, n: int = MAX_LINE) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _normalisera(text: str) -> str:
    """Gör om ett felmeddelande till en signatur som tål variationer.

    Siffror, hex, tidsstämplar och absoluta sökvägar varierar mellan
    gångerna utan att felet är ett annat. Kvar blir ordet - det som gör
    att 9 likadana TclError blir EN rad med antal 9.
    """
    s = str(text or "")
    s = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*", "<tid>", s)
    s = re.sub(r"\b\d{2}:\d{2}:\d{2}\.\d{3}\b", "<tid>", s)
    s = re.sub(r"0x[0-9a-fA-F]+", "<hex>", s)
    s = re.sub(r"\b[0-9a-fA-F]{8,}\b", "<hex>", s)
    s = re.sub(r"\b\d+\b", "#", s)
    s = re.sub(r"[A-Za-z]:\\[^\s:'\"]+", "<sökväg>", s)
    s = re.sub(r"(?<![\w])/(?:[^\s:'\"]+/)+[^\s:'\"]*", "<sökväg>", s)
    # Modulprefix: "pdfminer.pdfparser.PDFSyntaxError" och
    # "_tkinter.TclError" är samma fel som "PDFSyntaxError"/"TclError" -
    # annars blir samma händelse två poster bara för att den ena kom via
    # errors.log och den andra via sessionsloggen.
    s = re.sub(r"\b[a-z_][\w]*(?:\.[a-z_][\w]*)*\.(?=[A-Z])", "", s)
    return " ".join(s.split()).lower()


def _ram(tb_text: str) -> str:
    """Appens anropsställe i en spårning: fil + funktion, utan radnummer.

    Radnummer ändras vid varje release; funktionsnamnet gör det inte. Den
    FÖRSTA ramen i appens egen kod används (där felet utlöstes), inte den
    sista - sista ramen ligger ofta i tkinter och varierar med hur mycket
    av spårningen som hann skrivas.
    """
    ramar = re.findall(r'File "([^"]+)", line \d+, in (\w+)', tb_text or "")
    if not ramar:
        return ""
    for fil, funk in ramar:
        if _filnamn(fil).lower().startswith("pdfsorter"):
            return f"{_filnamn(fil)}:{funk}"
    fil, funk = ramar[-1]
    return f"{_filnamn(fil)}:{funk}"


def _filnamn(fil: str) -> str:
    """Filnamnet ur en sökväg - även Windows-sökvägar på Linux/macOS.

    ``Path("D:\\...\\pdfsorter.py").name`` blir hela strängen på POSIX, eftersom
    backslash inte är ett filavskiljningstecken där. Loggarna kan komma från
    en annan dator, så avskiljningstecknet måste normaliseras först.
    """
    return Path(str(fil).replace("\\", "/")).name


def fingerprint(message: str, tb_text: str = "") -> str:
    """Kort, stabil nyckel för ett fel - samma fel ger samma nyckel.

    Området (granska, motor, tk-callback ...) ingår INTE: samma fel ska slås
    ihop även när det kommit in via olika vägar - en gång ur minnet, en
    gång ur sessionsloggen och en gång ur errors.log.
    """
    grund = "|".join((_normalisera(message), _ram(tb_text)))
    return hashlib.sha1(grund.encode("utf-8", "replace")).hexdigest()[:8]


def note(område: str, message: str, level: str = "err",
         tb_text: str = "", när: Optional[datetime] = None,
         logg: bool = True) -> Dict[str, Any]:
    """Notera ett fel/en varning. Kastar aldrig - diagnostik får inte sänka appen.

    ``logg=False`` när anroparen redan skrivit till sessionsloggen (appens
    egna excepthook gör det) - då räcker det att felet hamnar i minnet.
    """
    try:
        ts = när or datetime.now()
        nivå = "VARN" if str(level).lower() in ("warn", "varning") else "FEL"
        meddelande = _kort(message)
        tb = str(tb_text or "").strip()
        fp = fingerprint(meddelande, tb)
        post = {
            "fp": fp,
            "nivå": nivå,
            "område": str(område or "app")[:12],
            "meddelande": meddelande,
            "spårning": tb,
            "ram": _ram(tb),
            "tid": ts,
        }
        with _State.lock:
            _State.ring.append(post)
            sedd = _State.seen.get(fp)
            if sedd is None:
                sedd = dict(post, antal=0, först=ts, senast=ts, källor=["minne"])
                _State.seen[fp] = sedd
            sedd["antal"] += 1
            sedd["senast"] = ts
            if tb:
                sedd["spårning"] = tb
        if logg:
            _skriv_till_logg(post)
        return post
    except Exception:
        return {}


def note_exception(område: str, exc: BaseException,
                   tb_text: str = "", level: str = "err",
                   logg: bool = True) -> Dict[str, Any]:
    """Notera ett undantag med full spårning."""
    try:
        if not tb_text:
            tb_text = "".join(traceback.format_exception(
                type(exc), exc, getattr(exc, "__traceback__", None)))
        text = f"{type(exc).__name__}: {exc}"
    except Exception:
        text, tb_text = "okänt fel", ""
    return note(område, text, level=level, tb_text=tb_text, logg=logg)


def _skriv_till_logg(post: Dict[str, Any]) -> None:
    """Skriv felet till sessionsloggen också, om appen kopplat en skrivare."""
    logger = _State.logger
    if logger is None:
        return
    try:
        med = post["meddelande"]
        if post["spårning"]:
            med = med + "\n" + post["spårning"].rstrip()
        logger(post["område"], med,
               "warn" if post["nivå"] == "VARN" else "err")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Krokar: fångar allt som annars bara hamnar i en konsol som inte finns
# ---------------------------------------------------------------------------
def install_tk_hooks(root: Any) -> None:
    """Fånga undantag i Tk-callbacks (knappar, after, bindningar).

    Utan detta försvinner de spårlöst när appen startas med ``pythonw``:
    Tk fångar felet, skriver till ``stderr`` och fortsätter - och stderr
    finns inte. Här loggas de i stället, med samma väg som allt annat.
    """
    try:
        gammal = getattr(root, "report_callback_exception", None)

        def _rapportera(typ, värde, tb):  # noqa: ANN001 - Tk-signatur
            try:
                text = "".join(traceback.format_exception(typ, värde, tb))
                note("tk-callback", f"{typ.__name__}: {värde}", tb_text=text)
                _dump_if_due()
            except Exception:
                pass
            # Behåll Tk:s eget beteende (skriv till stderr när den finns),
            # men låt den aldrig krascha appen.
            if callable(gammal):
                try:
                    gammal(typ, värde, tb)
                except Exception:
                    pass

        root.report_callback_exception = _rapportera
        with _State.lock:
            _State.tk_installed = True
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Läsa loggar - bara svansen, alltid bounded
# ---------------------------------------------------------------------------
def tail_text(path: Path, max_bytes: int = DEFAULT_TAIL_BYTES) -> str:
    """Läs slutet av en fil utan att läsa hela.

    En sessionslogg kan vara tiotalet megabyte efter en lång dag. Att läsa
    hela för att få de sista 200 raderna är slöseri - och gör att
    "0 sekunder" blir fel. Här hoppas direkt till rätt offset.
    """
    p = Path(path)
    try:
        storlek = p.stat().st_size
        with open(p, "rb") as fh:
            if storlek > max_bytes:
                fh.seek(storlek - max_bytes)
                data = fh.read()
                # Första raden är nästan alltid avklippt - kasta den.
                klippt = data.find(b"\n")
                if klippt >= 0:
                    data = data[klippt + 1:]
            else:
                data = fh.read()
        return data.decode("utf-8", "replace")
    except OSError:
        return ""


def parse_session_log(text: str) -> List[Dict[str, Any]]:
    """Plocka ut rader med nivå FEL/VARN ur en sessionslogg.

    Format: ``HH:MM:SS.mmm  NIVÅ  kategori  meddelande`` med
    fortsättningsrader indenterade med 22 tecken (spårningar).
    """
    ut: List[Dict[str, Any]] = []
    nuvarande: Optional[Dict[str, Any]] = None
    for rad in text.splitlines():
        m = _RE_SESSION.match(rad)
        if m:
            if nuvarande:
                ut.append(nuvarande)
                nuvarande = None
            if m.group("nivå") in ("FEL", "VARN"):
                nuvarande = {
                    "tid": m.group("tid"),
                    "nivå": m.group("nivå"),
                    "område": m.group("kat"),
                    "meddelande": m.group("msg").strip(),
                    "spårning": "",
                }
            continue
        if nuvarande is not None:
            f = _RE_FORTS.match(rad)
            if f:
                nuvarande["spårning"] += f.group("rad") + "\n"
            else:
                ut.append(nuvarande)
                nuvarande = None
    if nuvarande:
        ut.append(nuvarande)
    for post in ut:
        post["spårning"] = post["spårning"].strip()
        post["ram"] = _ram(post["spårning"])
    return ut


def parse_error_blocks(text: str, område: str = "errors.log") -> List[Dict[str, Any]]:
    """Dela upp ``errors.log``/``krasch.log`` i block (``===== tid =====``)."""
    ut: List[Dict[str, Any]] = []
    ts, buf = "", []
    for rad in text.splitlines():
        m = _RE_BLOCK.match(rad)
        if m and len(rad) > 6:
            if buf:
                ut.append(_block(ts, buf, område))
            ts, buf = m.group("ts"), []
            continue
        buf.append(rad)
    if buf:
        ut.append(_block(ts, buf, område))
    return [p for p in ut if p]


def _block(ts: str, rader: List[str], område: str) -> Optional[Dict[str, Any]]:
    text = "\n".join(rader).strip()
    if not text:
        return None
    # Sista raden i spårningen är feltypen - den är rubriken.
    rader_utan_tomma = [r for r in text.splitlines() if r.strip()]
    if not rader_utan_tomma:
        return None
    sista = rader_utan_tomma[-1].strip()
    return {
        "tid": ts,
        "nivå": "FEL",
        "område": område,
        "meddelande": _kort(sista),
        "spårning": text,
        "ram": _ram(text),
    }


def _nya_filer(logs_dir: Path, max_files: int) -> List[Path]:
    """De nyaste loggfilerna: sessionsloggar, errors.log, krasch.log."""
    kandidater: List[Path] = []
    try:
        for p in Path(logs_dir).rglob("*"):
            if not p.is_file():
                continue
            namn = p.name.lower()
            if namn.endswith(".log") or namn.endswith(".log.gz"):
                kandidater.append(p)
    except OSError:
        return []
    def nyckel(p: Path):
        try:
            return p.stat().st_mtime_ns
        except OSError:
            return 0
    kandidater.sort(key=nyckel, reverse=True)
    return kandidater[:max_files]


def read_log(path: Path, tail_bytes: int = DEFAULT_TAIL_BYTES,
             djup: bool = False) -> Dict[str, Any]:
    """Läs en loggfil: hel om den är liten, annars bara svansen.

    Returnerar ``{"text", "läst", "storlek", "trunkerad"}``. ``trunkerad``
    betyder att filen är större än vad som lästes - då måste rapporten säga
    det, så att "inga fel" inte feltolkas som "inga fel alls".
    """
    p = Path(path)
    try:
        storlek = p.stat().st_size
    except OSError:
        return {"text": "", "läst": 0, "storlek": 0, "trunkerad": False}
    gräns = HARD_READ_MAX if djup else FULL_READ_MAX
    if storlek <= gräns:
        try:
            with open(p, "rb") as fh:
                data = fh.read(gräns)
        except OSError:
            return {"text": "", "läst": 0, "storlek": storlek, "trunkerad": False}
        return {"text": data.decode("utf-8", "replace"),
                "läst": len(data), "storlek": storlek,
                "trunkerad": len(data) < storlek}
    # Läs svansen direkt: till skillnad från tail_text behålls en enda
    # lång rad (en loggfil kan i teorin vara en enda rad) - annars skulle
    # filen se tom ut och "inga fel" bli en lögn.
    gräns_bytes = max(int(tail_bytes), 1)
    try:
        with open(p, "rb") as fh:
            fh.seek(max(0, storlek - gräns_bytes))
            data = fh.read()
    except OSError:
        return {"text": "", "läst": 0, "storlek": storlek, "trunkerad": True}
    if b"\n" in data[:-1]:
        data = data.split(b"\n", 1)[1]      # kasta avklippt första rad
    return {"text": data.decode("utf-8", "replace"), "läst": len(data),
            "storlek": storlek, "trunkerad": True}


def collect(logs_dir: Optional[Path] = None, max_files: int = DEFAULT_MAX_FILES,
            max_bytes: int = DEFAULT_TAIL_BYTES,
            djup: bool = False) -> Dict[str, Any]:
    """Samla in minnets fel + loggfilernas, slå ihop dubbletter.

    ``max_bytes`` är svansen som läses ur filer som är för stora för att
    läsas helt. ``djup`` läser hela filer upp till ``HARD_READ_MAX``.

    Returnerar ``{"fel", "varningar", "lästa", "ofullständiga", "byte",
    "filer", "sekunder"}``.
    """
    start = time.perf_counter()
    lästa: List[Dict[str, Any]] = []
    ofullständiga: List[Dict[str, Any]] = []
    läst_byte = 0
    logs_dir = Path(logs_dir) if logs_dir else _State.logs_dir

    with _State.lock:
        samlade: Dict[str, Dict[str, Any]] = {
            fp: dict(post) for fp, post in _State.seen.items()}

    if logs_dir and Path(logs_dir).is_dir():
        for p in _nya_filer(Path(logs_dir), max_files):
            if p.name.endswith(".gz"):
                # Gzippade arkiv är gamla - de behövs inte för "vad hände nu".
                continue
            läst = read_log(p, tail_bytes=max_bytes, djup=djup)
            text = läst["text"]
            if not text:
                continue
            lästa.append({"fil": p.name, "byte": läst["läst"],
                          "storlek": läst["storlek"]})
            läst_byte += läst["läst"]
            if läst["trunkerad"]:
                ofullständiga.append({"fil": p.name,
                                      "storlek": läst["storlek"],
                                      "läst": läst["läst"]})
            if p.name.lower().startswith(("errors", "krasch")):
                poster = parse_error_blocks(text, p.name)
            else:
                poster = parse_session_log(text)
            for post in poster:
                fp = fingerprint(post["meddelande"],
                                 post.get("spårning", ""))
                post["fp"] = fp
                sedd = samlade.get(fp)
                if sedd is None:
                    samlade[fp] = {
                        "fp": fp, "nivå": post["nivå"],
                        "område": post["område"],
                        "meddelande": post["meddelande"],
                        "spårning": post.get("spårning", ""),
                        "ram": post.get("ram", ""),
                        "antal": 1, "först": post["tid"], "senast": post["tid"],
                        "källor": [p.name],
                    }
                else:
                    sedd["antal"] += 1
                    sedd["senast"] = post["tid"]
                    if p.name not in sedd["källor"]:
                        sedd["källor"].append(p.name)
                    if len(post.get("spårning", "")) > len(sedd.get("spårning", "")):
                        sedd["spårning"] = post["spårning"]

    def sortera(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(items, key=lambda p: (-int(p.get("antal", 1)),
                                            str(p.get("senast", ""))))

    fel = sortera(p for p in samlade.values() if p.get("nivå") == "FEL")
    varningar = sortera(p for p in samlade.values() if p.get("nivå") == "VARN")
    return {
        "fel": fel,
        "varningar": varningar,
        "lästa": lästa,
        "ofullständiga": ofullständiga,
        "byte": läst_byte,
        "filer": len(lästa),
        "sekunder": time.perf_counter() - start,
    }


# ---------------------------------------------------------------------------
# Avidentifiering
# ---------------------------------------------------------------------------
def avidentifiera(text: str, logs_dir: Optional[Path] = None) -> str:
    """Ta bort användarnamn och hemkatalog ur texten.

    Rapporten ska kunna klistras in i en chatt utan att lämna ut mer än
    nödvändigt. Sökvägsstrukturen behålls - den behövs för felsökning.
    """
    ut = str(text or "")
    hem = str(Path.home())
    ut = ut.replace(hem, "~")
    for nyckel in ("USERPROFILE", "HOME"):
        v = os.environ.get(nyckel)
        if v:
            ut = ut.replace(v, "~")
    användare = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if användare and len(användare) > 2:
        ut = ut.replace(f"\\Users\\{användare}", "\\Users\\<användare>")
        ut = ut.replace(f"/Users/{användare}", "/Users/<användare>")
        ut = ut.replace(f"/home/{användare}", "/home/<användare>")
    if logs_dir:
        ut = ut.replace(str(logs_dir), "~" + os.sep + "logs")
    return ut


# ---------------------------------------------------------------------------
# Rapporten
# ---------------------------------------------------------------------------
def _rad(text: str = "") -> str:
    return str(text).replace("\r", "")


def build_ai_report(logs_dir: Optional[Path] = None, *,
                    rubrik: Optional[str] = None,
                    miljö: Optional[Sequence[str]] = None,
                    extra: Optional[Sequence[str]] = None,
                    max_per_nivå: int = 12,
                    spårningsrader: int = 8,
                    kontext: int = 16,
                    max_files: int = DEFAULT_MAX_FILES,
                    max_bytes: int = DEFAULT_TAIL_BYTES,
                    djup: bool = False,
                    avidentifiera_text: bool = True,
                    nu: Optional[datetime] = None) -> str:
    """Bygg ett kompakt block som visar ALLA fel - klart att klistras in.

    Läser bara svansen av varje loggfil, så tiden beror på hur mycket som
    ska visas - inte på hur stora loggarna är.
    """
    start = time.perf_counter()
    nu = nu or datetime.now()
    logs_dir = Path(logs_dir) if logs_dir else _State.logs_dir
    data = collect(logs_dir, max_files=max_files, max_bytes=max_bytes,
                   djup=djup)

    rader: List[str] = []
    rubrik = rubrik or "ARKIVPILOTEN - AI-RAPPORT (alla fel)"
    rader.append("=" * 74)
    rader.append(f"{rubrik}  ·  {_State.version or '?'}  ·  {nu:%Y-%m-%d %H:%M:%S}")
    rader.append("=" * 74)

    miljö = list(miljö or [])
    if not miljö:
        miljö = [
            f"Python {platform.python_version()} · {platform.system()} "
            f"{platform.release()} · {platform.machine()}",
        ]
    rader.extend(_rad(r) for r in miljö)
    moduler = _versionsrad()
    if moduler:
        rader.append(moduler)

    fel, varningar = data["fel"], data["varningar"]
    unika = len(fel) + len(varningar)
    rader.append("")
    def _antal(n: int, ett: str, flera: str) -> str:
        return f"{n} {ett if n == 1 else flera}"

    rader.append(
        f"FEL: {_antal(len(fel), 'unik', 'unika')}, "
        f"{_antal(sum(int(p.get('antal', 1)) for p in fel), 'förekomst', 'förekomster')}"
        f"   |   VARNINGAR: {_antal(len(varningar), 'unik', 'unika')}, "
        f"{_antal(sum(int(p.get('antal', 1)) for p in varningar), 'förekomst', 'förekomster')}")
    rader.append(f"Läste {data['filer']} loggfil(er), {data['byte'] / 1024:.0f} kB, "
                 f"på {data['sekunder']:.3f} s"
                 + (f"  ·  {logs_dir}" if logs_dir else ""))

    # Ärligheten först: har någon fil bara lästs delvis måste det stå -
    # annars kan "inga fel" läsas som "inga fel alls".
    if data["ofullständiga"]:
        rader.append("")
        rader.append("OBS: dessa loggfiler lästes bara delvis (stora):")
        for f in data["ofullständiga"]:
            rader.append(f"  {f['fil']}: {f['storlek'] / 1_048_576:.1f} MB, "
                         f"läste sista {f['läst'] / 1024:.0f} kB")
        rader.append("  Kör med --djup för att läsa hela filerna.")

    if not unika:
        rader.append("")
        rader.append("INGA FEL ELLER VARNINGAR HITTADES i det som lästes.")
        if not data["ofullständiga"]:
            rader.append("(Alla loggfiler lästes i sin helhet.)")

    def _blockera(poster: List[Dict[str, Any]], titel: str) -> None:
        if not poster:
            return
        rader.append("")
        rader.append(f"--- {titel} " + "-" * max(0, 66 - len(titel)))
        for i, p in enumerate(poster[:max_per_nivå], 1):
            antal = int(p.get("antal", 1))
            fp = p.get("fp") or "?"
            område = str(p.get("område", "?"))[:12]
            rader.append("")
            rader.append(f"[{i}] {fp}  ×{antal}  {område}")
            rader.append(f"    {_rad(p.get('meddelande', ''))[:MAX_LINE]}")
            tid = _tidsintervall(p)
            if tid:
                rader.append(f"    tid: {tid}")
            if p.get("ram"):
                rader.append(f"    plats: {p['ram']}")
            spår = str(p.get("spårning", "")).strip().splitlines()
            if spår:
                # Sista raderna är de intressanta; rubriken visas redan.
                visa = spår[-spårningsrader:]
                rader.append("    spårning:")
                rader.extend(f"      {_rad(r)[:MAX_LINE]}" for r in visa)

    _blockera(fel, "FEL")
    _blockera(varningar, "VARNINGAR")

    if len(fel) > max_per_nivå or len(varningar) > max_per_nivå:
        rader.append("")
        rader.append(f"({len(fel) + len(varningar) - max_per_nivå * 2} fler "
                     "unika poster finns i loggarna - se filnamnen nedan.)")

    # Senaste händelserna: visar vad som hände precis före felet.
    if kontext > 0:
        senaste = _senaste_rader(logs_dir, kontext, max_bytes)
        if senaste:
            rader.append("")
            rader.append("--- SENASTE HÄNDELSER (nyaste sessionsloggen) " + "-" * 15)
            rader.extend(f"  {_rad(r)[:MAX_LINE]}" for r in senaste)

    if extra:
        rader.append("")
        rader.append("--- STATUS " + "-" * 63)
        for r in extra:
            rader.append(f"  {_rad(r)}")

    if data["lästa"]:
        rader.append("")
        rader.append("--- LÄSTA LOGGFILER " + "-" * 54)
        for f in data["lästa"]:
            if f.get("storlek", 0) > f["byte"]:
                rader.append(f"  {f['fil']}  (sista {f['byte'] / 1024:.0f} kB "
                             f"av {f['storlek'] / 1_048_576:.1f} MB)")
            else:
                rader.append(f"  {f['fil']}  (hel, {f['byte'] / 1024:.0f} kB)")

    rader.append("")
    rader.append(f"--- rapporten byggd på {time.perf_counter() - start:.3f} s "
                 + "-" * 30)
    text = "\n".join(rader) + "\n"
    if avidentifiera_text:
        text = avidentifiera(text, logs_dir)
    return text


def _tid_kort(v: Any) -> str:
    """Kort, jämförbar tidsstämpel: dagens loggar tid, äldre med datum."""
    if isinstance(v, datetime):
        return f"{v:%H:%M:%S}" if v.date() == datetime.now().date() \
            else f"{v:%Y-%m-%d %H:%M:%S}"
    text = str(v or "").strip()
    m = re.search(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", text)
    if m:
        dag, tid = m.group(1), m.group(2)
        if dag == f"{datetime.now():%Y-%m-%d}":
            return tid
        return f"{dag} {tid}"
    m = re.match(r"^(\d{2}:\d{2}:\d{2})\.\d{3}$", text)
    return m.group(1) if m else text


def _tidsintervall(p: Dict[str, Any]) -> str:
    a, b = _tid_kort(p.get("först")), _tid_kort(p.get("senast"))
    if not a or not b:
        return ""
    return a if a == b else f"{a} → {b}"


def _versionsrad() -> str:
    try:
        module = ("pdfsorter", "pdfsorter_system", "pdfsorter_read",
                  "pdfsorter_data", "pdfsorter_theme")
        delar = []
        for namn in module:
            m = sys.modules.get(namn)
            if m is None:
                continue
            v = getattr(m, "APP_VERSION", getattr(m, "VERSION", "?"))
            delar.append(f"{namn.replace('pdfsorter', '').lstrip('_') or 'main'}={v}")
        if len(set(delar)) > 1:
            return "Moduler: " + ", ".join(delar)
    except Exception:
        pass
    return ""


def _senaste_rader(logs_dir: Optional[Path], antal: int,
                   max_bytes: int) -> List[str]:
    if not logs_dir or not Path(logs_dir).is_dir():
        return []
    filer = [p for p in _nya_filer(Path(logs_dir), 3)
             if not p.name.endswith(".gz")
             and not p.name.lower().startswith(("errors", "krasch"))]
    if not filer:
        return []
    text = read_log(filer[0], tail_bytes=max_bytes)["text"]
    return text.splitlines()[-antal:]


# ---------------------------------------------------------------------------
# Alltid en färdig rapport på disk
# ---------------------------------------------------------------------------
def _dump_if_due(min_seconds: float = 60.0) -> None:
    """Skriv en färdig rapport när ett NYTT fel inträffar (högst var 60:e s).

    Då finns filen redan när någon frågar - även om appen inte går att
    öppna. Skrivningen får aldrig påverka appen.
    """
    logs_dir = _State.logs_dir
    if not logs_dir:
        return
    nu = time.time()
    with _State.lock:
        if nu - _State.last_dump < min_seconds:
            return
        _State.last_dump = nu
    try:
        Path(logs_dir).mkdir(parents=True, exist_ok=True)
        mål = Path(logs_dir) / "ai-rapport-senaste.txt"
        extra = []
        try:
            if _State.extra is not None:
                extra = list(_State.extra())
        except Exception:
            extra = []
        text = build_ai_report(logs_dir, extra=extra)
        temporär = mål.with_suffix(".tmp")
        temporär.write_text(text, encoding="utf-8")
        os.replace(temporär, mål)
        with _State.lock:
            _State.dump_path = mål
    except Exception:
        pass


def latest_report_path() -> Optional[Path]:
    """Senaste automatiskt skrivna rapporten, om någon finns."""
    if _State.dump_path and Path(_State.dump_path).exists():
        return Path(_State.dump_path)
    if _State.logs_dir:
        p = Path(_State.logs_dir) / "ai-rapport-senaste.txt"
        return p if p.exists() else None
    return None


def dump_report(logs_dir: Optional[Path] = None,
                extra: Optional[Sequence[str]] = None) -> Optional[Path]:
    """Skriv rapporten till ``logs/ai-rapport-senaste.txt`` direkt."""
    try:
        mål_dir = Path(logs_dir) if logs_dir else _State.logs_dir
        if not mål_dir:
            return None
        mål_dir.mkdir(parents=True, exist_ok=True)
        mål = mål_dir / "ai-rapport-senaste.txt"
        text = build_ai_report(mål_dir, extra=extra)
        temporär = mål.with_suffix(".tmp")
        temporär.write_text(text, encoding="utf-8")
        os.replace(temporär, mål)
        with _State.lock:
            _State.dump_path = mål
        return mål
    except Exception:
        return None


def sammanfattning(logs_dir: Optional[Path] = None) -> str:
    """En rad för statusraden: `3 fel, 1 varning (senaste 09:31)`."""
    try:
        data = collect(logs_dir)
    except Exception:
        return ""
    fel, var = data["fel"], data["varningar"]
    if not fel and not var:
        return "Inga fel loggade"
    delar = []
    if fel:
        delar.append(f"{len(fel)} fel")
    if var:
        delar.append(f"{len(var)} varningar")
    senast = max((str(p.get("senast", "")) for p in fel + var), default="")
    return ", ".join(delar) + (f" (senast {senast[:8]})" if senast else "")
