#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArkivPiloten - automatisk sortering av PDF-filer till undermappar.
================================================================

Starta genom att dubbelklicka på pdfsorter.py (eller pdfsorter.pyw på
Windows - då syns ingen terminal alls).

Vad den gör
-----------
Bevakar en eller flera inmappar, läser varje ny PDF och flyttar den till
en undermapp i utmappen: allt om Pilkington -> Utmapp/Pilkington/.
Undermappar skapas automatiskt.

Ett tydligt stödord räcker normalt för att avgöra vart filen hör. En
kategori kan kräva fler - sätt "Kräver" under Matchningar om ett företag
har ord som lätt ger falska träffar. Ett bevisat organisationsnummer
räcker däremot alltid ensamt.

Är appen osäker visas en dialogruta med 10 föreslagna stödord ur just den
filen. Du bockar i de ord som hör till rätt kategori. Därefter går filen -
och alla framtida liknande filer - automatiskt.

Filer i projektet
-----------------
Fem filer som ska ligga i samma mapp:

    pdfsorter.py          det här: matchning, jobbmotor och gränssnitt
    pdfsorter_data.py     inställningar, regler, historik, filflytt
    pdfsorter_read.py     textextraktion, OCR, de tio ordförslagen
    pdfsorter_system.py   ikon, autostart, systemfält, hjälptext
    pdfsorter_theme.py    färger och ttk-stilar

De två första är nödvändiga. Saknas system- eller temamodulen startar
appen ändå, utan ikon respektive med Tkinters gråa standardutseende.

Funktioner
----------
* Flera bevakade inmappar samtidigt
* Årsmappar - läser dokumentets datum och lägger filen i Pilkington/2025/
* Kör i systemfältet (systray) med snabbmeny
* Autostart med operativsystemet
* Egen ikon, ritad i koden - inga externa bildfiler
* All matchning sparas i JSON som kan öppnas och redigeras i appen
* Ångra-funktion för varje flyttad fil
* OCR för inskannade PDF:er, och för logotyper i annars textbaserade filer
* Bara en instans åt gången - två samtidiga appar skulle skriva över
  varandras regler

Var sparas inställningarna?
    Alltid i appmappen (undermapparna json/, logs/, cache/ m.fl.) -
    inget sparas utanför appmappen på någon plattform.
    Kan överstyras med miljövariabeln PDFSORTER_HOME.

Beroenden - alla valfria, appen startar ändå:
    pip install pymupdf pypdf pdfminer.six pystray pillow pytesseract
    OCR kräver även systemprogrammet Tesseract.

Kommandorad (frivilligt):
    python pdfsorter.py --status
    python pdfsorter.py --input MAPP --output MAPP --no-ask
    python pdfsorter.py --watch
"""

from __future__ import annotations

import argparse
import concurrent.futures
import math
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


# ========================================================================
# KONSTANTER
# ========================================================================

APP_NAME = "ArkivPiloten"
APP_VERSION = "1.4.5"

#: Höjs bara om formatet på JSON-filerna ändras på ett icke bakåtkompatibelt
#: sätt. Läskoden tål okända fält, så tillägg kräver ingen höjning.
SCHEMA_VERSION = 1


# ==========================================================================
# WINDOWS: INGA KONSOLFÖNSTER VID UNDERPROCESSER (ANVÄNDARORDER 2026-10-05)
# ==========================================================================
# Under pythonw finns ingen konsol; varje subprocess.run/Popen som skapar
# ett konsolfönster får ett fönster att BLINKA till (t.ex. en gång per
# OCR-sida via pytesseract). Därför patchas subprocess globalt så att alla
# barnprocesser - våra egna och bibliotekens - startar dolda. Påverkar
# inte Linux/macOS, och anrop som själva ber om en konsol (skaparen anger
# egna flaggor) får behålla sitt beteende via setdefault.
if sys.platform.startswith("win"):
    try:
        import subprocess as _sp_win

        _SKAPA_DOLD = 0x08000000            # CREATE_NO_WINDOW
        _SI_WIN = _sp_win.STARTUPINFO()
        _SI_WIN.dwFlags |= _sp_win.STARTF_USESHOWWINDOW
        _SI_WIN.wShowWindow = 0             # SW_HIDE
        _orig_run_win = _sp_win.run
        _orig_popen_win = _sp_win.Popen

        def _run_dold(*a, **k):
            k.setdefault("startupinfo", _SI_WIN)
            k.setdefault("creationflags", _SKAPA_DOLD)
            return _orig_run_win(*a, **k)

        class _Popen_dold(_orig_popen_win):
            def __init__(self, *a, **k):
                k.setdefault("startupinfo", _SI_WIN)
                k.setdefault("creationflags", _SKAPA_DOLD)
                super().__init__(*a, **k)

        _sp_win.run = _run_dold
        _sp_win.Popen = _Popen_dold
    except Exception:
        pass


# ==========================================================================
# DEL 1 - LÄSA PDF OCH TA FRAM STÖDORD
# ==========================================================================
#
# Ligger i pdfsorter_read.py bredvid den här filen. Den modulen sköter
# textextraktion, OCR och de tio ordförslagen. Utan den kan appen inte läsa
# PDF alls, så här avbryter vi med ett begripligt meddelande i stället för
# ett kryptiskt importfel.

try:
    from pdfsorter_read import (          # noqa: F401
        Candidate,
        Extraction,
        _DOC_TYPE_WORDS,
        _ID_HINT,
        _RECIPIENT_MARKERS,
        _luhn_ok,
        _recipient_zone,
        backend_status,
        extract,
        guess_category_name,
        has_pymupdf,
        _open_pymupdf,
        normalize,
        ocr_available,
        STOPWORDS,
        reading_health,
        set_tesseract_path,
        status_text,
        suggest_keywords,
    )
    READ_MODULE = True
except ImportError as _read_err:
    READ_MODULE = False
    _READ_MISSING = str(_read_err)
    sys.stderr.write(
        f"\n{APP_NAME} kunde inte starta.\n\n"
        f"Filen pdfsorter_read.py hittades inte bredvid pdfsorter.py.\n"
        f"Den behövs för att läsa PDF-filer.\n\n"
        f"Detalj: {_READ_MISSING}\n\n"
        f"Lägg tillbaka filen i samma mapp och försök igen.\n")
    try:
        import tkinter as _tk_err
        from tkinter import messagebox as _mb_err
        _root = _tk_err.Tk()
        _root.withdraw()
        _mb_err.showerror(
            APP_NAME,
            "Filen pdfsorter_read.py saknas.\n\n"
            "Den behövs för att läsa PDF-filer och ska ligga i samma mapp "
            "som pdfsorter.py.")
        _root.destroy()
    except Exception:
        pass
    raise SystemExit(2)

# Tillägg i läsmodulen importeras separat, så att en GAMMAL men fungerande
# kopia av pdfsorter_read.py inte stoppar hela appen (som den gjorde när
# den blandades med en ny huvudfil) - funktionen som saknas stängs av i
# stället, och varningen om blandade versioner talar om vad som gäller.
try:
    from pdfsorter_read import denoise_numbers      # noqa: F401
    OLD_READ_MODULE = False
except ImportError:
    OLD_READ_MODULE = True

    def denoise_numbers(text: str) -> str:          # type: ignore[misc]
        """Gammal läsmodul: OCR-brustoleransen är avstängd."""
        return text


# ==========================================================================
# DEL 2 - LAGRING OCH FILFLYTT
# ==========================================================================
#
# Ligger i pdfsorter_data.py bredvid den här filen: inställningar, regler,
# historik och själva flytten av en PDF till rätt mapp. Utan den kan appen
# varken läsa sina regler eller flytta en fil, så här avbryter vi med ett
# begripligt meddelande i stället för ett kryptiskt importfel.

try:
    from pdfsorter_data import (        # noqa: F401
        SCHEMA_VERSION,
        DEFAULT_SETTINGS,
        SUBFOLDER_TEMPLATES,
        Rules,
        _io_lock,
        _read_json,
        _write_json,
        append_history,
        config_dir,
        config_dir_mode,
        InstanceLock,
        consume_show_request,
        history_path,
        flush_history,
        compact_history_if_large,
        is_ignored_file,
        json_dir,
        migrate_to_portable,
        list_ignored_files,
        load_history,
        lock_path,
        mark_ignored_file,
        request_show,
        load_settings,
        now_iso,
        place_file,
        render_subfolder,
        replace_history,
        rules_path,
        safe_folder_name,
        save_settings,
        unignore_file,
        settings_path,
        sha256_file,
        unique_target,
        build_matching_report,
        report_path,
    )
    DATA_MODULE = True
except ImportError as _data_err:
    DATA_MODULE = False
    sys.stderr.write(
        f"\n{APP_NAME} kunde inte starta.\n\n"
        f"Filen pdfsorter_data.py hittades inte bredvid pdfsorter.py.\n"
        f"Den behovs for att spara installningar och flytta filer.\n\n"
        f"Detalj: {_data_err}\n\n"
        f"Lagg tillbaka filen i samma mapp och forsok igen.\n")
    try:
        import tkinter as _tk_d
        from tkinter import messagebox as _mb_d
        _r = _tk_d.Tk(); _r.withdraw()
        _mb_d.showerror(
            APP_NAME,
            "Filen pdfsorter_data.py saknas.\n\n"
            "Den behovs for att spara installningar och flytta filer, och "
            "ska ligga i samma mapp som pdfsorter.py.")
        _r.destroy()
    except Exception:
        pass
    raise SystemExit(2)


# ==========================================================================
# DEL 3 - MATCHNINGSMOTORN
# ==========================================================================

#: Stödord som är starka bevis - de pekar ut ett bestämt företag eller
#: projekt och kan inte gärna dyka upp av en slump i någon annans dokument.
STRONG_KINDS = ("orgnr", "vat", "domain", "giro", "kod")

#: Vad de starka typerna heter för användaren.
STRONG_LABELS = {
    "orgnr": "organisationsnummer",
    "vat": "VAT-nummer",
    "giro": "bankgiro/plusgiro",
    "domain": "domän",
    "kod": "projekt-/objektkod",
}

#: Regex för att känna igen starka stödord direkt ur texten, utan att behöva
#: veta vilken typ de hade när de sparades.
_STRONG_PATTERNS = (
    # Blanksteg tillåts: "556033 9086" förekommer i sidfötter och OCR-text.
    ("orgnr", re.compile(r"^\d{6}[-\u2013 ]?\d{4}$")),
    ("vat", re.compile(r"^[a-z]{2}\d{9,12}$")),
    ("giro", re.compile(r"^\d{3,4}-\d{4}$")),
    # Domän: sista delen måste vara en riktig toppdomän av bokstäver.
    # Tidigare räckte "\w", vilket gjorde "24.10.2025", "1.234" och
    # "v1.4.4" till starka bevis - datum och versionsnummer är precis
    # motsatsen till ett unikt kännetecken.
    ("domain", re.compile(
        r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")),
    # Projekt- och objektkoder: IF26, AB-1200, K4711.
    # Bokstäver OCH siffror i samma korta ord är ingen slump - ingen
    # skriver "IF26" i förbigående. Ett rent årtal ("2025"), ett datum
    # ("2024-01") eller ett belopp är däremot vardagsmat och får aldrig
    # räknas som ett starkt bevis: det kringgår poängtröskel, antal
    # stödord och textlängd i _auto_blocker.
    ("kod", re.compile(
        r"^(?=.{3,12}$)(?=.*\d)(?=.*[a-z])[a-z0-9]+(?:[-:/][a-z0-9]+)*$")),
)


def _strength_of(t: str) -> str:
    for kind, pat in _STRONG_PATTERNS:
        if pat.match(t):
            # Org.nr ska ha giltig kontrollsiffra för att räknas. Ett
            # tiosiffrigt nummer med fel checksiffra är ett kundnummer,
            # inte ett organisationsnummer (REQ-C1 AC-1.2) - och det är
            # ingen projektkod heller, eftersom koder måste innehålla
            # minst en bokstav.
            if kind == "orgnr" and not _luhn_ok(
                    t.replace("-", "").replace("–", "")):
                continue
            return kind
    return ""


def keyword_strength(text: str) -> str:
    """Vilken sorts bevis är det här stödordet?

    Returnerar "orgnr", "vat", "giro", "domain", "kod" eller "" för vanliga
    ord. Används av den strikta sorteringen, som kan kräva att minst ett
    riktigt starkt bevis finns innan en fil flyttas automatiskt.

    OCR-tolerant (REQ-N6): matchar inte originaltexten prövas även en
    avbrusad kopia, så att "556O33-9O86" ur en skanning ändå räknas som
    organisationsnummer (kontrollsiffran räknas fortfarande efter).
    """
    t = normalize(text)
    d = denoise_numbers(t)
    if d != t:
        s = _strength_of(d)
        if s in ("orgnr", "vat", "giro"):
            # Ett OCR-läkt starkt bevis går före t.ex. "kod"-träffen.
            return s
    return _strength_of(t) or (_strength_of(d) if d != t else "")


#: Skiljetecken som får skilja delarna i en identifierare. Samma nummer
#: skrivs "556033-9086", "556033 9086", "556033–9086" eller "5560339086"
#: beroende på avsändare och OCR - regeln ska matcha alla skrivsätten.
_ID_SEP_RE = re.compile(r"[-\u2013\u2014\u2212:/]+")

#: Memo: text -> är stödordet en flexibel identifierare? (Dyr att räkna
#: ut per dokument, svaret beror bara på texten.)
_FLEX_CACHE: Dict[str, bool] = {}


def _id_groups(text: str) -> List[str]:
    """Dela en identifierare i sina delar, oberoende av skrivsätt.

    "556033-9086", "556033 9086" och "556033–9086" ger alla
    ["556033", "9086"]. Ett tiosiffrigt org.nr utan skiljetecken delas i
    6+4 när kontrollsiffran stämmer, och ett VAT-nummer i SE + 6 + 4 + 2.
    """
    parts = [p for p in _ID_SEP_RE.split(normalize(text)) if p]
    if len(parts) == 1:
        p = parts[0]
        if p.isdigit() and len(p) == 10 and _luhn_ok(p):
            return [p[:6], p[6:]]
        m = re.fullmatch(r"se(\d{12})", p)
        if m:
            d = m.group(1)
            return ["se", d[:6], d[6:10], d[10:]]
    return parts


def _flexible_id_pattern(text: str) -> Optional[re.Pattern]:
    """Mönster som matchar samma identifierare oavsett skiljetecken.

    Returnerar None för vanliga ord och för ensamma delar - då gäller den
    exakta ordgränsen som förut.
    """
    parts = _id_groups(text)
    if not 2 <= len(parts) <= 6:
        return None
    if not all(re.fullmatch(r"[a-z0-9]+", p) for p in parts):
        return None
    core = r"[-\u2013\u2014\u2212:/ ]*".join(re.escape(p) for p in parts)
    return re.compile(r"(?<![0-9a-z])" + core + r"(?![0-9a-z])")


def _is_flexible(text: str) -> bool:
    """Sant om stödordet är en stark identifierare med flera delar."""
    key = str(text or "")
    v = _FLEX_CACHE.get(key)
    if v is None:
        v = bool(keyword_strength(key)) and \
            _flexible_id_pattern(key) is not None
        if len(_FLEX_CACHE) > 4000:      # minnestak, som mönstercachen
            _FLEX_CACHE.clear()
        _FLEX_CACHE[key] = v
    return v


@dataclass
class CategoryScore:
    name: str
    score: float
    matched: List[str] = field(default_factory=list)
    #: stödord -> zon där det hittades ("header", "recipient", ...)
    zones: Dict[str, str] = field(default_factory=dict)
    #: Flersidig matchning: stödord som upprepas på flera sidor, med
    #: sidantal - "pilkington ×4 sidor". Starkt avsändarbevis.
    multipage: List[str] = field(default_factory=list)
    #: Rankningsbonus från en säker lärd klassificerare. Påverkar bara
    #: ordningen och marginalen - aldrig beviskraven i _auto_blocker.
    bonus: float = 0.0

    def zone_of(self, word: str) -> str:
        return self.zones.get(word, "body")

    @property
    def anchored(self) -> List[str]:
        """Stödord som hittades på en plats som pekar ut avsändaren."""
        return [w for w in self.matched
                if self.zone_of(w) in ("sender", "filename", "header",
                                       "identity", "pagehead", "pagefoot")]

    @property
    def only_recipient(self) -> bool:
        """Sant om alla träffar låg i mottagarblocket - då är vi kunden."""
        return bool(self.matched) and all(
            self.zone_of(w) == "recipient" for w in self.matched)

    @property
    def strong(self) -> List[str]:
        """De matchade stödord som är starka identifierare."""
        return [w for w in self.matched if keyword_strength(w)]

    @property
    def has_strong(self) -> bool:
        return bool(self.strong)

    @property
    def conclusive(self) -> List[str]:
        """Starka identifierare som dessutom står på avsändarens plats.

        Ett organisationsnummer med giltig kontrollsiffra, en domän eller
        ett bankgiro i brevhuvudet, sidfoten eller på en org.nr-rad är i
        praktiken ett bevis. Sådana nummer nämns inte i förbigående - de
        står där för att de tillhör avsändaren.
        """
        return [w for w in self.strong
                if self.zone_of(w) in ("sender", "header", "identity",
                                       "pagehead", "pagefoot", "filename")]

    @property
    def is_conclusive(self) -> bool:
        return bool(self.conclusive)


@dataclass
class Decision:
    path: Path
    extraction: Extraction
    scores: List[CategoryScore]
    status: str                     # "auto" | "ask" | "error"
    reason: str = ""
    #: N14: lärd klassificerares förslag (kategori, antal liknande filer);
    #: visas i granskningsrutan när reglerna inte räcker till.
    learned_hint: Optional[Tuple[str, int]] = None

    @property
    def best(self) -> Optional[CategoryScore]:
        return self.scores[0] if self.scores else None

    @property
    def runner_up(self) -> Optional[CategoryScore]:
        return self.scores[1] if len(self.scores) > 1 else None


def _kw_pattern(kw: Dict[str, Any]) -> re.Pattern:
    """Bygg sökmönstret för ett stödord.

    "Helt ord" ska hindra att `glas` matchar `glasögonfodral`, men får
    inte hindra att projektkoden `IF26` matchar `IF26-2024`,
    `IF26_bilaga` eller `IF26/A`. Bindestreck och understreck är
    avgränsare i verkliga dokumentbeteckningar, inte en del av ordet.

    Gränsen är därför bokstav/siffra: ordet får inte sitta ihop med fler
    bokstäver eller siffror. `IF26` matchar alltså inte `IF260` eller
    `IF26A` - det är andra beteckningar - men väl `IF26-2024`.
    """
    text = re.escape(kw["text"])
    if kw.get("whole_word", True):
        # \b fungerar dåligt intill siffror och bindestreck, så gränserna
        # skrivs ut explicit. [^\W_] = bokstav eller siffra, inte _
        return re.compile(r"(?<![^\W_])" + text + r"(?![^\W_])")
    return re.compile(text)


_PATTERN_CACHE: Dict[Tuple[str, bool, bool], re.Pattern] = {}


def _cached_pattern(kw: Dict[str, Any]) -> re.Pattern:
    """Sökmönstret för ett stödord (cache: text, helord, flexibel).

    Starka identifierare (org.nr, VAT, giro, projektkod) får ett flexibelt
    mönster: samma nummer matchar oavsett om det skrivs med bindestreck,
    blanksteg, tankstreck eller helt utan skiljetecken. Vanliga ord
    matchas exakt som förut.
    """
    text = kw["text"]
    helord = bool(kw.get("whole_word", True))
    flex = helord and _is_flexible(text)
    key = (text, helord, flex)
    pat = _PATTERN_CACHE.get(key)
    if pat is None:
        pat = _flexible_id_pattern(text) if flex else _kw_pattern(kw)
        # Minnestak (ANVÄNDARORDER 2026-08-26): mönstercachen får inte
        # växa obundet; vid tak töms den och byggs upp igen billigt.
        if len(_PATTERN_CACHE) > 4000:
            _PATTERN_CACHE.clear()
        _PATTERN_CACHE[key] = pat
    return pat


#: Var i dokumentet ett stödord hittades, och hur mycket det väger.
#:
#: Ett företagsnamn i brevhuvudet betyder att de skickat fakturan. Samma
#: namn under "Fakturaadress" betyder tvärtom att de är kund. Nämns namnet
#: mitt i en mening säger det nästan ingenting alls. Utan den här
#: viktningen sorteras fakturor till en leverantör som om de vore från dem.
ZONE_WEIGHTS: Dict[str, float] = {
    "sender": 1.60,       # allra översta raden - nästan alltid avsändaren
    "filename": 1.30,     # står i filnamnet - någon har döpt filen medvetet
    "header": 1.25,       # brevhuvudet, alltså avsändaren
    "identity": 1.15,     # rad med org.nr, VAT, bankgiro
    "pagefoot": 1.15,     # sidfot - avsändarens org.nr och bankgiro
    "pagehead": 1.20,     # sidhuvud som återkommer på varje sida
    "body": 1.00,         # brödtext, tabeller
    "recipient": 0.30,    # mottagarblocket - det är kunden, inte avsändaren
}

#: Zonnamn att visa för användaren.
ZONE_LABELS: Dict[str, str] = {
    "sender": "som avsändare överst",
    "filename": "i filnamnet",
    "header": "i brevhuvudet",
    "identity": "på rad med org.nr",
    "pagefoot": "i sidfoten",
    "pagehead": "i sidhuvudet",
    "body": "i löptexten",
    "recipient": "i mottagarblocket",
}


#: Bredd i bildpunkter på stapeln som visar stödordens inbördes styrka
#: i granskningsdialogen.
BAR_WIDTH = 90

#: Under så här många poäng räknas en kategori inte alls. Hindrar att
#: enbart nedviktade mottagarträffar råkar bli en match.
MIN_ZONE_SCORE = 0.35

#: Delar upp text i "ord" på samma sätt som ordgränserna i `_kw_pattern()`:
#: bokstäver och siffror hör ihop, allt annat skiljer. Måste stämma överens
#: med `(?<![^\W_])...(?![^\W_])` för att förfiltret ska vara säkert.
_TOKEN_RE = re.compile(r"[^\W_]+")


def _identity_zone(text: str) -> str:
    """Rader som innehåller org.nr, VAT, bankgiro och liknande.

    De hör till avsändaren även när de står längre ned på sidan.
    """
    out = []
    for line in text.splitlines():
        low = normalize(line)
        if _ID_HINT.search(low):
            out.append(low)
    return "\n".join(out)


#: Ord som inleder en mening. Ett brevhuvud består av namn och adresser,
#: inte av löpande text - dyker de här orden upp är vi förbi huvudet.
_PROSE_STARTERS = frozenset("""
vi ni jag du han hon man denna detta dessa den det har hade ska skall
kan kunde vill ville får fick bör måste tack hej hejsan enligt gällande
angående efter innan under vid som att om men och eller samt därför
eftersom vänligen bifogat bifogas härmed nedan ovan se observera notera
beslut beslutet mötet mote narvarande deltagare dagordning punkt
we you they this that these have has will would can could should please
regarding attached enclosed following below above note
""".split())

#: Ett brevhuvud är korta rader. Löptext är längre.
_HEADER_MAX_LINE = 60


def _looks_like_prose(line: str) -> bool:
    """Är raden löpande text snarare än en brevhuvudsrad?

    Brevhuvudet innehåller firmanamn, adress och kontaktuppgifter - korta
    rader utan meningsbyggnad. Så fort en riktig mening börjar är vi inne
    i dokumentets innehåll, och företag som nämns där är omtalade snarare
    än avsändare.
    """
    low = normalize(line)
    if not low:
        return False
    ord_ = low.split()
    if not ord_:
        return False
    # Identitetsrader (org.nr, telefon, bankgiro) är alltid brevhuvud,
    # även när de är långa.
    if _ID_HINT.search(low):
        return False
    if ord_[0] in _PROSE_STARTERS:
        return True
    # Lång rad med många ord och en avslutande punkt = mening.
    if len(low) > _HEADER_MAX_LINE and len(ord_) >= 8:
        return True
    return False


def _trim_prose(text: str) -> str:
    """Klipp bort allt från den första löptextraden och framåt.

    Sidhuvudsbandet plockas ut geometriskt - de översta 14 procenten av
    sidan. På ett glest dokument räcker det bandet ned i brödtexten, och
    då skulle ett företag som bara nämns i en mening få sidhuvudets vikt.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _looks_like_prose(line):
            return normalize("\n".join(lines[:i]))
    return normalize(text)


def _sender_zone(text: str, max_lines: int = 3) -> str:
    """De allra första meningsfulla raderna - avsändarens namn.

    I nästan all företagspost står avsändaren överst: firmanamnet på rad 1,
    ibland med adressen under. Det är dokumentets starkaste enskilda
    signal, starkare än både filnamn och org.nr, eftersom den säger vem
    brevet kommer FRÅN och inte bara vilka som förekommer i det.

    Bara rader före den första löptextraden räknas, och som mest tre.
    """
    out = []
    for line in text.splitlines():
        low = normalize(line)
        if not low:
            if out:
                break          # tom rad efter namnet avslutar blocket
            continue
        if _looks_like_prose(line):
            break
        first = low.split()[0].rstrip(":.")
        if first in _DOC_TYPE_WORDS:
            break
        if any(low.startswith(m) or f" {m}" in low for m in _RECIPIENT_MARKERS):
            break
        out.append(low)
        if len(out) >= max_lines:
            break
    return "\n".join(out)


def _header_zone(text: str, max_lines: int = 12) -> str:
    """Brevhuvudet - raderna före mottagarblocket.

    Utan avgränsningen skulle "Fakturaadress: Pilkington" på rad 9 räknas
    som brevhuvud, och en faktura TILL Pilkington såg ut att komma FRÅN dem.

    Zonen stängs av tre skäl: mottagarblocket börjar, dokumenttypen
    ("FAKTURA") anges, eller texten övergår i löpande meningar. Det sista
    är viktigt för dokument utan brevhuvud alls - mötesanteckningar som
    nämner ett företag ska inte se ut att komma från det företaget.
    """
    lines = text.splitlines()
    stop = min(len(lines), max_lines)
    seen = 0
    for i, line in enumerate(lines[:max_lines]):
        low = normalize(line)
        if not low:
            continue
        # Mottagarblocket börjar
        if any(low.startswith(m) or f" {m}" in low for m in _RECIPIENT_MARKERS):
            stop = i
            break
        # Dokumenttypen ("FAKTURA", "ARBETSORDER") avslutar brevhuvudet.
        # Allt därefter är innehåll, och företag som nämns där är omtalade
        # snarare än avsändare.
        first = low.split()[0].rstrip(":.")
        if i > 0 and first in _DOC_TYPE_WORDS:
            stop = i
            break
        # Löptexten har börjat - då är brevhuvudet slut. Rad 1 undantas:
        # den är avsändaren även om den råkar vara lång.
        if seen > 0 and _looks_like_prose(line):
            stop = i
            break
        seen += 1
    return normalize("\n".join(lines[:stop]))


@dataclass
class TextZones:
    """Dokumentet uppdelat i zoner, färdignormaliserat för sökning.

    Varje zon finns även som avbrusad kopia (`*_d`, REQ-N6): OCR-text där
    O/0 och I/l/1 förväxlats i sifferrunor. Sökningen prövar originalet
    först och kopian bara som reserv - brusfri text kostar inget extra.
    """
    full: str = ""
    filename: str = ""
    sender: str = ""
    header: str = ""
    identity: str = ""
    recipient: str = ""
    pagehead: str = ""
    pagefoot: str = ""
    full_d: str = ""
    filename_d: str = ""
    sender_d: str = ""
    header_d: str = ""
    identity_d: str = ""
    recipient_d: str = ""
    pagehead_d: str = ""
    pagefoot_d: str = ""
    #: Alla ord som förekommer i dokumentet eller filnamnet, som mängd.
    #: Används för att avfärda stödord utan att köra regex - se `locate()`.
    tokens: frozenset = frozenset()

    @classmethod
    def build(cls, text: str, filename: str = "",
              page_header: str = "", page_footer: str = "") -> "TextZones":
        recipient = _recipient_zone(text)
        identity = _identity_zone(text)
        # Rader som hör till mottagaren ska inte räknas som avsändarens
        # identitet, även om de innehåller ett org.nr.
        if recipient:
            identity = "\n".join(
                ln for ln in identity.splitlines() if ln not in recipient)
        full = normalize(text)
        namn = normalize(re.sub(r"[_\-.]+", " ", filename))
        sender = _sender_zone(text)
        header = _header_zone(text)
        pagehead = _trim_prose(page_header)
        pagefoot = normalize(page_footer)
        # Även de avbrusade runorna blir tokens, så att förfiltret
        # kan_finnas() släpper igenom ett OCR-skadat org.nr.
        return cls(
            full=full, full_d=denoise_numbers(full),
            filename=namn, filename_d=denoise_numbers(namn),
            sender=sender, sender_d=denoise_numbers(sender),
            header=header, header_d=denoise_numbers(header),
            identity=identity, identity_d=denoise_numbers(identity),
            recipient=recipient, recipient_d=denoise_numbers(recipient),
            pagehead=pagehead, pagehead_d=denoise_numbers(pagehead),
            pagefoot=pagefoot, pagefoot_d=denoise_numbers(pagefoot),
            tokens=frozenset(_TOKEN_RE.findall(
                full + " " + namn + " " + denoise_numbers(full))),
        )

    def kan_finnas(self, kw: Dict[str, Any]) -> bool:
        """Snabbtest: kan det här stödordet över huvud taget finnas?

        Med 600 regler och 30 kategorier är kanske fem relevanta för ett
        givet dokument. Att köra regex för de andra 595 är rent slöseri:
        76 ms per fil, tio gånger dyrare än att läsa själva PDF:en.

        Varje stödord innehåller minst ett helt ord. Finns inte det ordet
        bland dokumentets ord kan hela uttrycket omöjligt matcha, och en
        mängduppslagning är tusenfalt billigare än en regexsökning.

        Undantag: stödord utan `whole_word` kan matcha mitt inne i ett ord
        ("kington" i "Pilkington") och måste alltid prövas på riktigt.
        """
        if not kw.get("whole_word", True):
            return True
        if _is_flexible(kw["text"]):
            # Delarna kan stå med eller utan skiljetecken ("556033 9086",
            # "5560339086") - då räcker inte mängduppslagningen, utan
            # regexen får avgöra. Sådana stödord är få.
            return True
        delar = _TOKEN_RE.findall(kw["text"])
        if not delar:
            return True
        # Alla delar måste finnas - "saint gobain" kräver båda orden.
        return all(d in self.tokens for d in delar)

    def locate(self, pattern: re.Pattern) -> Tuple[bool, str, float]:
        """Var träffar mönstret? Returnerar (träff, zon, vikt).

        Zonerna prövas i fallande vikt, så den mest talande platsen vinner
        när ett ord förekommer flera gånger. Innehållet väger tyngre än
        filnamnet: står namnet i mottagarblocket spelar det ingen roll att
        någon råkat skriva det i filnamnet också.

        **Förtest först.** De allra flesta stödord finns inte alls i ett
        givet dokument - med 600 regler och 30 kategorier är kanske fem
        relevanta. Zonerna är delmängder av `full` (utom `filename`), så
        hittas ordet varken där eller i filnamnet kan det omöjligt finnas
        i någon zon. Ett enda anrop i stället för sju.
        """
        def träffar(zon: str) -> bool:
            """Mönstret i zonen - eller i zonens avbrusade OCR-kopia."""
            text = getattr(self, zon)
            if text and pattern.search(text):
                return True
            alt = getattr(self, zon + "_d", "")
            return bool(alt and alt != text and pattern.search(alt))

        i_full = träffar("full")
        i_name = bool(self.filename) and träffar("filename")
        if not i_full and not i_name:
            return False, "", 0.0


        in_recipient = bool(self.recipient) and träffar("recipient")

        if i_full:
            for zone in ("sender", "header", "pagehead", "identity", "pagefoot"):
                if träffar(zone):
                    return True, zone, ZONE_WEIGHTS[zone]

        if i_name:
            # Filnamnet räknas bara som starkt bevis om dokumentet inte
            # motsäger det genom att ha namnet i mottagarblocket.
            if in_recipient:
                return True, "recipient", ZONE_WEIGHTS["recipient"]
            return True, "filename", ZONE_WEIGHTS["filename"]

        if in_recipient:
            return True, "recipient", ZONE_WEIGHTS["recipient"]
        return True, "body", ZONE_WEIGHTS["body"]


#: Zoncache: samma dokument beslutas ibland flera gånger (kö + omskanning
#: + omskanning efter inlärning). Att bygga om zonerna (normalisering,
#: zonregex) är det dyraste steget i matchningen - cacha per innehåll.
_ZONES_CACHE: "OrderedDict[str, TextZones]" = OrderedDict()


def _zones_for(text: str, filename: str, page_header: str,
               page_footer: str) -> TextZones:
    import hashlib
    key = hashlib.sha1(
        (text + "\x00" + filename + "\x00" + page_header + "\x00" + page_footer)
        .encode("utf-8", "ignore")).hexdigest()
    z = _ZONES_CACHE.get(key)
    if z is None:
        z = TextZones.build(text, filename, page_header, page_footer)
        _ZONES_CACHE[key] = z
        while len(_ZONES_CACHE) > 200:
            _ZONES_CACHE.popitem(last=False)
    return z


#: Hur mycket varje avvisande sänker ett stödords vikt, och hur snabbt
#: gamla avvisanden glöms (halveringstid i dagar). Efter fem avvisanden
#: väger ordet noll och kan inte längre flytta en fil.
_REJECT_STEP = 0.2
_REJECT_HALF_LIFE_DAYS = 365.0


def _reject_factor(kw: Dict[str, Any],
                   now: Optional[datetime] = None) -> float:
    """Viktfaktor 0-1 utifrån hur ofta stödordet lett fel.

    Avvisanden åldras: ett ord som rättades för ett år sedan väger hälften
    så tungt som ett som rättades i går. På så vis ligger gamla misstag
    inte kvar och stör när reglerna väl blivit bättre.
    """
    n = int(kw.get("rejected", 0) or 0)
    if n <= 0:
        return 1.0
    age = 0.0
    stamp = str(kw.get("rejected_at", "") or "")
    if stamp:
        try:
            t = datetime.fromisoformat(stamp)
            nu = now or datetime.now().astimezone()
            if t.tzinfo is None:
                t = t.astimezone()
            age = max(0.0, (nu - t).total_seconds() / 86400.0)
        except (ValueError, TypeError, OSError):
            age = 0.0
    eff = n * (0.5 ** (age / _REJECT_HALF_LIFE_DAYS)) if age else float(n)
    return max(0.0, 1.0 - _REJECT_STEP * eff)


def score_text(rules: Rules, text: str, filename: str = "",
               page_header: str = "", page_footer: str = "",
               token_pages: Optional[Dict[str, int]] = None,
               body: str = "") -> List[CategoryScore]:
    """Poängsätt texten mot alla aktiva kategorier.

    Varje stödord vägs efter var i dokumentet det står. Ett namn i
    brevhuvudet räknas fullt ut, samma namn i mottagarblocket till knappt
    en tredjedel.

    FLERSIDIG MATCHNING (användarorder 2026-09-07): `token_pages` säger
    hur många sidor varje ord förekommer på. Ett stödord som upprepas på
    flera sidor sitter i ett brevhuvud/sidfot som följer med varje blad -
    ett sådant bevis får ett litet tillägg (0,15 per ord, max 0,45).
    Tillägget ändrar rangordningen till förmån för den verkliga avsändaren
    utan att ensam lyfta en kategori över auto-gränsen.
    """
    zones = _zones_for(text, filename, page_header, page_footer)
    norm_body = normalize(body) if body else ""
    out: List[CategoryScore] = []

    for cat in rules.categories:
        if not cat.get("enabled", True):
            continue
        total = 0.0
        matched: List[str] = []
        where: Dict[str, str] = {}
        multipage: List[str] = []
        mp_bonus = 0.0

        for kw in cat["keywords"]:
            # Avfärda ordet med en mängduppslagning innan regexen körs.
            if not zones.kan_finnas(kw):
                continue
            # Negativ inlärning: ett ord som lett fel väger mindre, och
            # efter tillräckligt många avvisanden ingenting alls.
            vikt = float(kw["weight"]) * _reject_factor(kw)
            if vikt <= 0:
                continue
            hit, zone, factor = zones.locate(_cached_pattern(kw))
            if not hit:
                continue
            total += vikt * factor
            matched.append(kw["text"])
            where[kw["text"]] = zone
            # Namn och kropp överens (matchningsrundan 2026-10-05): ett
            # stödord som står i FILNAMNET och ÄVEN i själva brödtexten
            # är starkare bevis än namnet ensamt - liten bonus.
            if zone == "filename" and norm_body \
                    and _cached_pattern(kw).search(norm_body):
                total += 0.1
            # Flersidigt bevis: ordet (alla dess delar) återkommer på
            # minst två sidor - typiskt firmamnet i brevhuvud/sidfot.
            if token_pages:
                delar = _TOKEN_RE.findall(kw["text"])
                if delar and all(token_pages.get(d, 1) >= 2 for d in delar):
                    sidor = min(token_pages.get(d, 1) for d in delar)
                    multipage.append(f"{kw['text']} ×{sidor} sidor")
                    mp_bonus = min(mp_bonus + 0.15, 0.45)

        if total >= MIN_ZONE_SCORE:
            # Precision-boost: Har kategorin ett *bevisat* avsändar-ID
            # (org.nr/domän/bankgiro på avsändarens plats) ska den rankas
            # tydligt över en kategori som bara matchade svag löptext. Ett
            # sådant nummer nämns inte i förbigående, så det förtjänar en
            # liten kusing till sin zonvikt. Bara rangordning — flyttar
            # aldrig en ask→auto som annars inte skulle blivit det.
            conclusive = sum(
                1 for w in matched
                if keyword_strength(w) and where[w] in (
                    "sender", "header", "identity", "pagehead",
                    "pagefoot", "filename"))
            if conclusive:
                total += 0.5 * conclusive
            # Samradssamträffande (rond 5, bättre matchning): två träffade
            # stödord på SAMMA rad är starkare bevis än spridda träffar -
            # "Pilkington ... 556033-9086" på en rad är avsändarens egen rad.
            # (Zonerna är normaliserade till en rad, så testet körs mot
            # råtextens rader.)
            if len(matched) >= 2:
                for rad in text.splitlines():
                    lw = normalize(rad)
                    if sum(1 for w in matched if w in lw) >= 2:
                        total += 0.25
                        break
            total += mp_bonus
            out.append(CategoryScore(cat["name"], round(total, 3), matched,
                                     where, multipage))

    out.sort(key=lambda s: (-s.score, s.name))
    return out


#: Färdiga strikthetsnivåer. Väljs i GUI:t och skriver över de enskilda
#: värdena, om användaren inte valt "egen".
STRICTNESS_LEVELS: Dict[str, Dict[str, Any]] = {
    "los": {
        "label": "Lös - sortera så mycket som möjligt",
        "min_score": 1.0, "ambiguity_margin": 0.01, "min_keywords": 1,
        "require_strong": False, "score_ratio": 1.0, "min_text_chars": 0,
        "require_anchor": False, "reject_recipient_only": False,
        "require_anchor_or_strong": False,
        "hint": "Ett svagt ord räcker, var som helst i dokumentet. "
                "Snabbt, men fler filer hamnar fel.",
    },
    "normal": {
        "label": "Normal - säkra bevis krävs (standard)",
        "min_score": 1.0, "ambiguity_margin": 0.5, "min_keywords": 2,
        "require_strong": False, "score_ratio": 1.0, "min_text_chars": 0,
        "require_anchor": False, "reject_recipient_only": True,
        "require_anchor_or_strong": True,
        "hint": "Två olika stödord räcker - men minst ett måste stå på "
                "avsändarens plats (brevhuvud, sidfot, filnamn eller en "
                "rad med org.nr), vara ett starkt kännetecken (org.nr, "
                "VAT, bankgiro, domän) eller återkomma på flera sidor. "
                "Ord som bara nämns i löptexten flyttar aldrig en fil "
                "automatiskt. Ett bevisat org.nr eller en domän räcker "
                "ändå ensamt. Filer där företaget bara står som mottagare "
                "hoppas över.",
    },
    "strikt": {
        "label": "Strikt - kräv tydliga bevis",
        "min_score": 2.0, "ambiguity_margin": 1.0, "min_keywords": 2,
        "require_strong": False, "score_ratio": 1.8, "min_text_chars": 40,
        "require_anchor": True, "reject_recipient_only": True,
        "require_anchor_or_strong": True,
        "hint": "Två stödord och minst ett i brevhuvudet eller filnamnet. "
                "Ett bevisat org.nr eller en domän räcker dock ensamt.",
    },
    "mycket_strikt": {
        "label": "Mycket strikt - bara säkra träffar",
        "min_score": 3.0, "ambiguity_margin": 2.0, "min_keywords": 2,
        "require_strong": True, "score_ratio": 2.5, "min_text_chars": 60,
        "require_anchor": True, "reject_recipient_only": True,
        "require_anchor_or_strong": True,
        "hint": "Kräver org.nr, VAT, bankgiro eller domän som avsändaren "
                "äger. Nästan inga fel, men fler frågor.",
    },
    "egen": {
        "label": "Egen - jag ställer in själv",
        "hint": "Värdena nedan används precis som de står.",
    },
}


#: Ordningen som nivåerna visas i gränssnittet.
STRICT_ORDER = ["los", "normal", "strikt", "mycket_strikt", "egen"]


def effective_thresholds(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Slå ihop vald strikthetsnivå med användarens egna värden.

    En namngiven nivå styr allt. Väljs "egen" används fälten som de står i
    inställningarna, så att den som vill kan finjustera fritt.
    """
    level = str(settings.get("strictness", "normal"))
    preset = STRICTNESS_LEVELS.get(level)
    out = {
        "min_score": float(settings.get("min_score", 1.0)),
        "ambiguity_margin": float(settings.get("ambiguity_margin", 0.5)),
        "min_keywords": int(settings.get("min_keywords", 1)),
        "require_strong": bool(settings.get("require_strong", False)),
        "score_ratio": float(settings.get("score_ratio", 1.0)),
        "min_text_chars": int(settings.get("min_text_chars", 0)),
        "require_anchor": bool(settings.get("require_anchor", False)),
        "reject_recipient_only": bool(settings.get("reject_recipient_only", True)),
        "require_anchor_or_strong": bool(
            settings.get("require_anchor_or_strong", True)),
    }
    if preset and level != "egen":
        for key in out:
            if key in preset:
                out[key] = preset[key]
    return out


# --------------------------------------------------------------------------
# SNABBTANGENTER I ALLA DROPDOWNS/LISTOR (ANVÄNDARORDER 2026-10-06)
# --------------------------------------------------------------------------
# Skriv en bokstav -> markeringen hoppar direkt till första träffen
# (t.ex. 'd' -> första kategorin/mappen som börjar på D). Gäller via
# klassbindningar ALLA comboboxar och listboxar, även de som skapas
# senare i dialoger - en kodväg, enkelhet och konsekvens.
_TA_SPECIAL = {"Return", "Tab", "Escape", "Up", "Down", "Left", "Right",
               "BackSpace", "Delete", "Home", "End", "Prior", "Next",
               "Space", "Alt_L", "Alt_R", "Control_L", "Control_R",
               "Shift_L", "Shift_R", "Menu", "F1", "F2", "F3", "F4"}


#: Skrivbuffert per widget -> (text, giltig till). Nollställs efter en
#: kort paus, precis som i en vanlig rullgardin: "p", "pi", "pil" bygger
#: successivt upp sökordet i stället för att varje tecken söks separat.
_TA_STATE: Dict[str, Tuple[str, float]] = {}
_TA_IDLE = 1.2


def _ta_state(widget) -> Tuple[str, str]:
    key = str(widget)
    buf, until = _TA_STATE.get(key, ("", 0.0))
    if time.monotonic() > until:
        buf = ""
    return key, buf


def _ta_remember(widget, buf: str) -> None:
    key = str(widget)
    if buf:
        _TA_STATE[key] = (buf, time.monotonic() + _TA_IDLE)
    else:
        _TA_STATE.pop(key, None)
    if len(_TA_STATE) > 200:          # enkelt skydd i långa sessioner
        _TA_STATE.clear()


def _ta_forget(event) -> None:
    _ta_remember(event.widget, "")


def _ta_seed(widget) -> str:
    """Pågående sökord när en combobox-rullgardin öppnas.

    Rullgardinens listbox ligger på <combo>.popdown.f.l och får fokus när
    den öppnas. Utan detta skulle "p" + "i" + "l" börja om på "i".
    """
    path = str(widget)
    if ".popdown." not in path:
        return ""
    try:
        root = widget._root()
        combo = root.nametowidget(path.split(".popdown.", 1)[0])
    except Exception:
        return ""
    return _search_key(getattr(combo, "_ta_seed", ""))


def _ta_combobox(event) -> None:
    """Skriv "p" -> markeringen hoppar till första P-namnet; "pil" -> PIL.

    Tecknen byggs upp i en buffert (i stället för att läsa hela fältet),
    så att nästa tangent fortsätter sökordet även sedan fältet fyllts
    med ett komplett namn.
    """
    combo = event.widget
    if getattr(combo, "_egen_ta", False):     # dialog med eget beteende
        return
    keysym = getattr(event, "keysym", "")
    if getattr(event, "state", 0) & 0x4:      # Ctrl-kombos fria
        _ta_remember(combo, "")
        return
    _key, buf = _ta_state(combo)
    if keysym == "BackSpace":
        buf = buf[:-1]
    elif keysym in _TA_SPECIAL:
        return
    else:
        ch = getattr(event, "char", "")
        if not ch or not ch.isprintable() or ch.isspace():
            return
        buf += ch.casefold()
    _ta_remember(combo, buf)
    values = [str(v) for v in (combo["values"] or ())]
    if not buf or not values:
        return
    idx = _typeahead_index(values, buf, 0)
    if idx < 0 and len(buf) > 1:
        # "pp" -> cykla bland P-namnen i stället för att ge upp
        buf = buf[-1]
        _ta_remember(combo, buf)
        idx = _typeahead_index(values, buf, combo.current() + 1)
    if idx >= 0 and combo.current() != idx:
        try:
            combo.current(idx)
        except Exception:
            pass


def _ta_listbox(event) -> None:
    """Samma typahead i öppna listor/rullgardiner, med flera tecken."""
    lb = event.widget
    keysym = getattr(event, "keysym", "")
    if getattr(event, "state", 0) & 0x4:
        _ta_remember(lb, "")
        return
    _key, buf = _ta_state(lb)
    if not buf:
        buf = _ta_seed(lb)               # fortsätt på sökordet från fältet
    if keysym == "BackSpace":
        buf = buf[:-1]
    elif keysym in _TA_SPECIAL:
        return
    else:
        ch = getattr(event, "char", "")
        if not ch or not ch.isprintable() or ch.isspace():
            return
        buf += ch.casefold()
    _ta_remember(lb, buf)
    n = lb.size()
    if not buf or not n:
        return
    values = [str(lb.get(i)) for i in range(n)]
    cur = lb.curselection()
    cur_i = int(cur[0]) if cur else -1
    idx = _typeahead_index(values, buf, 0)
    if idx < 0 and len(buf) > 1:
        buf = buf[-1]
        _ta_remember(lb, buf)
        idx = _typeahead_index(values, buf, cur_i + 1)
    if idx >= 0:
        lb.selection_clear(0, "end")
        lb.selection_set(idx)
        try:
            lb.activate(idx)
        except Exception:
            pass
        lb.see(idx)


def install_snabbtangenter(root) -> None:
    """Klassbindningar: alla TCombobox/Listbox får hopp-beteende,
    även widgets som skapas efteråt (dialoger)."""
    root.bind_class("TCombobox", "<KeyRelease>", _ta_combobox, add="+")
    root.bind_class("Listbox", "<Key>", _ta_listbox, add="+")
    root.bind_class("TCombobox", "<FocusOut>", _ta_forget, add="+")
    root.bind_class("Listbox", "<FocusOut>", _ta_forget, add="+")


# --------------------------------------------------------------------------
# N14 - LÄRANDE KLASSIFICERARE (ANVÄNDARORDER 2026-09-28)
# --------------------------------------------------------------------------
# Naiv Bayes över historikens fattade beslut: varje kategori får en
# ordvikt-profil som tränas stegvis på filerna som flyttas (auto såväl
# som manuella val - korrigeringar blir därmed automatiskt ny träning,
# AC-14.4). Helt lokal, deterministisk, inga ML-paket, inget nätverk.
#
# Säkerhetsfilosofi (AC-14.3): modellen får bryta dödlägen och föreslå
# i granskningsrutan, men på striktare nivåer än "Lös" lyfter den aldrig
# ensam en fil till auto utan stödordsstöd.

#: Träningsmaterial per beslut: de ~60 mest karakteristiska orden.
_LEARNED_MAX_TOKENS = 60
#: Minst så här många lärda filer per kategori innan profilen används.
_LEARNED_MIN_FILES = 5
#: Tak per kategori-profil (minne).
_LEARNED_CAP_TOKENS = 2500
#: Marginal (log-sannolikhet) som krävs för att modellen ska räknas säker.
_LEARNED_CONF_MARGIN = 0.25
#: Hur hårt ett ord som lett fel straffas i modellen. 0 = ingen påverkan.
_LEARNED_NEG_BETA = 0.5
#: Rankningsbonus för modellens val. Liten med flit: den får flytta
#: ordningen och marginalen, aldrig beviskraven.
_LEARNED_BONUS = 0.2

_LEARNED: Optional["LearnedMatcher"] = None


def learned_model_path() -> Path:
    return json_dir() / "learned_model.json"


def learn_tokens(text: str) -> List[str]:
    """De mest karakteristiska orden ur en fil - modellens träningsdata.

    Stoppsord och korta ord gallras bort; frekvens inom filen styr.
    """
    norm = normalize(text or "")
    counts = Counter(t for t in _TOKEN_RE.findall(norm)
                     if len(t) >= 3 and t not in STOPWORDS)
    if not counts:
        return []
    topp = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [t for t, _ in topp[:_LEARNED_MAX_TOKENS]]


class LearnedMatcher:
    """Ordvikter per kategori, tränad på historikens beslut."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else learned_model_path()
        self.cats: Dict[str, Dict[str, Any]] = {}
        self._sig: Optional[Any] = None
        self._dirty = False
        self._load()

    def _sig_now(self):
        try:
            st = self.path.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _load(self) -> None:
        sig = self._sig_now()
        if sig == self._sig and (self.cats or sig is None):
            return
        data = _read_json(self.path, {})
        cats = data.get("cats", {}) if isinstance(data, dict) else {}
        self.cats = {k: v for k, v in cats.items() if isinstance(v, dict)}
        self._sig = sig

    def train(self, category: str, tokens: List[str],
              rejected_for: Optional[str] = None) -> None:
        """Träna på ett beslut.

        `rejected_for` = kategorin som gissade fel. Då räknas filens ord
        som NEGATIVA bevis för den kategorin, så att samma ord inte leder
        fel igen. En användarkorrigering lär alltså både rätt och fel.
        """
        if not category or not tokens:
            return
        c = self.cats.setdefault(category, {"n": 0, "tot": 0, "w": {}})
        c["n"] = int(c.get("n", 0)) + 1
        w = c.setdefault("w", {})
        for t in dict.fromkeys(tokens):          # en gång per fil
            w[t] = int(w.get(t, 0)) + 1
            c["tot"] = int(c.get("tot", 0)) + 1
        if len(w) > _LEARNED_CAP_TOKENS:         # minnestak
            c["w"] = dict(sorted(w.items(), key=lambda kv: -kv[1])
                          [:_LEARNED_CAP_TOKENS])
        if rejected_for and rejected_for != category:
            neg = self.cats.setdefault(rejected_for, {"n": 0, "tot": 0, "w": {}})
            nw = neg.setdefault("neg", {})
            for t in dict.fromkeys(tokens):
                nw[t] = int(nw.get(t, 0)) + 1
                neg["neg_tot"] = int(neg.get("neg_tot", 0)) + 1
            if len(nw) > _LEARNED_CAP_TOKENS:
                neg["neg"] = dict(sorted(nw.items(), key=lambda kv: -kv[1])
                                  [:_LEARNED_CAP_TOKENS])
        self._dirty = True

    def flush(self) -> None:
        if not self._dirty:
            return
        with _io_lock():
            _write_json(self.path, {"updated": now_iso(), "cats": self.cats})
        self._sig = self._sig_now()
        self._dirty = False

    def predict(self, tokens: List[str],
                min_files: int = _LEARNED_MIN_FILES
                ) -> Optional[Tuple[str, float, int]]:
        """(kategori, marginal, antal lärda filer) eller None.

        Normaliserad log-likelihood med Laplace-mjukning + prior;
        marginalet är avståndet till tvåan i samma rum.
        """
        self._load()
        if not tokens:
            return None
        kval = {namn: c for namn, c in self.cats.items()
                if int(c.get("n", 0)) >= min_files}
        if not kval:
            return None
        total = sum(int(c["n"]) for c in kval.values())
        vocab = sum(len(c.get("w", {})) for c in kval.values()) or 1
        tk = Counter(tokens)
        ntk = sum(tk.values()) or 1
        res = []
        for namn, c in kval.items():
            tot = int(c.get("tot", 0)) or 1
            s = math.log(int(c["n"]) / total)              # prior
            w = c.get("w", {})
            neg = c.get("neg", {}) or {}
            neg_tot = int(c.get("neg_tot", 0) or 0)
            for t, k in tk.items():
                s += k * math.log((w.get(t, 0) + 1) / (tot + vocab))
                # Negativ inlärning: jämför hur vanligt ordet är i
                # kategorins RÄTTA filer med hur vanligt det är i de filer
                # där kategorin gissade fel. Är det vanligare bland
                # misstagen straffas det - annars inte alls.
                if neg_tot:
                    nw = int(neg.get(t, 0) or 0)
                    if nw:
                        pos = (int(w.get(t, 0)) + 1) / (tot + vocab)
                        negr = (nw + 1) / (neg_tot + vocab)
                        if negr > pos:
                            s -= (k * min(math.log(negr / pos), 2.0)
                                  * _LEARNED_NEG_BETA)
            res.append((s / ntk, namn))
        res.sort(key=lambda x: (-x[0], x[1]))
        topp = res[0]
        tvaa = res[1][0] if len(res) > 1 else float("-inf")
        return topp[1], topp[0] - tvaa, int(kval[topp[1]]["n"])


def _learned() -> LearnedMatcher:
    global _LEARNED
    if _LEARNED is None:
        _LEARNED = LearnedMatcher()
    return _LEARNED


def flush_learned() -> None:
    """Skriv modellen till disk (anropas vid batchslut/avslut)."""
    try:
        _learned().flush()
    except Exception:
        pass


#: Hårt golv för automatisk sortering, oavsett strikthetsnivå: har färre
#: tecken än så lästs ur dokumentet är underlaget för tunt att flytta på
#: - om inte ett bevisat avsändar-ID (org.nr/domän/bankgiro på avsändarens
#: plats) redan avgör saken. En misslyckad läsning ska ge en fråga, inte
#: en tyst felplacering (säkerhetsrundan 2026-10-16).
_MIN_AUTO_TEXT_CHARS = 12


def _auto_blocker(score: CategoryScore, rules: Rules,
                  t: Dict[str, Any], text_len: int) -> Optional[str]:
    """Varför får den här kategorin INTE sortera filen automatiskt?

    Returnerar en fråge-orsak, eller None om kategorin har tillräckliga
    bevis för att få flytta filen på egen hand. Alla spärrar som gällde
    bästa kategorin i decide() bor här, så att samma prov kan köras på
    tvåan innan lärda modellen/historiken får byta vinnare - en kategori
    som bara står som mottagare ska aldrig kunna bli auto-vinnare bakvägen
    (säkerhetsrundan 2026-10-16).
    """
    proved = score.is_conclusive

    # 1. För lite läst text - underlaget går inte att lita på
    need_chars = t["min_text_chars"]
    if need_chars and text_len < need_chars:
        return (f"Bara {text_len} tecken lästes ur filen "
                f"(kräver {need_chars})")
    if text_len < _MIN_AUTO_TEXT_CHARS and not proved:
        return (f"Bara {text_len} tecken lästes ur filen - för lite "
                f"text för att avgöra avsändare automatiskt")

    # 2. Poängen måste nå upp till tröskeln
    if score.score < t["min_score"] and not proved:
        return (f"För låg poäng: {score.name} fick {score.score:g}, "
                f"kräver {t['min_score']:g}")

    # 3. Tillräckligt många olika stödord ska ha träffat.
    # Kategorin får kräva fler stödord än nivån gör. Praktiskt när en
    # kategori har breda ord som lätt ger falska träffar: sätt 3 där, och
    # låt övriga kategorier gå på nivåns vanliga krav.
    egen = rules.get(score.name) or {}
    need_kw = max(int(t["min_keywords"]), int(egen.get("min_keywords", 0) or 0))
    if len(score.matched) < need_kw and not proved:
        vems = (" (kategorins eget krav)"
                if int(egen.get("min_keywords", 0) or 0) > int(t["min_keywords"])
                else "")
        return (f"Bara {len(score.matched)} stödord matchade {score.name}, "
                f"kräver {need_kw}{vems}")

    # 4. Alla träffar i mottagarblocket - då är vi kunden, inte de
    if t["reject_recipient_only"] and score.only_recipient:
        return (f"{score.name} står bara som mottagare i dokumentet "
                f"({', '.join(score.matched[:3])}) - filen är till dem, "
                f"inte från dem")

    # 5. Minst ett stödord på en plats som pekar ut avsändaren
    if t["require_anchor"] and not score.anchored:
        return (f"{score.name} nämns bara i löptexten - inget stödord i "
                f"brevhuvudet, filnamnet eller på en rad med org.nr")

    # 5b. Ett ensamt svagt ord mitt i brödtexten är för tunt underlag även
    # på lägre nivåer. "Vi monterade glas från Pilkington" gör inte
    # dokumentet till en Pilkington-faktura. Ett org.nr eller en domän
    # räcker däremot - sådana nämns inte i förbigående.
    if (t["reject_recipient_only"] and len(score.matched) == 1
            and not score.anchored and not score.has_strong):
        word = score.matched[0]
        return (f"\"{word}\" nämns bara i löptexten och är inget unikt "
                f"kännetecken - för tunt för att avgöra avsändare")

    # 5c. Bara löptextträffar flyttar aldrig en fil automatiskt på
    # Normal-nivån och uppåt: minst ett bevis måste sitta på avsändarens
    # plats, vara ett starkt kännetecken eller återkomma på flera sidor
    # (brevhuvud/sidfot). Två svaga ord mitt i en mening om en leverantör
    # gör inte avsändaren till leverantören (säkerhetsrundan 2026-10-16).
    if (t.get("require_anchor_or_strong", True) and not score.anchored
            and not score.has_strong and not score.multipage):
        return (f"{score.name} nämns bara i löptexten "
                f"({', '.join(score.matched[:3])}) - inget bevis på "
                f"avsändarens plats, inget org.nr/domän/bankgiro och "
                f"inget som återkommer på flera sidor")

    # 6. Minst ett starkt bevis - org.nr, VAT, bankgiro eller domän
    if t["require_strong"] and not score.has_strong:
        return (f"{score.name} matchade bara svaga ord "
                f"({', '.join(score.matched[:3])}) - kräver org.nr, "
                f"VAT, bankgiro eller domän")
    return None


def _apply_learned_ranking(scores: List[CategoryScore],
                           lm_pred: Tuple[str, float, int]) -> None:
    """Låt en säker lärd modell flytta rankningen - aldrig bevisen.

    Bonusen räknas in när kategorier jämförs (ordning och marginal) men
    inte när _auto_blocker prövar beviskraven: den läser fortfarande den
    regelbaserade poängen. Ett bevisat avsändar-ID får aldrig petas ned,
    och modellen kan inte uppfinna en kategori som reglerna inte alls
    matchade - den måste redan finnas bland träffarna.
    """
    namn, conf, _antal = lm_pred
    if conf < _LEARNED_CONF_MARGIN:
        return
    target = next((s for s in scores if s.name == namn), None)
    if target is None:
        return
    if scores[0].name != namn and scores[0].is_conclusive:
        return
    target.bonus = _LEARNED_BONUS
    scores.sort(key=lambda s: (-(s.score + s.bonus), s.name))


def decide(rules: Rules, extraction: Extraction, settings: Dict[str, Any]) -> Decision:
    """Avgör om filen kan sorteras automatiskt eller behöver frågas om.

    Sorteringen är avsiktligt försiktig: varje villkor som inte uppfylls
    skickar filen till granskning i stället för att gissa. Det är alltid
    billigare att svara på en fråga än att leta rätt på en felsorterad fil.
    """
    if extraction.error and not extraction.text:
        return Decision(extraction.path, extraction, [], "error", extraction.error)

    scores = score_text(rules, extraction.combined, extraction.path.name,
                        extraction.page_header, extraction.page_footer,
                        getattr(extraction, "token_pages", None),
                        body=extraction.text or "")
    t = effective_thresholds(settings)

    # N14: modellens syn på filen (om påslagen och tränad).
    lm_pred = None
    if settings.get("learned_matching", True):
        try:
            lm_pred = _learned().predict(
                learn_tokens(extraction.text or extraction.combined))
        except Exception:
            lm_pred = None

    if lm_pred is not None and scores:
        _apply_learned_ranking(scores, lm_pred)

    if not scores:
        # Säkerhetsrundan 2026-10-16: den lärda klassificeraren får aldrig
        # ensam flytta en fil som inga regler matchade - inte ens på Lös
        # nivå. En inlärd profil är ett stöd för ett beslut, inte ett
        # bevis; den visas som förslag i granskningsrutan i stället.
        d = Decision(extraction.path, extraction, scores, "ask",
                     "Ingen kategori matchade")
        if lm_pred is not None:
            d.learned_hint = (lm_pred[0], lm_pred[2])
        return d

    best = scores[0]
    # Jämförelserna nedan använder den effektiva poängen (regelpoäng +
    # eventuell modellbonus). Beviskraven i _auto_blocker läser däremot
    # den regelbaserade poängen, så bonusen kan aldrig sänka en tröskel.
    def _eff(s: CategoryScore) -> float:
        return s.score + s.bonus

    second = _eff(scores[1]) if len(scores) > 1 else 0.0

    def ask(reason: str) -> Decision:
        d = Decision(extraction.path, extraction, scores, "ask", reason)
        if lm_pred is not None:
            d.learned_hint = (lm_pred[0], lm_pred[2])
        return d

    # Ett bevisat avsändar-ID väger tyngre än antalet träffar. Ett
    # organisationsnummer med giltig kontrollsiffra i sidfoten, eller
    # avsändarens egen domän i brevhuvudet, identifierar företaget lika
    # säkert ensamt som tillsammans med tio vanliga ord. Räknereglerna
    # (antal stödord, poängsumma) är till för att sålla bland svaga
    # ledtrådar och ska inte hindra ett dokument som redan är bevisat.
    #
    # Tvåan måste däremot fortfarande vägas: har även den ett bevisat ID
    # står två företag mot varandra och då är frågan berättigad.
    proved = best.is_conclusive
    rival_proved = len(scores) > 1 and scores[1].is_conclusive

    # 1-6. Alla beviskrav på bästa kategorin (se _auto_blocker).
    blocker = _auto_blocker(best, rules, t, len(extraction.text))
    if blocker:
        return ask(blocker)

    # 7. Tillräcklig marginal ned till tvåan, både absolut och relativt.
    # Har bara den ena kategorin ett bevisat avsändar-ID är saken redan
    # avgjord - en konkurrent som nämns i löptexten gör inte dokumentet
    # tvetydigt, hur många gånger den än nämns.
    if len(scores) > 1 and not (proved and not rival_proved):
        nära = (_eff(best) - second < t["ambiguity_margin"]
                or (t["score_ratio"] > 1.0 and second > 0
                    and _eff(best) < second * t["score_ratio"]))
        if nära and scores[1].only_recipient:
            # 2026-10-15: en tvåa som BARA står som mottagare gör inte
            # dokumentet tvetydigt - vi är kunden hos dem, inte tvärtom.
            # Marginalen ignoreras då och bästa kategorin vinner.
            nära = False
        if nära:
            # N14: båda kandidaterna ligger nära - modellens tränade öga
            # får avgöra om den är säker på en av de två. Säkerhetsrundan
            # 2026-10-16: vinnaren måste själv klara alla beviskrav
            # (_auto_blocker) - tidigare kunde modellen lyfta en tvåa som
            # t.ex. bara stod som mottagare rakt till auto-flytt.
            if (lm_pred is not None and lm_pred[1] >= _LEARNED_CONF_MARGIN
                    and lm_pred[0] in (best.name, scores[1].name)):
                kandidat = (best if lm_pred[0] == best.name else scores[1])
                if _auto_blocker(kandidat, rules, t,
                                 len(extraction.text)) is None:
                    vinnare = lm_pred[0]
                    if vinnare != best.name:
                        scores.sort(key=lambda s2: (s2.name != vinnare,
                                                    -s2.score, s2.name))
                        best = scores[0]
                        second = _eff(scores[1])
                    d = Decision(extraction.path, extraction, scores, "auto",
                                 f"Lärd klassificerare bryter dödläget "
                                 f"({lm_pred[2]} liknande filer)")
                    return d
            # Exakt oavgjort och modellen osäker: kategorin med fler
            # tidigare sorterade filer vinner (enkel historikprior som
            # är aktiv redan från första filen, till skillnad från N14).
            # Även här gäller beviskraven för en ny vinnare (2026-10-16).
            if abs(_eff(best) - second) < 0.001:
                f1 = int((rules.get(best.name) or {}).get("files_sorted", 0) or 0)
                f2 = int((rules.get(scores[1].name) or {}).get("files_sorted", 0) or 0)
                if f1 != f2:
                    vinnare = best.name if f1 > f2 else scores[1].name
                    kandidat = (best if vinnare == best.name else scores[1])
                    if _auto_blocker(kandidat, rules, t,
                                     len(extraction.text)) is None:
                        if vinnare != best.name:
                            scores.sort(key=lambda s2: (s2.name != vinnare,
                                                        -s2.score, s2.name))
                            best = scores[0]
                            second = _eff(scores[1])
                        d = Decision(extraction.path, extraction, scores, "auto",
                                     f"Historik bryter exakt dödläge: {vinnare} "
                                     f"har {max(f1, f2)} tidigare filer mot "
                                     f"{min(f1, f2)}")
                        return d
            d = ask(f"{best.name} ({_eff(best):g}) och {scores[1].name} "
                    f"({second:g}) ligger för nära")
            d.learned_hint = (lm_pred[0], lm_pred[2]) if lm_pred else None
            return d
        ratio = t["score_ratio"]
        if ratio > 1.0 and second > 0 and _eff(best) < second * ratio:
            d = ask(f"{best.name} ({_eff(best):g}) är inte {ratio:g} gånger "
                    f"starkare än {scores[1].name} ({second:g})")
            d.learned_hint = (lm_pred[0], lm_pred[2]) if lm_pred else None
            return d

    d = Decision(extraction.path, extraction, scores, "auto", "")
    return d


# ==========================================================================
# DEL 4 - JOBBMOTOR OCH MAPPBEVAKNING
# ==========================================================================

IGNORE_PREFIX = ("~$", ".")
IGNORE_SUFFIX = (".crdownload", ".part", ".partial", ".tmp", ".filepart")


def _ignore_reason(path: Path, ext: Extraction,
                  settings: Dict[str, Any]) -> str:
    """Ignoreringsregler (ANVÄNDARORDER 2026-08-26): filer som innehåller
    vissa ord eller har vissa filnamn hopas över helt och hållet, även om
    de ligger i en skanningsmapp. Returnerar orsak eller tom sträng."""
    name = path.name.lower()
    for pat in settings.get("ignore_filename_globs", []) or []:
        if pat and fnmatch.fnmatch(name, pat.lower()):
            return f"filnamnet möter '{pat}'"
    if ext.text:
        norm = normalize(ext.text)
        for w in settings.get("ignore_words", []) or []:
            wn = normalize(w)
            if wn and wn in norm:
                return f"innehåller '{w}'"
    return ""


def _inuti(barn: Path, förälder: Path) -> bool:
    """Sant om `barn` ligger inuti `förälder` (men inte är samma mapp).

    Path.is_relative_to finns först i Python 3.9. Appen ska gå att köra
    på äldre installationer, så jämförelsen görs på parts-listan.
    """
    try:
        b, f = barn.resolve().parts, förälder.resolve().parts
    except OSError:
        return False
    return len(b) > len(f) and b[:len(f)] == f


def list_pdfs(folder: Path, recursive: bool = False,
              excludes=()) -> List[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    # Undantagsmappar (ANVÄNDARORDER 2026-08-26): hoppas över även när de
    # ligger inuti en skanningsmapp (t.ex. Arkiv/ under inmappen).
    exc = [os.path.normcase(os.path.abspath(str(e))) for e in excludes if e]

    def _excluded(p: Path) -> bool:
        pc = os.path.normcase(os.path.abspath(str(p)))
        return any(pc == e or pc.startswith(e + os.sep) for e in exc)

    if recursive:
        it = folder.rglob("*")
    else:
        # os.scandir är märkbart snabbare än glob på Windows och
        # nätverksdiskar (en systemanropssvit i stället för många stat).
        try:
            with os.scandir(folder) as sc:
                it = [Path(e.path) for e in sc]
        except OSError:
            return []
    out = []
    for p in it:
        try:
            if exc and _excluded(p):
                continue
            if not p.is_file() or p.suffix.lower() != ".pdf":
                continue
            if p.name.startswith(IGNORE_PREFIX) or p.name.lower().endswith(IGNORE_SUFFIX):
                continue
            out.append(p)
        except OSError:
            continue
    return sorted(out)


def pdf_looks_complete(path: Path) -> bool:
    """Sant om filen ser ut som en färdigskriven PDF.

    En PDF börjar med %PDF- och slutar med %%EOF. Saknas slutmarkören
    håller skannern/skrivaren troligen fortfarande på att skriva filen.
    """
    try:
        size = path.stat().st_size
        if size < 400:
            return False
        with open(path, "rb") as fh:
            if fh.read(5) != b"%PDF-":
                return False
            fh.seek(max(0, size - 2048))
            return b"%%EOF" in fh.read()
    except (OSError, PermissionError):
        return False


def is_stable(path: Path, seconds: float = 3.0, require_complete: bool = True) -> bool:
    """Sant om filen inte ändrats på `seconds`, går att öppna och är hel.

    Hindrar att appen tar tag i en PDF som skannern fortfarande skriver.
    """
    try:
        st = path.stat()
        if time.time() - st.st_mtime < seconds:
            return False
        with open(path, "rb") as fh:
            fh.read(1)
    except (OSError, PermissionError):
        return False
    if require_complete and not pdf_looks_complete(path):
        return False
    return True


class TextCache:
    """Sparar utläst PDF-text så att omskanningar går fort.

    Att läsa om ett textlager kostar några millisekunder, men att OCR:a en
    skannad sida tar över en sekund. Efter varje inlärt stödord skannas
    allt osorterat om, och utan cache betyder det att samma skannade filer
    OCR:as gång på gång: 1 000 filer tar då 25 minuter i stället för
    sekunder.

    Nyckeln är sökväg + filstorlek + ändringstid. Ändras filen på disk
    blir nyckeln en annan och texten läses om - en inaktuell text kan
    alltså aldrig användas.

    Cachen ligger bara i minnet. Den överlever inte en omstart, vilket är
    med flit: en cachefil på disk skulle behöva hanteras vid uppgradering,
    korruption och diskbrist, och vinsten uppstår ändå under en och samma
    körning.
    """

    #: Minnessnåla tak (ANVÄNDARORDER 2026-08-26: ska ej använda mycket
    #: minne). Både antal poster OCH total textmängd begränsas, så cachen
    #: kan aldrig växa obundet; äldsta posten ryker först. Den bestående
    # cachen ligger på disk (DiskTextCache) i stället för i RAM.
    MAX_ENTRIES = 800
    MAX_BYTES = 24 * 1024 * 1024   # ~24 MB text, värsta fall

    def __init__(self) -> None:
        self._data: "OrderedDict[Tuple[str, int, int], Extraction]" = OrderedDict()
        self._bytes = 0
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(path: Path) -> Optional[Tuple[str, int, int]]:
        try:
            st = path.stat()
        except OSError:
            return None
        # Ändringstiden avrundas till hel mikrosekund - olika filsystem
        # har olika upplösning och float-jämförelser blir annars ostadiga.
        return (str(path.resolve()), st.st_size, int(st.st_mtime_ns // 1000))

    def get(self, path: Path) -> Optional[Extraction]:
        key = self._key(path)
        if key is None:
            return None
        with self._lock:
            found = self._data.get(key)
            if found is not None:
                self._data.move_to_end(key)
                self.hits += 1
            else:
                self.misses += 1
            return found

    def put(self, path: Path, extraction: Extraction) -> None:
        key = self._key(path)
        if key is None:
            return
        with self._lock:
            gammal = self._data.get(key)
            if gammal is not None:
                self._bytes -= len(gammal.text)
            self._data[key] = extraction
            self._data.move_to_end(key)
            self._bytes += len(extraction.text)
            while (len(self._data) > self.MAX_ENTRIES
                   or self._bytes > self.MAX_BYTES):
                _, popped = self._data.popitem(last=False)
                self._bytes -= len(popped.text)

    def forget(self, path: Path) -> None:
        """Släng en enskild fil, t.ex. sedan den flyttats."""
        key = self._key(path)
        with self._lock:
            if key is not None:
                popped = self._data.pop(key, None)
                if popped is not None:
                    self._bytes -= len(popped.text)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._bytes = 0
            self.hits = self.misses = 0

    def stats(self) -> str:
        with self._lock:
            total = self.hits + self.misses
            andel = (self.hits / total * 100) if total else 0.0
            return (f"{len(self._data)} filer / {self._bytes // (1024 * 1024)} MB "
                    f"i minnet, {self.hits} träffar av {total} ({andel:.0f} %)")


#: Delas av alla som läser PDF - jobbmotorn, omskanningen och kön.
TEXT_CACHE = TextCache()


class DiskTextCache:
    """Bestående textcache i konfigmappen (cache/<hash>.json).

    Minnescachen töms vid varje omstart, vilket tvingar fram dyr omläsning
    och - värst av allt - dyr OCR vid första svepet. Diskcachen nycklas på
    exakt samma signatur (sökväg + storlek + mtime), så en oförändrad fil
    träffar cachen även efter omstart: andra starten blir lika snabb som
    den första, och skannade filer OCR:as aldrig två gånger.
    """

    MAX_ENTRIES = 1500

    def __init__(self) -> None:
        self.dir = config_dir() / "cache"
        self._puts = 0

    @staticmethod
    def _hash(path: Path) -> Optional[str]:
        key = TextCache._key(path)
        if key is None:
            return None
        import hashlib
        return hashlib.sha1(repr(key).encode("utf-8")).hexdigest()

    def get(self, path: Path) -> Optional[Extraction]:
        kh = self._hash(path)
        if kh is None:
            return None
        try:
            with open(self.dir / (kh + ".json"), "r", encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not d.get("text"):
            return None
        return Extraction.from_cache_dict(path, d)

    def put(self, path: Path, ext: Extraction) -> None:
        kh = self._hash(path)
        if kh is None or not ext.text:
            return
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            with open(self.dir / (kh + ".json"), "w", encoding="utf-8") as fh:
                json.dump(ext.to_cache_dict(), fh, ensure_ascii=False)
        except OSError:
            return
        # Enkel städning var hundrade skrivning: behåll de nyaste.
        self._puts += 1
        if self._puts % 100 == 0:
            try:
                filer = sorted(self.dir.glob("*.json"),
                               key=lambda p: p.stat().st_mtime)
                while len(filer) > self.MAX_ENTRIES:
                    filer.pop(0).unlink(missing_ok=True)
            except OSError:
                pass


DISK_CACHE = DiskTextCache()


def read_pdf(path: Path, settings: Dict[str, Any],
             use_cache: bool = True) -> Extraction:
    """Läs en PDF, med minnes- och diskcache. Enda stället som anropar
    extract().

    Filer som gav fel cachas inte - nästa försök ska få läsa om, t.ex.
    sedan en låst fil släppts eller Tesseract installerats.
    """
    if use_cache:
        found = TEXT_CACHE.get(path)
        if found is not None:
            return found
        found = DISK_CACHE.get(path)
        if found is not None:
            TEXT_CACHE.put(path, found)
            return found
    ext = extract(
        path,
        max_pages=int(settings.get("max_pages_text", 0)),
        ocr_enabled=bool(settings.get("ocr_enabled", True)),
        ocr_max_pages=int(settings.get("ocr_max_pages", 3)),
        ocr_language=settings.get("ocr_language", "swe+eng"),
        ocr_quality=settings.get("ocr_quality", "high"),
    )
    if use_cache and not ext.error:
        TEXT_CACHE.put(path, ext)
        DISK_CACHE.put(path, ext)
    return ext


class SortEngine:
    """Kör igenom filer, fattar beslut, flyttar. Trådsäker."""

    def __init__(self, rules: Rules, settings: Dict[str, Any],
                 log: Optional[Callable[[str, str], None]] = None,
                 conflict_asker: Optional[Callable[[Path, Path, str], str]] = None):
        self.rules = rules
        self.settings = settings
        self.log = log or (lambda msg, level="info": None)
        #: REQ-N4: anropas när en dubblett upptäcks och returnerar
        # "replace" eller "rename". None (headless) = behåll båda + logga.
        self.conflict_asker = conflict_asker
        self.lock = threading.RLock()
        self.stats = Counter()
        # Debouncad rules.save (snabbare batch, mindre I/O-hack): högst en
        # skrivning per sekund; resten sparas vid flush_rules().
        self._last_rules_save = 0.0
        self._rules_dirty = False

    def _rules_save(self) -> None:
        now = time.time()
        if now - self._last_rules_save >= 1.0:
            self.rules.save()
            self._last_rules_save = now
        else:
            self._rules_dirty = True

    def flush_rules(self) -> None:
        """Skriv reglerna om en debouncad skrivning väntar (batchslut)."""
        if self._rules_dirty:
            self.rules.save()
            self._rules_dirty = False
            self._last_rules_save = time.time()
        flush_learned()        # N14: modellen i hamn tillsammans med reglerna

    # -- analys ------------------------------------------------------------
    def analyze(self, path: Path) -> Decision:
        """Läs filen och fatta beslut.

        Texten hämtas via cachen, så en omskanning efter ett nytt stödord
        slipper läsa om - och framför allt slipper OCR:a om - filer som
        redan är lästa under samma körning.
        """
        # Individuellt ignorerad fil (markerad i granskningsrutan)?
        # Känns igen på innehållet - även omdöpt eller flyttad. Kollas
        # FÖRE läsningen så att en markerad fil aldrig OCR:as i onödan.
        try:
            if is_ignored_file(path):
                self.log(f"{path.name}  ⊘ individuellt ignorerad - känns igen",
                         "info")
                return Decision(path, Extraction(path=Path(str(path))), [],
                                "ignored",
                                "Individuellt ignorerad (känns igen på innehållet)")
        except Exception:
            pass
        with LogContext("tid", f"analys {path.name}"):
            ext = read_pdf(path, self.settings)
            # Säkerhetsrundan 2026-10-16: fingeravtryck på exakt de byte
            # som analyserades. apply() vägrar flytta filen om den hunnit
            # ändras sedan dess (skanner/synk som fortfarande skriver) -
            # beslutet gäller då inte längre den fil som ligger på disk.
            try:
                st = path.stat()
                ext._fp = (st.st_size, sha256_file(path))
            except Exception:
                ext._fp = None
            reason = _ignore_reason(path, ext, self.settings)
            if reason:
                return Decision(path, ext, [], "ignored",
                                f"Ignorerad: {reason}")
            with self.lock:
                return decide(self.rules, ext, self.settings)

    # -- verkställ ---------------------------------------------------------
    def subfolder_for(self, extraction: Extraction,
                      template: str = "") -> Tuple[str, Optional[date], str]:
        """Räkna ut undermappen för en fil.

        Returnerar (relativ sökväg, använt datum, källa). Allt tomt när
        datumsorteringen är avstängd - då beter sig appen exakt som förut.
        """
        s = self.settings
        sub, when, källa = "", None, ""
        if s.get("date_enabled", False):
            mall = template or s.get("date_default_template", "{år}")
            if mall:
                when = getattr(extraction, "doc_date", None)
                källa = getattr(extraction, "date_source", "")
                if when is None:
                    reserv = s.get("date_fallback", "none")
                    if reserv == "unknown":
                        return "Utan datum", None, "saknas"
                    if reserv == "filedate":
                        try:
                            when = date.fromtimestamp(
                                extraction.path.stat().st_mtime)
                            källa = "filens tid"
                        except OSError:
                            return "", None, ""
                    else:
                        when = None
                if when is not None:
                    sub = render_subfolder(mall, when)
        # N16 (ANVÄNDARORDER 2026-10-15): årsmapp från filens eget
        # datum, automatiskt. Året tas från det ÄLDSTA av ändrat/skapat
        # (kopian bevarar ursprungligt ändringsdatum men får nytt
        # skapelsedatum - min av dem är året användaren menar).
        if not sub and s.get("year_subfolder", True):
            try:
                st = extraction.path.stat()
                ts = min(st.st_mtime,
                         getattr(st, "st_ctime", st.st_mtime))
                when = date.fromtimestamp(ts)
                sub = str(when.year)
                källa = "fil-datum"
            except (OSError, ValueError, OverflowError):
                pass
        return sub, when, källa

    def _fil_ändrad(self, decision: Decision) -> bool:
        """Har filen på disk andra byte än den som analyserades?

        Fingeravtrycket sätts i analyze() (storlek + sha256). Saknas det
        (beslut byggda för hand) finns inget att jämföra med - då gäller
        som förut. En fil som ändrats får aldrig flyttas på ett beslut
        som fattades om en annan fil (säkerhetsrundan 2026-10-16).
        """
        fp = getattr(decision.extraction, "_fp", None)
        if not fp:
            return False
        try:
            st = decision.path.stat()
            if st.st_size != fp[0]:
                return True
            return sha256_file(decision.path) != fp[1]
        except OSError:
            return True

    def apply(self, decision: Decision, category: str, matched: List[str],
              decided_by: str = "auto", learned: Optional[List[str]] = None) -> Tuple[bool, str]:
        # Hela verkställandet serialiseras: parallella sorteringstrådar får
        # aldrig tävla om målnamn (REQ-D2 - filer skrivs aldrig över).
        s = self.settings
        with self.lock:
            if not s.get("dry_run", False) and self._fil_ändrad(decision):
                self.stats["left"] += 1
                return False, ("Filen ändrades efter analysen - lämnas "
                               "kvar för ny skanning i stället för att "
                               "flyttas på ett inaktuellt beslut")
            cat = self.rules.get(category) or self.rules.ensure_category(category)
            folder = cat["folder"]
            mall = cat.get("subfolder", "")
            sub, when, källa = self.subfolder_for(decision.extraction, mall)

            # -- REQ-N4: dubblettkontroll innan något rör disken --
            on_conflict = s.get("on_conflict", "rename")
            conflict = ""
            same_content_file: Optional[Path] = None
            if not s.get("dry_run", False):
                dest_dir = Path(s["output_dir"]) / safe_folder_name(folder)
                if sub:
                    for nivå in sub.split("/"):
                        if nivå.strip():
                            dest_dir = dest_dir / safe_folder_name(nivå)
                namnkrock = dest_dir / decision.path.name
                if namnkrock.exists():
                    conflict = "name"
                elif decision.path.exists() and dest_dir.is_dir():
                    # Innehållsdubblett med annat namn: samma storlek är
                    # förfiltret, hashen är beviset.
                    try:
                        src_st = decision.path.stat()
                        src_sha = sha256_file(decision.path)
                        for cand in dest_dir.iterdir():
                            try:
                                if (cand.is_file()
                                        and cand.stat().st_size == src_st.st_size
                                        and sha256_file(cand) == src_sha):
                                    same_content_file = cand
                                    conflict = "content"
                                    break
                            except OSError:
                                continue
                    except OSError:
                        pass
                if conflict:
                    if self.conflict_asker is not None:
                        svar = self.conflict_asker(decision.path, namnkrock, conflict)
                    else:
                        svar = "rename"
                        self.log(f"Dubblett upptäckt ({conflict}) - "
                                 f"behåller båda: {decision.path.name}", "warn")
                    if svar == "skip":
                        self.stats["left"] += 1
                        return False, "Överhoppad - dubblettfrågan avbröts"
                    if svar == "replace":
                        on_conflict = "overwrite"
                        if conflict == "content" and same_content_file is not None:
                            try:
                                same_content_file.unlink()
                            except OSError:
                                on_conflict = "rename"
                    else:
                        on_conflict = "rename"

            ok, msg, target = place_file(
                decision.path, Path(s["output_dir"]), folder,
                action=s.get("action", "move"),
                on_conflict=on_conflict,
                dry_run=bool(s.get("dry_run", False)),
                subfolder=sub,
            )
            if not ok:
                self.stats["error"] += 1
                return False, msg
            if not s.get("dry_run", False) and s.get("tag_pdf_metadata", True):
                try:
                    tag_pdf_metadata(Path(target), category)
                except Exception:
                    pass
            # Filen ligger inte kvar på sin gamla plats - släpp den ur cachen
            # så att minnet inte fylls av poster som aldrig kan träffa igen.
            TEXT_CACHE.forget(decision.path)

            if not s.get("dry_run", False):
                self.rules.register_hit(category, matched)
                best = decision.best
                # Negativ inlärning (2026-10-20): rättade användaren en
                # automatisk gissning ska den felaktiga kategorin lära sig
                # av misstaget - dess stödord väger mindre nästa gång och
                # den lärda modellen får negativa bevis. Utan detta blev
                # bara det rätta valet starkare och samma ord kunde leda
                # fel om och om igen.
                wrong = ""
                if (decided_by == "user" and best is not None
                        and best.name != category):
                    wrong = best.name
                    self.rules.register_reject(wrong, best.matched)
                self._rules_save()
                # N14: varje beslut blir träningsdata (AC-14.4) - även
                # användarens korrigeringar, eftersom kategorin här är
                # det slutgiltiga valet.
                toks = learn_tokens(decision.extraction.text
                                    or decision.extraction.combined)
                if s.get("learned_matching", True):
                    try:
                        _learned().train(category, toks,
                                         rejected_for=wrong or None)
                    except Exception:
                        pass
                append_history({
                    "tokens": toks,
                    "time": now_iso(),
                    "action": s.get("action", "move"),
                    "source": str(decision.path),
                    "target": str(target),
                    "category": category,
                    "score": best.score if best else 0.0,
                    "runner_up": ({"category": decision.runner_up.name,
                                   "score": decision.runner_up.score}
                                  if decision.runner_up else None),
                    "matched": matched,
                    "used_ocr": decision.extraction.used_ocr,
                    "decided_by": decided_by,
                    "corrected_from": wrong or None,
                    "learned": learned or [],
                    "date": when.isoformat() if when else None,
                    "date_source": källa,
                    "subfolder": sub,
                    "conflict": conflict or None,
                })
            self.stats["sorted"] += 1
            return True, str(target)

    def send_to_unmatched(self, decision: Decision) -> Tuple[bool, str]:
        """Flytta till _Osorterat om en sådan mapp är konfigurerad."""
        with self.lock:
            if (not self.settings.get("dry_run", False)
                    and self._fil_ändrad(decision)):
                self.stats["left"] += 1
                return False, ("Filen ändrades efter analysen - lämnas "
                               "kvar för ny skanning")
            folder = (self.settings.get("unmatched_folder") or "").strip()
            if not folder:
                self.stats["left"] += 1
                return False, "Lämnad i inmappen"
            ok, msg, target = place_file(
                decision.path, Path(self.settings["output_dir"]), folder,
                action=self.settings.get("action", "move"),
                on_conflict=self.settings.get("on_conflict", "rename"),
                dry_run=bool(self.settings.get("dry_run", False)),
            )
            if ok and not self.settings.get("dry_run", False):
                append_history({
                    "time": now_iso(),
                    "action": self.settings.get("action", "move"),
                    "source": str(decision.path),
                    "target": str(target),
                    "category": folder,
                    "score": 0.0,
                    "matched": [],
                    "used_ocr": decision.extraction.used_ocr,
                    "decided_by": "unmatched",
                    "learned": [],
                })
            self.stats["unmatched"] += 1
            return ok, msg

    def learn(self, category: str, words: List[str], folder: Optional[str] = None) -> None:
        """Spara användarens valda stödord som permanenta regler."""
        with self.lock:
            self.rules.ensure_category(category, folder)
            if words:
                self.rules.add_keywords(category, words, weight=1.0, source="dialog")
            self.rules.save()
            _PATTERN_CACHE.clear()


class FolderWatcher:
    """Bevakar en mapp med polling. Fungerar likadant på alla OS och
    på nätverksenheter där händelsebaserad bevakning ofta missar filer."""

    def __init__(self, folder: Path, on_file: Callable[[Path], None],
                 interval: float = 5.0, stable_seconds: float = 3.0,
                 recursive: bool = False, excludes=()):
        self.folder = Path(folder)
        self.on_file = on_file
        self.interval = max(1.0, float(interval))
        self.stable_seconds = float(stable_seconds)
        self.recursive = recursive
        self.excludes = tuple(excludes)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._seen: Dict[str, Tuple[int, float]] = {}
        self._waiting: Counter = Counter()   # filer som ännu inte är hela
        self._dir_sig: Optional[Tuple[int, int]] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="pdfsorter-watch")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2.0)
        self._thread = None

    def forget(self, path: Path) -> None:
        self._seen.pop(str(path), None)
        self._waiting.pop(str(path), None)

    def _loop(self) -> None:
        while not self._stop.is_set():
            # Snabbväg (snabbare): oförändrad mapp (icke-rekursivt) och inga
            # halvfärdiga filer som väntar -> hoppa över glob denna rond.
            # Nya filer ändrar mappens mtime, så inget kan missas.
            try:
                if not self.recursive and not self._waiting:
                    st_d = self.folder.stat()
                    sig = (st_d.st_mtime_ns, st_d.st_size)
                    if sig == self._dir_sig:
                        self._stop.wait(self.interval)
                        continue
                    self._dir_sig = sig
            except OSError:
                pass
            try:
                for pdf in list_pdfs(self.folder, self.recursive, self.excludes):
                    if self._stop.is_set():
                        break
                    try:
                        st = pdf.stat()
                    except OSError:
                        continue
                    sig = (st.st_size, st.st_mtime)
                    if self._seen.get(str(pdf)) == sig:
                        continue
                    key = str(pdf)
                    if not is_stable(pdf, self.stable_seconds):
                        # Skrivs fortfarande, eller saknar %%EOF. Vänta.
                        # Efter 10 svep behandlas den ändå (trasig men stilla fil),
                        # annars skulle den ligga kvar och kontrolleras för alltid.
                        self._waiting[key] += 1
                        if self._waiting[key] < 10 or not is_stable(
                                pdf, self.stable_seconds, require_complete=False):
                            continue
                    self._waiting.pop(key, None)
                    self._seen[key] = sig
                    try:
                        self.on_file(pdf)
                    except Exception:
                        pass
            except Exception:
                pass
            self._stop.wait(self.interval)


class MultiFolderWatcher:
    """Bevakar flera mappar samtidigt.

    Varje mapp får en egen FolderWatcher, så en otillgänglig nätverksmapp
    aldrig blockerar de andra. Utåt beter den sig som en enda bevakare.
    """

    def __init__(self, folders: List[Path], on_file: Callable[[Path], None],
                 interval: float = 5.0, stable_seconds: float = 3.0,
                 recursive: bool = False, excludes=()):
        self.folders = [Path(f) for f in folders]
        self.watchers = [
            FolderWatcher(f, on_file, interval, stable_seconds, recursive,
                          excludes)
            for f in self.folders
        ]

    @property
    def running(self) -> bool:
        return any(w.running for w in self.watchers)

    def start(self) -> None:
        for w in self.watchers:
            w.start()

    def stop(self) -> None:
        for w in self.watchers:
            w.stop()

    def forget(self, path: Path) -> None:
        for w in self.watchers:
            w.forget(path)


def undo_event(event: Dict[str, Any]) -> Tuple[bool, str]:
    """Flytta tillbaka en fil till sin ursprungliga plats."""
    src = Path(event.get("target", ""))
    dst = Path(event.get("source", ""))
    if not src.exists():
        return False, "Filen finns inte kvar på målplatsen"
    if event.get("action") == "copy":
        try:
            src.unlink()
            return True, "Kopian togs bort"
        except OSError as exc:
            return False, str(exc)
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        final = unique_target(dst)
        shutil.move(str(src), str(final))
        return True, str(final)
    except OSError as exc:
        return False, str(exc)


# ==========================================================================
# SYSTEMINTEGRATION - ikon, autostart, systemfält och hjälptext
# ==========================================================================
#
# Ligger i pdfsorter_system.py bredvid den här filen. Saknas den fungerar
# appen ändå: sorteringen är kärnan, ikonen och systemfältet är extra.
# Ersättarna nedan gör att koden kan anropa samma namn oavsett.

try:
    import pdfsorter_system as _sys_mod

    _sys_mod.configure(
        config_dir=config_dir,
        now_iso=now_iso,
        main_script=Path(__file__).resolve(),
        app_name=APP_NAME,
        app_version=APP_VERSION,
    )

    make_icon_image = _sys_mod.make_icon_image
    icon_photoimage = _sys_mod.icon_photoimage
    write_icon_file = _sys_mod.write_icon_file
    ensure_icon_file = _sys_mod.ensure_icon_file
    brand_window = _sys_mod.brand_window
    set_app_user_model_id = _sys_mod.set_app_user_model_id
    autostart_supported = _sys_mod.autostart_supported
    autostart_enabled = _sys_mod.autostart_enabled
    autostart_session_available = _sys_mod.autostart_session_available
    set_autostart = _sys_mod.set_autostart
    sync_autostart = _sys_mod.sync_autostart
    effective_autostart = _sys_mod.effective_autostart
    create_desktop_shortcut = _sys_mod.create_desktop_shortcut
    install_helpers = _sys_mod.install_helpers
    tray_available = _sys_mod.tray_available
    tray_backend_name = _sys_mod.tray_backend_name
    tray_hidden_start_safe = _sys_mod.tray_hidden_start_safe
    TrayIcon = _sys_mod.TrayIcon
    HELP_CONTENT = _sys_mod.HELP_CONTENT
    help_as_text = _sys_mod.help_as_text
    _crash_report = _sys_mod.crash_report
    start_session = _sys_mod.start_session
    session_log = _sys_mod.session_log
    session_error = _sys_mod.session_error
    session_path = _sys_mod.session_path
    session_dir = _sys_mod.session_dir
    latest_session_log = _sys_mod.latest_session_log
    install_excepthooks = _sys_mod.install_excepthooks
    close_session = _sys_mod.close_session
    set_process_dpi_aware = _sys_mod.set_process_dpi_aware
    qr_png_bytes = _sys_mod.qr_png_bytes
    swish_payload = _sys_mod.swish_payload
    auto_install_tesseract = _sys_mod.auto_install_tesseract
    search_tesseract = _sys_mod.search_tesseract
    check_for_update = _sys_mod.check_for_update
    perform_update = _sys_mod.perform_update
    update_python_packages = _sys_mod.update_python_packages
    autostart_status = _sys_mod.autostart_status
    tag_pdf_metadata = _sys_mod.tag_pdf_metadata
    export_year_archive = _sys_mod.export_year_archive
    lookup_company_name_online = _sys_mod.lookup_company_name_online
    svenska_saknas = _sys_mod.svenska_saknas
    classify_autostart = _sys_mod.classify_autostart
    get_autostart_conflicts = _sys_mod.get_autostart_conflicts
    LogContext = _sys_mod.LogContext
    SYSTEM_MODULE = True

except Exception as _sys_err:                       # noqa: BLE001
    SYSTEM_MODULE = False
    _SYS_MISSING = str(_sys_err)

    def _noop_icon(*_a, **_k):
        return None

    make_icon_image = icon_photoimage = _noop_icon
    write_icon_file = ensure_icon_file = _noop_icon
    brand_window = _noop_icon

    def set_app_user_model_id(*_a, **_k) -> None:
        return None

    def autostart_supported() -> bool:
        return False

    def autostart_enabled() -> bool:
        return False

    def autostart_session_available() -> bool:
        return True

    def set_autostart(enabled: bool) -> Tuple[bool, str]:
        return False, "pdfsorter_system.py saknas - autostart går inte att ställa in"

    def sync_autostart(want: bool) -> Tuple[bool, str]:
        return False, "pdfsorter_system.py saknas - autostart går inte att ställa in"

    def effective_autostart(_settings: dict) -> Tuple[bool, bool]:
        return False, False

    def create_desktop_shortcut() -> Tuple[bool, str]:
        return False, "pdfsorter_system.py saknas - kan inte skapa genväg"

    def check_for_update(timeout: int = 15) -> dict:
        return {"ok": False, "current": APP_VERSION, "remote": None,
                "available": False, "error": "pdfsorter_system.py saknas"}

    def perform_update(timeout: int = 180, root=None) -> Tuple[bool, str]:
        return False, "pdfsorter_system.py saknas - kan inte uppdatera"

    def update_python_packages(root=None, timeout: int = 1800) -> Tuple[bool, str]:
        return False, "pdfsorter_system.py saknas - kan inte uppdatera paket"

    def search_tesseract():
        return None

    def tag_pdf_metadata(path, category, sender="") -> bool:
        return False

    def export_year_archive(output_root, dest_dir, log=lambda m: None) -> dict:
        return {"mapp": "", "filer": 0, "fel": 1}

    def lookup_company_name_online(orgnr, timeout=6.0):
        return None

    def autostart_status() -> dict:
        return {"platform": sys.platform, "supported": False,
                "enabled": False, "klass": "missing", "entry": ""}

    def install_helpers() -> List[str]:
        return []

    def tray_available() -> bool:
        return False

    def tray_backend_name() -> str:
        return ""

    def tray_hidden_start_safe() -> Tuple[bool, str]:
        return False, "pdfsorter_system.py saknas"

    TrayIcon = None                                  # type: ignore[assignment]

    HELP_CONTENT: List[Tuple[str, str]] = [
        ("h1", "Hjälpen kunde inte laddas"),
        ("body", "Filen pdfsorter_system.py hittades inte bredvid "
                 "pdfsorter.py. Sorteringen fungerar precis som vanligt, men "
                 "ikonen i systemfältet, autostart och den här hjälptexten "
                 "kräver den filen."),
        ("body", f"Felmeddelande: {_SYS_MISSING}"),
    ]

    def help_as_text() -> str:
        return "\n".join(t for _, t in HELP_CONTENT)

    def _crash_report(exc: BaseException) -> None:
        import traceback
        traceback.print_exception(type(exc), exc, exc.__traceback__)

    # Sessionsloggens reservvägar: utan systemmodul loggas inget till fil,
    # men anropen måste fungera ändå (REQ-A2 - appen går alltid att köra).
    def start_session(banner_lines=None):
        return None

    def session_log(category: str, message: str, level: str = "info") -> None:
        return None

    def session_error(category: str, exc: BaseException) -> None:
        return None

    def session_path():
        return None

    def session_dir():
        return None

    def latest_session_log():
        return None

    def install_excepthooks() -> None:
        return None

    def close_session() -> None:
        return None

    def set_process_dpi_aware() -> None:
        return None

    def qr_png_bytes(text, scale=8, border=4):
        return b""

    def swish_payload(number, amount=None):
        return ""

    def auto_install_tesseract() -> Tuple[bool, str]:
        return False, "pdfsorter_system.py saknas"

    def svenska_saknas() -> bool:
        return False

    def classify_autostart() -> str:
        return "missing" if not autostart_enabled() else "correct"

    def get_autostart_conflicts():
        return []

    class LogContext:
        def __init__(self, category: str, label: str):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False


# ==========================================================================
# UTSEENDE - färger, typsnitt och ttk-stilar
# ==========================================================================
#
# Ligger i pdfsorter_theme.py bredvid den här filen. Saknas den startar
# appen ändå, med Tkinters gråa standardutseende - utseendet är trevligt
# att ha, men ingenting som sorteringen behöver.

try:
    from pdfsorter_theme import COLORS, Theme, dark_titlebar
    THEME_MODULE = True
except ImportError as _theme_err:   # noqa: F401
    THEME_MODULE = False
    _THEME_MISSING = str(_theme_err)

    #: Minsta möjliga palett så att self.C[...] fungerar ändå.
    COLORS: Dict[str, str] = {
        "bg": "#f0f0f0", "surface": "#ffffff", "surface_alt": "#f6f6f6",
        "surface_sunk": "#e4e4e4", "border": "#cccccc",
        "border_strong": "#aaaaaa", "text": "#000000",
        "text_muted": "#555555", "text_faint": "#888888",
        "text_invert": "#ffffff", "accent": "#0a5ac8",
        "accent_dark": "#083f8c", "accent_light": "#dce8fa",
        "accent_hair": "#c9dcf8", "ok": "#1a7f37", "ok_light": "#e6f5ec",
        "warn": "#8a5a00", "warn_light": "#fdf3e0", "err": "#b42318",
        "err_light": "#fdeceb", "header_bg": "#e8e8e8", "shadow": "#d0d0d0",
    }

    #: Mörk minimipalett med samma nycklar, så att mörkt läge fungerar
    #: även när temamodulen saknas (REQ-A2).
    _FALLBACK_DARK: Dict[str, str] = {
        "bg": "#171b21", "surface": "#20262e", "surface_alt": "#252c35",
        "surface_sunk": "#12161b", "border": "#323b47",
        "border_strong": "#48525f", "text": "#e8ecf1",
        "text_muted": "#9aa7b6", "text_faint": "#68737f",
        "text_invert": "#ffffff", "accent": "#4d8fe8",
        "accent_dark": "#82b3f2", "accent_light": "#24344d",
        "accent_hair": "#2c3f5e", "ok": "#4cc38a", "ok_light": "#1d332a",
        "warn": "#e0a63f", "warn_light": "#3a2f1a", "err": "#e5726a",
        "err_light": "#3b2220", "header_bg": "#1b2128", "shadow": "#0d1014",
    }

    class Theme:                       # type: ignore[no-redef]
        """Reservtema som inte färgsätter något.

        Appen ska gå att köra även om utseendemodulen råkat bli kvar på
        en annan dator. Allt som GUI-koden anropar finns här, men gör
        ingenting utöver det nödvändigaste.
        """

        PAD, GAP, INNER = 12, 8, 10

        def __init__(self, root, ttk, dark: bool = False):
            self.root, self.ttk = root, ttk
            self.dark = dark
            self.c = _FALLBACK_DARK if dark else COLORS
            self.style = ttk.Style(root)
            self.f_base = ("TkDefaultFont", 10)
            self.f_small = self.f_tiny = ("TkDefaultFont", 9)
            self.f_bold = ("TkDefaultFont", 10, "bold")
            self.f_head = ("TkDefaultFont", 12, "bold")
            self.f_title = ("TkDefaultFont", 14, "bold")
            self.f_huge = ("TkDefaultFont", 20, "bold")
            self.f_mono = ("TkFixedFont", 9)
            self.f_mono_bold = ("TkFixedFont", 9, "bold")
            # Registrera stilnamnen tomma, annars kraschar widgetarna
            for name in ("Card.TFrame", "CardInner.TFrame", "Shadow.TFrame",
                         "Sunk.TFrame", "Status.TFrame"):
                self.style.configure(name)
            for name in ("Card.TLabel", "CardMuted.TLabel", "CardHead.TLabel",
                         "CardTitle.TLabel", "CardKey.TLabel", "Muted.TLabel",
                         "Faint.TLabel", "Title.TLabel", "Head.TLabel",
                         "Huge.TLabel", "Section.TLabel", "Ok.TLabel",
                         "Warn.TLabel", "Err.TLabel", "Status.TLabel",
                         "PillMuted.TLabel"):
                self.style.configure(name)
            for name in ("Accent.TButton", "Danger.TButton", "Link.TButton",
                         "CardLink.TButton"):
                self.style.configure(name)
            for name in ("Card.TCheckbutton", "Card.TRadiobutton"):
                self.style.configure(name)

        def card(self, parent, title: str = "", subtitle: str = "", **kw):
            frame = self.ttk.LabelFrame(parent, text=f"  {title}  ", **kw)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)
            frame.body = frame            # type: ignore[attr-defined]
            return frame

        def zebra(self, tree) -> None:
            pass

        def fit_columns(self, tree, spec) -> None:
            for col, txt, sample, anchor, stretch in spec:
                tree.heading(col, text=txt)
                tree.column(col, width=max(len(txt) * 9 + 34, sample * 9),
                            anchor=anchor, stretch=stretch)


# ==========================================================================
# VERSIONSSAMSTÄMMIGHET - upptäck blandade filkopior
# ==========================================================================
#
# Fem filer som levereras tillsammans ska ha samma version. Blandas en ny
# huvudfil med en gammal läsmodul (som hände 2026-08-26) ska appen dels
# klara sig, dels tydligt tala om att filerna behöver uppdateras.

def _module_versions() -> Dict[str, str]:
    v = {"main": APP_VERSION}
    for kort in ("read", "data", "system", "theme"):
        mod = sys.modules.get(f"pdfsorter_{kort}")
        v[kort] = (getattr(mod, "VERSION", getattr(mod, "APP_VERSION", "?"))
                   if mod else "saknas")
    return v


VERSIONS_BLANDADE = len(set(_module_versions().values())) > 1


# ==========================================================================
# DEL 5 - GRAFISKT GRÄNSSNITT (Tkinter)
# ==========================================================================

def _tk():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, simpledialog
    return tk, ttk, filedialog, messagebox, simpledialog


TESSERACT_URL = "https://ub-mannheim.github.io/tesseract/"


def missing_extensions() -> List[Dict[str, str]]:
    """Saknade valfria tillägg + vad de ger (ANVÄNDARORDER 2026-09-28:
    erbjud installation vid start). Returnerar lista med dict:
    nyckel, namn, beskrivning, slag ("pip" | "tesseract")."""
    st = backend_status()
    ut: List[Dict[str, str]] = []
    if not st["pytesseract"]:
        ut.append({"nyckel": "pytesseract", "slag": "pip",
                   "namn": "pytesseract (Python-paket)",
                   "beskr": "kopplar appen till Tesseract-motorn"})
    if not st["pymupdf"]:
        ut.append({"nyckel": "pymupdf", "slag": "pip",
                   "namn": "PyMuPDF (Python-paket)",
                   "beskr": "snabbaste och bästa textläsningen"})
    if not st["tesseract"]:
        ut.append({"nyckel": "tesseract", "slag": "tesseract",
                   "namn": "Tesseract OCR (program)",
                   "beskr": "läser SKANNADE PDF:er (bilder utan textlager)"})
    elif svenska_saknas():
        ut.append({"nyckel": "swe", "slag": "sprak",
                   "namn": "Svenskt språkpaket till Tesseract",
                   "beskr": "mycket bättre avläsning av svenska skanningar"})
    if not st["pdftoppm"] and not st["pymupdf"]:
        ut.append({"nyckel": "pdftoppm", "slag": "tesseract",
                   "namn": "pdftoppm (poppler-utils)",
                   "beskr": "reservmotor för att rita sidor till OCR"})
    if not tray_available():
        ut.append({"nyckel": "pystray", "slag": "pip",
                   "namn": "pystray (Python-paket)",
                   "beskr": "ikon i systemfältet"})
    return ut


def open_externally(path: Path) -> None:
    """Öppna filen/mappen i systemets standardprogram (alla OS).

    Linux: pröva xdg-open och sedan gio - minimala distributioner kan
    sakna det ena. Misslyckas allt loggas det i stället för att sväljas
    tyst (felsökningsdesign).
    """
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))                      # type: ignore[attr-defined]
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
            return
        for cmd in (["xdg-open", str(path)], ["gio", "open", str(path)]):
            try:
                subprocess.Popen(cmd)
                return
            except (FileNotFoundError, OSError):
                continue
        session_log("ui", f"Kunde inte öppna {path} - inget "
                    "öppningsprogram hittades (xdg-open/gio)", "warn")
    except Exception as exc:
        session_error("ui", exc)


def human_size(n: float) -> str:
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def _fit_geometry(win, want_w: int, want_h: int, min_w: int, min_h: int) -> None:
    """Anpassa fönstret till skärmstorleken (ANVÄNDARORDER 2026-08-26).

    Fönstret blir aldrig större än skärmen, centreras, och minsta storlek
    krymps på små skärmar så att inget fönster blir oåtkomligt. På en stor
    skärm får fönstret sin tänkta storlek; på en liten anpassas den nedåt.
    """
    try:
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
    except Exception:
        sw, sh = want_w + 240, want_h + 240
    w = min(want_w, sw - 120)
    h = min(want_h, sh - 100)
    w = max(w, min(min_w, sw - 20), 640)
    h = max(h, min(min_h, sh - 20), 480)
    win.minsize(min(min_w, sw - 20), min(min_h, sh - 20))
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")
    session_log("fönster", f"Geometri: skärm {sw}x{sh}, fönster {w}x{h}+{x}+{y} "
                f"(önskat {want_w}x{want_h}, min {min_w}x{min_h})")


# --------------------------------------------------------------------------
# Granskningsdialogen - kärnan: 10 stödord att bocka i
# --------------------------------------------------------------------------

#: Widgetklasser som är inmatningsfält: mushjulet får aldrig ändra deras
#: värde i granskningsdialogen (ANVÄNDARORDER 2026-08-26).
_FIELD_CLASSES = {"TCombobox", "TSpinbox", "TEntry", "Entry",
                  "Spinbox", "Text"}


def _dialog_wheel(inner_canvas, outer_canvas, is_inner, event):
    """Mushjul i granskningsdialogen (ANVÄNDARORDER 2026-08-26):

    * över inmatningsfält (rullgardin/spinn/entry/text): "break" utan
      någon rullning - hjulet får aldrig ändra ett fältvärde;
    * över stödordslistan: rullar listan;
    * överallt annars i fönstret: rullar hela fönstret (yttre canvas).
    """
    try:
        cls = event.widget.winfo_class()
    except Exception:
        cls = ""
    if cls in _FIELD_CLASSES:
        return "break"
    delta = -1 * (event.delta // 120) if event.delta else (
        1 if getattr(event, "num", 4) == 5 else -1)
    try:
        if is_inner(event.widget):
            inner_canvas.yview_scroll(delta, "units")
        elif outer_canvas is not None:
            outer_canvas.yview_scroll(delta, "units")
        else:
            inner_canvas.yview_scroll(delta, "units")
    except Exception:
        pass
    return "break"


class ReviewDialog:
    """Visar 10 föreslagna stödord för en osäker fil.

    Resultat i self.result:
        None                                   - avbrutet/hoppa över
        {"category":..., "words":[...],
         "save_rule":bool, "folder":..., "unmatched":bool}
    """

    def __init__(self, parent, decision: Decision, rules: Rules,
                 candidates: List[Candidate], index: int = 1, total: int = 1,
                 theme=None, preview: bool = False,
                 suggested_sender: str = ""):
        tk, ttk, filedialog, messagebox, simpledialog = _tk()
        self.tk, self.ttk, self.messagebox = tk, ttk, messagebox
        self.theme = theme
        self.C = theme.c if theme else COLORS
        self.decision = decision
        self.rules = rules
        self.candidates = candidates
        self.result: Optional[Dict[str, Any]] = None

        self.win = tk.Toplevel(parent)
        self.win.configure(background=self.C["bg"])
        self.win.after(80, lambda: dark_titlebar(
            self.win, bool(getattr(self.theme, "dark", False))))
        self.win.title(f"Osäker fil — {index} av {total}")
        self.win.transient(parent)
        _fit_geometry(self.win, 1000, 940, 860, 760)
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(0, weight=1)

        # -- hela fönstret rullbart (yttre canvas) -------------------------
        # Innehållet ovanför knappraden läggs i en yttre rullyta, så att
        # mushjulet kan rulla hela fönstret även när innehållet är högre
        # än skärmen. Stödordslistan behåller sin egen inre rullning.
        self._outer = tk.Canvas(self.win, highlightthickness=0, borderwidth=0,
                                background=self.C["bg"])
        self._outer_sb = ttk.Scrollbar(self.win, orient="vertical",
                                       command=self._outer.yview)
        self._outer.configure(yscrollcommand=self._outer_sb.set)
        self._outer_sb.grid(row=0, column=1, sticky="ns")
        self._outer.grid(row=0, column=0, sticky="nsew")
        self._all = ttk.Frame(self._outer, style="TFrame")
        self._all.columnconfigure(0, weight=1)
        self._all_id = self._outer.create_window((0, 0), window=self._all,
                                                 anchor="nw")
        self._all.bind("<Configure>",
                       lambda e: self._outer.configure(
                           scrollregion=self._outer.bbox("all")))
        self._outer.bind("<Configure>",
                         lambda e: self._outer.itemconfigure(
                             self._all_id, width=e.width))

        pad = dict(padx=14, pady=(10, 0))
        ext = decision.extraction

        # -- filinfo -------------------------------------------------------
        head = ttk.Frame(self._all, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew", **pad)
        head.columnconfigure(0, weight=1)

        ttk.Label(head, text=decision.path.name, style="CardTitle.TLabel"
                  ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 0))
        try:
            size = human_size(decision.path.stat().st_size)
        except OSError:
            size = "?"
        info = f"{size}"
        if ext.page_count:
            info += f"  ·  {ext.page_count} sidor"
        if ext.used_ocr:
            info += "  ·  läst via OCR"
        elif getattr(ext, "ocr_logo", False):
            info += "  ·  textlager + OCR av logotypen"
        else:
            info += "  ·  textlager"
        ttk.Label(head, text=info, style="CardMuted.TLabel").grid(
            row=1, column=0, sticky="w", padx=16)

        best, second = decision.best, decision.runner_up
        if best:
            guess = f"Appens gissning: {best.name} ({best.score:g} poäng)"
            hint = getattr(decision, "learned_hint", None)
            if hint:
                guess += f"   ·   lärd: {hint[0]} ({hint[1]} liknande filer)"
            if second:
                guess += f"   ·   tvåa: {second.name} ({second.score:g})"
        else:
            hint = getattr(decision, "learned_hint", None)
            if hint:
                guess = (f"Ingen kategori matchade - lärd klassificerare "
                         f"föreslår: {hint[0]} ({hint[1]} liknande filer)")
            else:
                guess = "Ingen kategori matchade den här filen"
        ttk.Label(head, text=guess, style="Card.TLabel",
                  foreground=self.C["warn"]
                  ).grid(row=2, column=0, sticky="w", padx=16, pady=(10, 0))

        # Var i dokumentet träffarna låg - förklarar ofta tveksamheten
        if best and best.matched:
            var_txt = ", ".join(
                f"{w} {ZONE_LABELS.get(best.zone_of(w), '')}"
                for w in best.matched[:3])
            ttk.Label(head, text=f"Träffar: {var_txt}", style="CardMuted.TLabel"
                      ).grid(row=4, column=0, sticky="w", padx=16, pady=(2, 14))
        if decision.reason and best:
            ttk.Label(head, text="→ " + decision.reason,
                      style="CardMuted.TLabel").grid(row=3, column=0,
                                                     sticky="w", padx=16)

        ttk.Separator(self._all).grid(row=1, column=0, sticky="ew", padx=14, pady=(10, 0))

        # -- förhandsvisning (REQ-N7, FRAMSKJUTEN) ---------------------------
        # Koden finns kvar men är AVSTÄNGD som standard tills beställaren
        # säger till (settings["preview_in_dialog"]).
        row_box = 2
        if preview:
            prev = ttk.Frame(self._all, style="Card.TFrame")
            prev.grid(row=2, column=0, sticky="ew", padx=14, pady=(10, 0))
            prev.columnconfigure(0, weight=1)
            prev.rowconfigure(1, weight=1)
            self._prev_status = ttk.Label(prev, text="Läser in förhandsvisning…",
                                          style="CardMuted.TLabel")
            self._prev_status.grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))
            self._prev_img = tk.Label(prev, background=self.C["surface_sunk"],
                                      anchor="nw")
            self._prev_img.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)
            nav = ttk.Frame(prev, style="CardInner.TFrame")
            nav.grid(row=1, column=1, sticky="ns", padx=(0, 8), pady=8)
            self._prev_pil: List[Any] = []
            self._prev_pages: List[Any] = []
            self._prev_page = 0
            ttk.Button(nav, text="‹", width=3,
                       command=lambda: self._prev_show(self._prev_page - 1)).pack(pady=2)
            self._prev_info = ttk.Label(nav, text="–", style="CardMuted.TLabel")
            self._prev_info.pack(pady=2)
            ttk.Button(nav, text="›", width=3,
                       command=lambda: self._prev_show(self._prev_page + 1)).pack(pady=2)
            self._start_preview_load()
            row_box = 3

        # -- stödordslistan ------------------------------------------------
        box = ttk.LabelFrame(self._all,
                             text="  Välj de stödord som hör till rätt kategori  ")
        box.grid(row=row_box, column=0, sticky="nsew", padx=14, pady=(12, 0))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)

        # Fast höjd på inre listan: den rullar själv, medan resten av
        # fönstret rullas av den yttre canvasen.
        canvas = tk.Canvas(box, height=300, highlightthickness=0, borderwidth=0,
                           background=self.C["surface"])
        scroll = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        self._canvas_scroll = scroll
        self.inner = ttk.Frame(canvas, style="CardInner.TFrame")
        self.inner.bind("<Configure>",
                        lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win_id = canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        scroll.grid(row=0, column=1, sticky="ns", pady=6)

        def _in_inner(w) -> bool:
            """Pekar händelsen inuti stödordslistan (canvas + dess barn)?"""
            while w is not None:
                if w is canvas or w is self._canvas_scroll:
                    return True
                w = getattr(w, "master", None)
            return False

        def _wheel(event):
            return _dialog_wheel(canvas, self._outer, _in_inner, event)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.win.bind_all(seq, _wheel)
        self._canvas = canvas

        self.vars: List[Tuple[Any, str]] = []
        self._build_rows()

        ttk.Button(box, text="+ Eget ord…",
                   command=self._add_own).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 8))

        # -- kategori ------------------------------------------------------
        catbox = ttk.LabelFrame(
            self._all, text="  Kategori / mapp (skriv för att söka)  ")
        catbox.grid(row=row_box + 1, column=0, sticky="ew", padx=14, pady=(12, 0))
        catbox.columnconfigure(1, weight=1)

        self.guess_name = guess_category_name(candidates)
        # Har ingen kategori träffat väljer vi "Ny mapp" med ett gissat namn,
        # i stället för att peka ut en slumpmässig befintlig kategori.
        start_mode = "existing" if (best and best.name in rules.names()) else (
            "new" if self.guess_name or not rules.names() else "existing")
        self.mode = tk.StringVar(value=start_mode)
        ttk.Radiobutton(catbox, text="Befintlig:", value="existing", variable=self.mode,
                        command=self._sync).grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self._all_categories = list(rules.names())
        self.combo = ttk.Combobox(catbox, values=self._all_categories,
                                  state="normal")
        if best and best.name in rules.names():
            self.combo.set(best.name)
        elif rules.names():
            self.combo.current(0)
        self.combo.bind("<<ComboboxSelected>>", self._combo_chosen)
        # Sökbar rullgardin: skriv några tecken -> listan filtreras och
        # visar bara matchande kategorier (början på namnet först).
        # Enter väljer första/unika träffen, Escape återställer listan.
        # Egen sökning i stället för klassbindningens "hoppa till första
        # prefix" (klassbindningen hoppar över pga _egen_ta).
        self.combo._egen_ta = True
        self.combo.bind("<KeyRelease>", self._combo_search)
        self.combo.bind("<Return>", self._combo_pick)
        self.combo.bind("<Escape>", self._combo_reset)
        self.combo.bind("<FocusIn>", self._combo_focus_in)
        self.combo.bind("<FocusOut>", self._combo_focus_out)
        self.combo.bind("<Down>", self._combo_navigate)
        self.combo.bind("<Up>", self._combo_navigate)
        # Mushjulet får ALDRIG byta kategori. Bindningen ligger på
        # widgeten (körs före TCombobox-klassens egen hjulbindning) och
        # returnerar "break"; i stället rullas dialogens yttre yta.
        for _seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.combo.bind(_seq, self._combo_wheel)
        self.combo.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=6)

        # Liten hjälprad: visar vad sökningen hittar och vad Enter gör.
        self._combo_hint_lbl = ttk.Label(catbox, text="",
                                        style="CardMuted.TLabel",
                                        wraplength=560, justify="left")
        self._combo_hint_lbl.grid(row=2, column=0, columnspan=2, sticky="w",
                                  padx=8, pady=(0, 4))
        self._combo_show_hint()

        ttk.Radiobutton(catbox, text="Ny mapp:", value="new", variable=self.mode,
                        command=self._sync).grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        self.new_entry = ttk.Entry(catbox)
        self.new_entry.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(0, 8))
        self.new_entry.bind("<KeyRelease>", lambda e: self.mode.set("new"))
        if self.guess_name:
            self.new_entry.insert(0, self.guess_name)
        if suggested_sender and not (best and best.name in rules.names()):
            self.mode.set("new")
            self.new_entry.delete(0, "end")
            self.new_entry.insert(0, suggested_sender)
            ttk.Label(catbox,
                      text=f"🔎 Uppslag via org.nr: {suggested_sender}"
                           " - kontrollera namnet innan du sparar",
                      style="CardMuted.TLabel").grid(
                          row=3, column=0, columnspan=2, sticky="w",
                          padx=8, pady=(0, 6))
        # "Ny mapp"-fältet ska vara låst när "Befintlig" är förvalt.
        self._sync()

        self.save_rule = tk.BooleanVar(value=True)
        ttk.Checkbutton(catbox, variable=self.save_rule,
                        text="Spara valda ord som regel (matchar automatiskt nästa gång)"
                        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))

        # -- knappar (ligger utanför rullytan, alltid synliga) -------------
        btns = ttk.Frame(self.win)
        btns.grid(row=1, column=0, sticky="ew", padx=14, pady=12)
        btns.columnconfigure(2, weight=1)
        ttk.Button(btns, text="Förhandsgranska PDF",
                   command=lambda: open_externally(decision.path)).grid(row=0, column=0)
        ttk.Button(btns, text="Hoppa över",
                   command=self._skip).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(btns, text="Ignorera filen",
                   command=self._ignore_file).grid(row=0, column=2, padx=8)
        ttk.Button(btns, text="Lägg i _Osorterat",
                   command=self._unmatched).grid(row=0, column=3, padx=(0, 8))
        ok = ttk.Button(btns, text="Spara & flytta", style="Accent.TButton",
                        command=self._ok)
        ok.grid(row=0, column=4)
        ok.focus_set()

        self._sync()
        self.win.protocol("WM_DELETE_WINDOW", self._skip)
        self.win.bind("<Escape>", lambda e: self._skip())
        self.win.bind("<Return>", lambda e: self._ok())
        self.win.update_idletasks()
        try:
            self.win.grab_set()
        except Exception:
            pass

    # -- rader ------------------------------------------------------------
    def _build_rows(self) -> None:
        ttk, tk = self.ttk, self.tk
        for child in self.inner.winfo_children():
            child.destroy()
        self.vars.clear()
        self.inner.columnconfigure(1, weight=0, minsize=BAR_WIDTH + 20)
        self.inner.columnconfigure(2, weight=1)

        if not self.candidates:
            ttk.Label(self.inner, text="Inga stödord kunde tas fram ur filen.\n"
                                       "Använd \"+ Eget ord…\" eller välj bara en mapp.",
                      style="CardMuted.TLabel").grid(row=0, column=0, columnspan=4,
                                                 sticky="w", padx=10, pady=10)
            return

        top = max((c.score for c in self.candidates), default=1.0) or 1.0
        for i, cand in enumerate(self.candidates):
            # Förbocka de starkaste identifierarna - avsändaren i
            # brevhuvudet, org.nr, VAT och domän är nästan alltid rätt.
            strong = ("sender", "orgnr", "vat", "company", "domain")
            var = tk.BooleanVar(value=(i < 3 and cand.kind in strong))
            self.vars.append((var, cand.text))
            ttk.Checkbutton(self.inner, variable=var, text=cand.display,
                            style="Card.TCheckbutton"
                            ).grid(row=i, column=0, sticky="w",
                                   padx=(12, 6), pady=4)
            # Stapeln ritas i pixlar, inte med tecken. Blockglyfer (█ ━ ─)
            # har olika bredd och täckning i olika typsnitt och blir
            # oläsliga eller likadana beroende på vilket typsnitt datorn
            # råkar ha. En ritad stapel ser likadan ut överallt.
            andel = max(0.06, min(1.0, cand.score / top))
            spår = tk.Frame(self.inner, width=BAR_WIDTH, height=8,
                            background=self.C["surface_sunk"])
            spår.grid(row=i, column=1, sticky="w", padx=10)
            spår.grid_propagate(False)
            tk.Frame(spår, width=int(BAR_WIDTH * andel), height=8,
                     background=self.C["accent"]).place(x=0, y=0)
            note = cand.label
            if cand.count > 1:
                note += f", {cand.count} ggr"
            owners = [o for o in self.rules.keyword_owners(cand.text)]
            if owners:
                note += "  ⚠ finns i " + ", ".join(owners[:2])
            ttk.Label(self.inner, text=note, style="CardMuted.TLabel"
                      ).grid(row=i, column=2, sticky="w", padx=(10, 14))

    # -- förhandsvisning (REQ-N7) -----------------------------------------
    def _start_preview_load(self) -> None:
        """Rendera de tre första sidorna i bakgrunden; dialogen öppnas
        direkt och bilderna dyker upp när de är klara."""
        if not has_pymupdf():
            self._prev_status.configure(
                text="Förhandsvisningen kräver pymupdf - knappen "
                     "Förhandsgranska PDF öppnar filen externt.")
            return
        path = self.decision.path

        def load():
            bilder = []
            try:
                import io as _io
                from PIL import Image as _PILImage
                pymupdf = _open_pymupdf()
                with pymupdf.open(str(path)) as doc:
                    for i in range(min(3, len(doc))):
                        pix = doc[i].get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4))
                        bilder.append(_PILImage.open(
                            _io.BytesIO(pix.tobytes("png"))))
            except Exception:
                bilder = []
            try:
                self.win.after(0, lambda b=bilder: self._preview_loaded(b))
            except Exception:
                pass

        threading.Thread(target=load, daemon=True,
                         name="pdfsorter-preview").start()

    def _preview_loaded(self, bilder: List[Any]) -> None:
        try:
            if not bilder:
                self._prev_status.configure(
                    text="Kunde inte förhandsvisa den här filen.")
                return
            self._prev_pil = bilder
            self._prev_status.configure(
                text=f"Förhandsvisning - {len(bilder)} av sidorna:")
            self._prev_show(0)
        except Exception:
            pass

    def _prev_show(self, i: int) -> None:
        """Visa sida i (0-baserat). PhotoImage skapas i huvudtråden och
        referensen sparas så att den inte sopas bort."""
        try:
            if not self._prev_pil or not (0 <= i < len(self._prev_pil)):
                return
            self._prev_page = i
            from PIL import ImageTk
            pil = self._prev_pil[i].copy()
            pil.thumbnail((760, 300))
            foto = ImageTk.PhotoImage(pil)
            self._prev_pages.append(foto)      # behåll referensen
            self._prev_img.configure(image=foto)
            self._prev_info.configure(text=f"{i + 1}/{len(self._prev_pil)}")
        except Exception:
            pass

    def _add_own(self) -> None:
        tk, ttk, filedialog, messagebox, simpledialog = _tk()
        word = simpledialog.askstring("Eget stödord",
                                      "Skriv ordet eller frasen som ska matcha:",
                                      parent=self.win)
        if not word or not normalize(word):
            return
        text = normalize(word)
        if any(t == text for _, t in self.vars):
            return
        self.candidates.append(Candidate(text, word.strip(), "word", 1, 0.01))
        self._build_rows()
        if self.vars:
            self.vars[-1][0].set(True)

    def _sync(self) -> None:
        # Rullgardinen är alltid skrivbar/sökbar; bara "Ny mapp"-fältet
        # växlas mellan aktivt och inaktivt.
        is_new = self.mode.get() == "new"
        self.new_entry.configure(state="normal" if is_new else "disabled")

    def _combo_show_hint(self, text: str = "") -> None:
        """Liten hjälprad under fältet: vad sökningen hittade och vad
        Enter gör. Gör beteendet begripligt även när listan är stängd."""
        lbl = getattr(self, "_combo_hint_lbl", None)
        if lbl is None:
            return
        q = str(text or "").strip()
        if not q:
            antal = len(self._all_categories)
            msg = (f"{antal} mappar – skriv för att söka, ↓ öppnar listan."
                   if antal else
                   "Inga mappar än – skriv ett namn för att skapa en.")
            lbl.configure(text=msg)
            return
        träffar, nivå = _rank_categories(q, self._all_categories)
        n = len(träffar)
        if nivå == "prefix":
            msg = f"{n} mappar börjar med ”{q}” – ↓/Enter visar dem."
        elif nivå == "word":
            msg = (f"Ingen mapp börjar med ”{q}” – {n} har ett ord "
                   "som börjar så.")
        elif nivå == "contains":
            msg = f"{n} mappar innehåller ”{q}”."
        else:
            msg = f"Ingen mapp matchar ”{q}” – Enter skapar den."
        lbl.configure(text=msg)

    def _combo_chosen(self, event=None) -> None:
        self.mode.set("existing")
        self._sync()
        self.new_entry.delete(0, "end")
        # Efter valet ska nästa öppning visa hela listan igen.
        self.combo["values"] = self._all_categories
        self.combo._ta_seed = ""
        self._combo_show_hint()

    def _combo_search(self, event=None) -> None:
        """Filtrera listan medan användaren skriver."""
        if event is not None:
            if getattr(event, "keysym", "") in (
                    "Up", "Down", "Return", "Escape", "Tab",
                    "Left", "Right", "Home", "End", "Prior", "Next",
                    "Shift_L", "Shift_R", "Control_L", "Control_R",
                    "Alt_L", "Alt_R"):
                return
            # Ctrl-kombon (Ctrl+A, Ctrl+C ...) ska inte filtrera; klistra
            # in (Ctrl+V) ska däremot uppdatera listan.
            if getattr(event, "state", 0) & 0x4 and \
                    getattr(event, "keysym", "") not in ("v", "V"):
                return
        text = self.combo.get().strip()
        if not text:
            self.combo["values"] = self._all_categories
            self.combo._ta_seed = ""
            self.mode.set("existing")
            self._sync()
            self.new_entry.delete(0, "end")
            self._combo_show_hint()
            return
        träffar = _filter_categories(text, self._all_categories)
        # Tom lista = inga träffar (visar ärligt att sökordet inte finns).
        self.combo["values"] = träffar
        self._combo_show_hint(text)
        if träffar:
            self.mode.set("existing")
            self._sync()
            self.new_entry.delete(0, "end")
            # Sökordet följer med ned i listan, så att "p" + "i" + "l"
            # fortsätter till PIL i stället för att börja om på "i".
            self._post_dropdown(seed=text)
        else:
            # Skrivet namn finns inte bland kategorierna -> ny mapp.
            self.combo._ta_seed = ""
            if self._popdown_open():
                try:
                    self.combo.tk.call("ttk::combobox::Unpost", self.combo)
                except Exception:
                    pass
            self.mode.set("new")
            self._sync()
            self.new_entry.delete(0, "end")
            self.new_entry.insert(0, text)

    def _popdown_open(self) -> bool:
        try:
            popdown = self.combo.tk.call(
                "ttk::combobox::PopdownWindow", self.combo)
            return bool(int(self.combo.tk.call("winfo", "ismapped", popdown)))
        except Exception:
            return False

    def _popdown_select_first(self) -> None:
        """Markera första träffen när listan öppnats - då räcker Enter."""
        lb = self._popdown_lb_path()
        if not lb:
            return
        try:
            if int(self.combo.tk.call(lb, "size")):
                self.combo.tk.call(lb, "selection", "clear", 0, "end")
                self.combo.tk.call(lb, "selection", "set", 0)
                try:
                    self.combo.tk.call(lb, "activate", 0)
                except Exception:
                    pass
                self.combo.tk.call(lb, "see", 0)
        except Exception:
            pass

    def _popdown_lb_path(self) -> str:
        try:
            popdown = str(self.combo.tk.call(
                "ttk::combobox::PopdownWindow", self.combo))
            return f"{popdown}.f.l"
        except Exception:
            return ""

    def _post_dropdown(self, seed: Optional[str] = None) -> None:
        """Visa/uppdatera den filtrerade listan (best effort)."""
        if seed is not None:
            self.combo._ta_seed = seed
        try:
            if self._popdown_open():
                # Redan öppen: uppdatera raderna med de nya träffarna.
                try:
                    self.combo.tk.call(
                        "ttk::combobox::ConfigureListbox", self.combo)
                except Exception:
                    pass
            else:
                self.combo.tk.call("ttk::combobox::Post", self.combo)
                try:
                    self.win.after_idle(self._popdown_select_first)
                except Exception:
                    pass
        except Exception:
            pass

    def _combo_reset_values(self, event=None) -> None:
        if not self._popdown_open():
            self.combo["values"] = self._all_categories

    def _combo_focus_in(self, event=None) -> None:
        """Fältet är en sökruta: markera allt så att första tecknet
        ersätter det förvalda kategorinamnet i stället för att hamna
        efter det ("Pilkington" + p = "Pilkingtonp")."""
        if not self._popdown_open():
            self.combo["values"] = self._all_categories
        self.combo._ta_seed = ""
        self._combo_show_hint()
        try:
            self.combo.selection_range(0, "end")
            self.combo.icursor("end")
        except Exception:
            pass

    def _combo_focus_out(self, event=None) -> None:
        # Fokus flyttar till rullgardinens listbox när den öppnas - då
        # får listan absolut inte återställas till hela kategorilistan.
        try:
            self.win.after_idle(self._combo_focus_check)
        except Exception:
            pass

    def _combo_focus_check(self) -> None:
        try:
            w = self.win.focus_get()
        except Exception:
            w = None
        if w is not None:
            path = str(w)
            cpath = str(self.combo)
            popdown = ""
            try:
                popdown = str(self.combo.tk.call(
                    "ttk::combobox::PopdownWindow", self.combo))
            except Exception:
                pass
            if path == cpath or path.startswith(cpath + ".") or \
                    (popdown and path.startswith(popdown)):
                return
        self.combo._ta_seed = ""
        self.combo["values"] = self._all_categories
        self._combo_show_hint()

    def _combo_reset(self, event=None) -> str:
        """Escape: stäng listan/återställ den - stänger inte dialogen."""
        if self._popdown_open():
            try:
                self.combo.tk.call("ttk::combobox::Unpost", self.combo)
            except Exception:
                pass
        self.combo._ta_seed = ""
        self._combo_reset_values()
        self._combo_show_hint()
        return "break"

    def _combo_pick(self, event=None) -> str:
        """Enter: välj den entydiga träffen i stället för att gissa."""
        text = self.combo.get().strip()
        namn = _resolve_category_name(text, self._all_categories)
        if namn:
            self.combo.set(namn)
            self.mode.set("existing")
            self._sync()
            self.new_entry.delete(0, "end")
            self.combo._ta_seed = ""
            self._combo_reset_values()
            self._combo_show_hint()
        elif _filter_categories(text, self._all_categories):
            # Flera träffar: öppna listan med dem och markera första
            # raden, så att nästa Enter väljer den.
            self._post_dropdown(seed=text)
        elif text:
            self.mode.set("new")
            self._sync()
            self.new_entry.delete(0, "end")
            self.new_entry.insert(0, text)
            self.combo._ta_seed = ""
            self._combo_reset_values()
            self._combo_show_hint(text)
        return "break"

    def _combo_wheel(self, event) -> str:
        """Mushjulet rullar fönstret - det får aldrig byta kategori."""
        try:
            delta = int(getattr(event, "delta", 0) or 0)
            # Använd tecknet, inte storleken: macOS rapporterar ibland ±1
            # per hack medan Windows rapporterar ±120.
            if delta:
                steg = -1 if delta > 0 else 1
            else:
                steg = 1 if getattr(event, "num", 4) == 5 else -1
            self._outer.yview_scroll(steg, "units")
        except Exception:
            pass
        return "break"

    def _combo_navigate(self, event) -> str:
        """Ner öppnar listan (native), upp bläddrar bakåt bland namnen."""
        if self._popdown_open():
            return ""
        if getattr(event, "keysym", "") == "Down":
            # Låt TCombobox öppna rullgardinen med de filtrerade raderna.
            return ""
        names = self._all_categories
        if not names:
            return "break"
        cur = self.combo.get()
        idx = names.index(cur) if cur in names else -1
        idx = (idx - 1) % len(names)
        self.combo.set(names[idx])
        self.mode.set("existing")
        self._sync()
        self.new_entry.delete(0, "end")
        self.combo._ta_seed = ""
        self._combo_reset_values()
        self._combo_show_hint()
        return "break"

    def _chosen(self) -> List[str]:
        return [text for var, text in self.vars if var.get()]

    def _category(self) -> str:
        if self.mode.get() == "new":
            return self.new_entry.get().strip()
        # Skrivet sökord kan vara en ofullständig träff: använd den bara
        # när den pekar ut exakt en kategori, aldrig som nytt mappnamn.
        return _resolve_category_name(self.combo.get(), self._all_categories)

    def _ok(self) -> None:
        cat = self._category()
        if not cat and self.mode.get() == "existing" and self.combo.get().strip():
            self.messagebox.showwarning(
                APP_NAME,
                f"Flera kategorier matchar \"{self.combo.get().strip()}\".\n\n"
                "Välj en av dem i listan (eller använd \"Ny mapp\" om du "
                "vill skapa en ny).", parent=self.win)
            self._post_dropdown()
            return
        if not cat:
            self.messagebox.showwarning(APP_NAME, "Välj en befintlig kategori eller skriv ett namn på en ny mapp.",
                                        parent=self.win)
            return
        words = self._chosen()
        if self.save_rule.get() and not words:
            if not self.messagebox.askyesno(
                    APP_NAME,
                    "Du har inte bockat i något stödord.\n\n"
                    "Filen flyttas då bara den här gången, ingen regel sparas.\n"
                    "Fortsätta?", parent=self.win):
                return
        self.result = {
            "category": cat,
            "words": words if self.save_rule.get() else [],
            "save_rule": bool(self.save_rule.get() and words),
            "folder": cat,
            "unmatched": False,
        }
        self._close()

    def _unmatched(self) -> None:
        self.result = {"unmatched": True}
        self._close()

    def _skip(self) -> None:
        self.result = None
        self._close()

    def _ignore_file(self) -> None:
        """Markera just DENNA fil som ignorerad: appen känns igen den på
        innehållet (hash) och frågar aldrig igen, oavsett namn eller mapp."""
        self.result = {"ignored_file": True}
        self._close()

    def _close(self) -> None:
        # Släpp förhandsvisningsbilderna direkt (minne, rond 5).
        if hasattr(self, "_prev_pages"):
            self._prev_pages.clear()
            self._prev_pil.clear()
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self._canvas.unbind_all(seq)
            except Exception:
                pass
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()

    def show(self) -> Optional[Dict[str, Any]]:
        self.win.wait_window()
        return self.result


# --------------------------------------------------------------------------
# Dubblettfrågan (REQ-N4) - Ersätt eller Behåll båda (2)
# --------------------------------------------------------------------------
def _search_key(text: str) -> str:
    """Söknyckel: gemener, utan diakriter (å/ä/ö = a/a/o), enkla mellanslag.

    Används bara av sökfältet - matchningsmotorn har sin egen normalize.
    """
    t = unicodedata.normalize("NFKD", str(text or "").casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip()


def _rank_categories(text: str, names) -> Tuple[List[str], str]:
    """Träffar + hur de matchades. Nivå används av hjälptexten i dialogen.

    Nivåerna är strikta: finns det namn som BÖRJAR på sökordet visas bara
    de (precis som en vanlig rullgardin som hoppar till P när man trycker
    p). Annars visas namn där ett ORD börjar på sökordet ("plan" hittar
    "Utrymningsplan"), och sist namn som innehåller det ("aygsinn" hittar
    "PARKERINGEN AYGSINN"). Skiftläge och å/ä/ö spelar ingen roll.
    """
    q = _search_key(text)
    if not q:
        return list(names), "all"
    start = [n for n in names if _search_key(n).startswith(q)]
    if start:
        return start, "prefix"
    ordstart = [n for n in names
                if any(w.startswith(q) for w in _search_key(n).split(" "))]
    if ordstart:
        return ordstart, "word"
    rest = [n for n in names if q in _search_key(n)]
    if rest:
        return rest, "contains"
    return [], "none"


def _filter_categories(text: str, names) -> List[str]:
    """Matchande kategorier, i den ordning de ska visas (se _rank_categories)."""
    return _rank_categories(text, names)[0]


def _typeahead_index(values, text: str, start: int = 0) -> int:
    """Första index (från start, cykliskt) vars namn börjar på text.

    -1 när inget matchar. Delas av combobox- och listbox-sökningen så att
    "p" hoppar till P och "pil" till PIL i HELA listan, oavsett hur den
    råkar vara filtrerad.
    """
    q = _search_key(text)
    n = len(values)
    if not q or not n:
        return -1
    for off in range(n):
        i = (int(start) + off) % n
        if _search_key(values[i]).startswith(q):
            return i
    return -1


def _resolve_category_name(text: str, names) -> str:
    """Översätt det skrivna fältet till en befintlig kategori.

    Exakt namn vinner, därefter en unik begynnelse- eller delsträng.
    Returnerar "" när inget eller flera namn matchar - då ska dialogen
    be användaren välja ur listan i stället för att gissa.
    """
    text = str(text or "").strip()
    if not text:
        return ""
    if text in names:
        return text
    q = _search_key(text)
    exact = [n for n in names if _search_key(n) == q]
    if len(exact) == 1:
        return exact[0]
    start = [n for n in names if _search_key(n).startswith(q)]
    if len(start) == 1:
        return start[0]
    alla = [n for n in names if q in _search_key(n)]
    if len(alla) == 1:
        return alla[0]
    return ""


def _typeahead_match(val: str, names) -> Tuple[Optional[str], bool]:
    """Sökbar rullgardin med typeahead (ANVÄNDARORDER 2026-08-26).

    Returnerar (namn, exakt_träff): först exakt match, annars första
    kategorin vars namn börjar med det skrivna (skriv 'd' -> hoppa till
    första D-kategorin). None om inget matchar (=> nytt mappnamn).
    """
    v = normalize(val)
    if not v:
        return None, False
    exact = next((n for n in names if normalize(n) == v), None)
    if exact:
        return exact, True
    jump = next((n for n in names if normalize(n).startswith(v)), None)
    return jump, False


def _conflict_ask_impl(app, src: Path, target: Path, kind: str) -> str:
    """Dubblettfrågan, trådsäker och dödläsningsfri (se App._ask_conflict)."""
    if app._conflict_remember:
        session_log("dubblett", f"{src.name}: kom ihåg-svar används = "
                    f"{app._conflict_remember}")
        return app._conflict_remember
    session_log("dubblett", f"Dubblett ({kind}) upptäckt: {src.name} krockar "
                f"med {target.name} - frågar användaren")
    resultat = {"v": "rename"}
    if threading.current_thread() is getattr(app, "_main_thread", None):
        try:
            resultat["v"] = ConflictDialog(app.root, src, target, kind, app).show()
        except Exception as exc:
            session_error("dubblett", exc)
            resultat["v"] = "rename"
        session_log("dubblett", f"Svar: {resultat['v']}")
        return resultat["v"]
    klart = threading.Event()

    def show():
        try:
            resultat["v"] = ConflictDialog(app.root, src, target, kind, app).show()
        except Exception as exc:
            session_error("dubblett", exc)
            resultat["v"] = "rename"
        finally:
            klart.set()

    app._post(show)
    klart.wait(120)
    session_log("dubblett", f"Svar: {resultat['v']}"
                + ("" if klart.is_set() else " (timeout 120 s - rename används)"))
    return resultat["v"]


class ConflictDialog:
    """Upptäcks en dubblett vid flytt frågar appen alltid: ska den nya
    filen ersätta den gamla, eller ska båda behållas (kopian får "(2)"
    i namnet)? Valet kan kommas ihåg under körningen."""

    def __init__(self, parent, src: Path, target: Path, kind: str, app):
        tk, ttk, filedialog, messagebox, simpledialog = _tk()
        self.tk = tk
        self.app = app
        self.result = "rename"
        self.win = tk.Toplevel(parent)
        self.win.after(80, lambda: dark_titlebar(
            self.win, bool(getattr(app, "theme", None)
                           and app.theme.dark)))
        self.win.title(f"{APP_NAME} - dubblett")
        self.win.transient(parent)
        self.win.resizable(False, False)
        try:
            self.win.configure(background=(app.C if app else COLORS)["bg"])
        except Exception:
            pass

        c = (app.C if app else COLORS)
        vad = ("En fil med samma namn finns redan i målmappen."
               if kind == "name" else
               "En fil med IDENTISKT innehåll (SHA-256) finns redan i "
               "målmappen, fast med annat namn.")
        tk.Label(self.win,
                 text=f"{vad}\n\n"
                      f"  Ny fil:      {src.name}\n"
                      f"  I målmappen: {target.name}\n\n"
                      f"Vad vill du göra?",
                 justify="left", anchor="w",
                 background=c["bg"], foreground=c["text"],
                 font=("TkDefaultFont", 10)).pack(padx=18, pady=(16, 8))

        self.var_remember = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.win, variable=self.var_remember,
                        text="Kom ihåg under denna körning").pack(
            anchor="w", padx=18)

        rad = ttk.Frame(self.win)
        rad.pack(padx=18, pady=16, fill="x")

        def ersatt():
            self.result = "replace"
            self.win.destroy()

        def bada():
            self.result = "rename"
            self.win.destroy()

        ttk.Button(rad, text="Ersätt den gamla", style="Danger.TButton",
                   command=ersatt).pack(side="left")
        ttk.Button(rad, text="Behåll båda (2)", style="Accent.TButton",
                   command=bada).pack(side="left", padx=8)
        ttk.Button(rad, text="Avbryt flytten",
                   command=self._avbryt).pack(side="right")
        self.win.bind("<Escape>", lambda e: self._avbryt())
        self.win.update_idletasks()
        try:
            self.win.grab_set()
        except Exception:
            pass

    def _avbryt(self):
        # Avbryt = ingen flytt alls: signaleras med "skip" och hanteras
        # av motorn som en överhoppad fil.
        self.result = "skip"
        self.win.destroy()

    def show(self) -> str:
        self.win.wait_window()
        if self.var_remember.get() and self.result != "skip":
            self.app._conflict_remember = self.result
        return self.result


# --------------------------------------------------------------------------
# Huvudfönstret
# --------------------------------------------------------------------------

# ==========================================================================
# TVÅSPRÅKIGT GRÄNSSNITT (1.1.0): ui_language = "sv" | "en"
# ==========================================================================
# Gränssnittet byggs på svenska; vid "en" översätts alla widgettexter som
# finns i tabellen efter bygget. Okända strängar står kvar på svenska -
# aldrig tomma, aldrig krasch.

_UI_EN = {
    "Sortera": "Sort", "Matchningar": "Rules", "Inställningar": "Settings",
    "Granska": "Review", "Historik": "History", "Hjälp": "Help",
    "Sortera nu": "Sort now", "Sorterar…": "Sorting…",
    "Starta bevakning": "Start watching", "Stoppa bevakning": "Stop watching",
    "●  Bevakning av": "●  Watching off",
    "TESTKÖRNING": "DRY RUN", "Spara": "Save", "Spara ändringar": "Save changes",
    "Avbryt": "Cancel", "Stäng": "Close", "Öppna": "Open", "Öppna mappen": "Open folder",
    "Ta bort": "Delete", "Ta bort markering": "Delete selected", "Byt namn": "Rename",
    "Uppdatera": "Refresh", "Läs om": "Reload", "Rensa": "Clear", "Töm kön": "Empty queue",
    "Bläddra…": "Browse…", "Lägg till…": "Add…", "Importera…": "Import…",
    "Exportera…": "Export…", "Exportera rapport (MD)": "Export report (MD)",
    "Exportera årsarkiv…": "Export year archive…",
    "Granska alla…": "Review all…", "Ångra valda": "Undo selected",
    "Sök efter uppdateringar…": "Check for updates…",
    "Kontrollera uppdateringar": "Check updates",
    "Installera Python-paket": "Install Python packages",
    "Uppdatera Python-paket": "Update Python packages",
    "Starta automatiskt med datorn": "Start automatically with the computer",
    "Starta bevakningen direkt": "Start watching immediately",
    "Starta minimerad i systemfältet": "Start minimized to tray",
    "Visa ikon i systemfältet": "Show tray icon",
    "Krysset minimerar i stället för att avsluta": "Close button minimizes to tray instead",
    "Visa notis när filer sorterats": "Notify when files are sorted",
    "Sök uppdateringar på GitHub vid start": "Check GitHub for updates at start",
    "Installera uppdateringar automatiskt": "Install updates automatically",
    "Schemalagd sortering": "Scheduled sorting",
    "Skriv kategori som PDF-metadata vid sortering": "Write category as PDF metadata when sorting",
    "Slå upp okända avsändare via nätet (org.nr)": "Look up unknown senders online (org. no.)",
    "Tema:": "Theme:", "Ljust": "Light", "Mörkt": "Dark",
    "   Kontrast:": "   Contrast:", "Normal": "Normal", "Hög": "High",
    "Språk:": "Language:", "(gäller vid omstart)": "(applies after restart)",
    "Skapa genväg på skrivbordet": "Create desktop shortcut",
    "Spara ikonfil": "Save icon file", "Öppna inställningsmappen": "Open settings folder",
    "Öppna log-mappen": "Open log folder", "Kopiera diagnostik för support": "Copy diagnostics for support",
    "Fråga när appen är osäker": "Ask when the app is unsure",
    "OCR för skannade PDF:er": "OCR for scanned PDFs",
    "Bättre OCR (noggrannare, något långsammare)": "Better OCR (more accurate, slightly slower)",
    "Lärande matchning (appen lär av dina beslut)": "Learning matching (the app learns from your choices)",
    "Läs även undermappar i inmappen": "Include subfolders of the inbox",
    "Lägg filer i undermappar efter datum": "Put files in subfolders by date",
    "Skanna om allt när ett nytt stödord lärts in": "Rescan everything when a new keyword is learned",
    "Poppa upp dialogen direkt under bevakning": "Pop up the dialog directly while watching",
    "Aktiv": "Active", "Dagar:": "Days:", "Hoppa över": "Skip",
    "Spara & flytta": "Save & move", "Lägg i _Osorterat": "Put in _Unsorted",
    "Ignorera filen": "Ignore file", "Befintlig:": "Existing:", "Ny mapp:": "New folder:",
    "Mappnamn:": "Folder name:", "Undermapp:": "Subfolder:",
    "Sök stödord": "Search keywords", "Kontrollera": "Check", "Kontrollera igen": "Check again",
    "Spara hjälpen som textfil…": "Save help as text file…",
    "Stöd projektet 💖": "Support the project 💖",
    "Inga filer väntar på granskning.": "No files are waiting for review.",
    "Sluta ignorera markerad": "Stop ignoring selected",
    "Skanna om alla": "Rescan all", "Filnamnsmönster": "Filename pattern",
    "Ord i innehållet": "Words in content", "Åtgärd:": "Action:", "Flytta": "Move",
    "Hämta Tesseract…": "Get Tesseract…", "Sök datorn": "Search computer",
    "Installera Tesseract automatiskt": "Install Tesseract automatically",
    "Hämta svenska": "Get Swedish", "+ Ny": "+ New", "Kopiera": "Copy",
    "Visa inte detta igen": "Don't show this again",
    "Kom ihåg under denna körning": "Remember for this run",
    "Behåll båda (2)": "Keep both (2)", "Ersätt den gamla": "Replace the old one",
    "Avbryt flytten": "Cancel the move",
}


def _translate_ui_tree(widget, mapping) -> int:
    """Översätt widgettexter enligt mapping, rekursivt. Returnerar antal."""
    antal = 0
    try:
        klass = widget.winfo_class()
    except Exception:
        return 0
    try:
        if klass == "TNotebook":
            for flik in widget.tabs():
                try:
                    txt = widget.tab(flik, "text")
                    if txt in mapping:
                        widget.tab(flik, text=mapping[txt]); antal += 1
                except Exception:
                    pass
        elif klass == "Menu":
            slut = widget.index("end")
            for i in range((slut + 1) if slut is not None else 0):
                try:
                    txt = widget.entrycget(i, "label")
                    if txt in mapping:
                        widget.entryconfigure(i, label=mapping[txt]); antal += 1
                except Exception:
                    pass
        else:
            txt = widget.cget("text")
            if isinstance(txt, str) and txt in mapping:
                widget.configure(text=mapping[txt]); antal += 1
    except Exception:
        pass
    try:
        for barn in widget.winfo_children():
            antal += _translate_ui_tree(barn, mapping)
    except Exception:
        pass
    return antal


class App:
    def __init__(self, start_hidden: bool = False) -> None:
        tk, ttk, filedialog, messagebox, simpledialog = _tk()
        self.tk, self.ttk = tk, ttk
        self.filedialog, self.messagebox, self.simpledialog = filedialog, messagebox, simpledialog

        self.settings = load_settings()
        self.rules = Rules.load()
        # Manuellt utpekad tesseract (installerad på udda ställe) ska
        # gälla direkt vid start, innan standardsökningen ens körs.
        try:
            set_tesseract_path(self.settings.get("tesseract_path", ""))
        except Exception:
            pass
        self._warm_patterns()
        self.engine = SortEngine(self.rules, self.settings,
                                 log=self._log_threadsafe,
                                 conflict_asker=self._ask_conflict)
        # Startsammanfattning till sessionsloggen - den som felsöker ska
        # direkt se inställningar, regler och motorer utan att fråga.
        _antal_kw = sum(len(c.get("keywords", []))
                        for c in self.rules.categories)
        session_log("start", f"Inställningar: strikthet="
                    f"{self.settings.get('strictness', 'normal')}, "
                    f"min_keywords={self.settings.get('min_keywords', 1)}, "
                    f"action={self.settings.get('action', 'move')}, "
                    f"dry_run={bool(self.settings.get('dry_run', False))}, "
                    f"ask_when_unsure={self.settings.get('ask_when_unsure', True)}")
        session_log("start", f"Mappar: in={self.input_dirs}, "
                    f"ut={self.settings.get('output_dir', '')}, "
                    f"exkluderade={list(self.settings.get('exclude_dirs', []))}")
        session_log("start", f"Regler: {len(self.rules.categories)} kategorier, "
                    f"{_antal_kw} stödord")
        try:
            session_log("start", "Läsmotorer: " + ", ".join(
                f"{k}={'ja' if v else 'nej'}"
                for k, v in backend_status().items()))
        except Exception:
            pass
        self.watcher: Optional[MultiFolderWatcher] = None
        self.queue: List[Decision] = []          # osäkra filer som väntar
        self._queued_paths: set = set()
        self._busy = False
        self._ui_calls: List[Callable[[], None]] = []
        self._ui_lock = threading.Lock()
        #: UI-tråden: används för att avgöra om en dialog kan visas direkt
        #: (dödlåsningsskydd i dubblettfrågan).
        self._main_thread = threading.current_thread()
        #: REQ-N4: "Kom ihåg under denna körning" från dubblettfrågan.
        self._conflict_remember: Optional[str] = None
        # TrayIcon är en variabel (klassen eller None-reserven), vilket en
        # typkontrollant inte accepterar i typuttryck - därför Any här.
        self.tray: Optional[Any] = None
        self.visible = True
        self._quitting = False
        self._rescanning = False
        self._icon_ref = None                    # håll kvar PhotoImage

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        # Fönstret anpassas dynamiskt till skärmstorleken (användarorder
        # 2026-08-26) - aldrig större än skärmen, centrerat, åtkomligt
        # minsta mått även på små skärmar.
        _fit_geometry(self.root, 1280, 880, 1060, 720)
        self.theme = Theme(self.root, ttk,
                           dark=str(self.settings.get("theme", "ljus")) == "mork",
                           contrast=self.settings.get("contrast", "normal"))
        self.C = self.theme.c
        install_snabbtangenter(self.root)
        # Modern titellist som följer temat (mörk lista i mörkt läge).
        self.root.after(120, lambda: dark_titlebar(self.root,
                                                   bool(self.theme.dark)))

        # Fönsterikon: brand_window sätter ikonen på det här fönstret och
        # (default=True) på alla framtida dialoger och felrutor, inklusive
        # aktivitetsfältet på Windows via iconbitmap.
        self._icon_ref = brand_window(self.root)

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(10, 0))
        self.tab_sort = ttk.Frame(self.nb)
        self.tab_opts = ttk.Frame(self.nb)
        self.tab_cats = ttk.Frame(self.nb)
        self.tab_review = ttk.Frame(self.nb)
        self.tab_hist = ttk.Frame(self.nb)
        self.tab_json = ttk.Frame(self.nb)
        self.tab_help = ttk.Frame(self.nb)
        self.nb.add(self.tab_sort, text="Sortera")
        self.nb.add(self.tab_cats, text="Matchningar")
        self.nb.add(self.tab_opts, text="Inställningar")
        self.nb.add(self.tab_review, text="Granska")
        self.nb.add(self.tab_hist, text="Historik")
        self.nb.add(self.tab_json, text="JSON")
        self.nb.add(self.tab_help, text="Hjälp")

        self._build_sort_tab()
        self._build_cats_tab()
        self._build_review_tab()
        self._build_hist_tab()
        self._build_json_tab()
        self._build_help_tab()

        status_line = status_text()
        if not SYSTEM_MODULE:
            status_line += "  |  pdfsorter_system.py saknas"
        self.status = ttk.Label(self.root, text=status_line, style="Status.TLabel",
                                anchor="w")
        self.status.pack(fill="x", side="bottom")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Unmap>", self._on_unmap)
        self.root.after(120, self._pump)
        self._refresh_input_list()
        self._refresh_categories()
        self._refresh_history()
        self._refresh_queue()

        # 1.1.0: engelskt gränssnitt om ui_language=en (byggs svenskt,
        # översätts här). Schemakontrollen tickar var 30:e sekund.
        if self.settings.get("ui_language", "sv") == "en":
            try:
                _translate_ui_tree(self.root, _UI_EN)
            except Exception:
                pass
        self.root.after(30000, self._schedule_tick)

        # Självläkande autostart (bättre autostart): OS-posten och
        # inställningen synkas vid varje start - och resultatet loggas,
        # så att en tyst trasig autostart syns i sessionsloggen.
        #
        # Startskedet får aldrig RADERA en fungerande autostart: om
        # OS-posten finns men settings säger av (t.ex. efter att ha
        # installerats via install.sh, en annan användares profil eller
        # en återställd settings.json) ärver vi OS-posten i stället.
        # Borttagning kräver ett uttryckligt val i gränssnittet.
        try:
            vill, ärvd = effective_autostart(self.settings)
            if ärvd:
                self.settings["autostart"] = True
                save_settings(self.settings)
                self._h("autostart",
                        "Autostarten fanns i operativsystemet - "
                        "inställningen uppdaterades i stället för att "
                        "posten togs bort", "warn")
            ok, msg = sync_autostart(vill)
            self._h("autostart", f"Startsynk: {msg}",
                    "ok" if ok else "warn")
        except Exception as exc:
            session_error("autostart", exc)

        # Uppdatering från Git (2026-10-16): sök tyst vid start om
        # inställningen är på - fråga alltid före installation om inte
        # auto_update valts uttryckligen.
        if self.settings.get("check_updates", True):
            self.root.after(5000, lambda: self._check_updates_gui(manual=False))

        # Systemfältsikon. TrayIcon är None när systemmodulen saknas
        # (REQ-A2) - då ska appen starta ändå, utan ikon.
        if self.settings.get("tray_enabled", True) and TrayIcon is not None:
            self.tray = TrayIcon(self)
            if self.tray.start():
                self._h("systemfält", "Systemfältsikon startad")
            else:
                self.tray = None
                self._h("systemfält", "Systemfältsikonen KUNDE INTE startas "
                        "(pystray-fel) - appen körs utan ikon", "warn")
                if start_hidden:
                    self._log("Systemfältet är inte tillgängligt "
                              "(installera pystray) - visar fönstret i stället.", "warn")
        elif start_hidden:
            self._h("systemfält", "Systemfält saknas helt (modul/pystray) - "
                    "visar fönstret trots --tray", "warn")
            self._log("Systemfältet är inte tillgängligt "
                      "(pdfsorter_system.py eller pystray saknas) - "
                      "visar fönstret i stället.", "warn")
        else:
            self._h("systemfält", f"Systemfältsikon avstängd "
                    f"(inställning tray_enabled={self.settings.get('tray_enabled', True)}, "
                    f"modul tillgänglig={TrayIcon is not None})")

        # Starta bevakning direkt
        if self.settings.get("autowatch_on_start", False):
            self.root.after(400, lambda: self._start_watch(quiet=True))

        # Vid start: installera saknade Python-tillägg automatiskt med
        # progress bar (ANVÄNDARORDER 2026-10-06); därefter dialog för
        # det som inte är pip (Tesseract/svenska). Aldrig blockerande.
        self.root.after(900, self._autoinstallera_tillagg)

        # Starta minimerad - men bara om ikonen garanterat går att se.
        # På Linux/GNOME utan AppIndicator blev appen tidigare helt osynlig
        # (inget fönster, ingen ikon) när autostarten körde --tray.
        vill_dold = bool(start_hidden
                         or self.settings.get("start_minimized", False))
        if vill_dold:
            varför = ("--tray" if start_hidden
                      else "inställningen 'starta minimerad'")
            if not self.tray:
                self._h("fönster", "Minimerad start begärd men systemfält "
                        "saknas - fönstret visas ändå", "warn")
            else:
                säkert, orsak = tray_hidden_start_safe()
                if säkert:
                    self._h("fönster", f"Fönstret visas INTE vid start "
                            f"({varför}) - göms i systemfältet efter 150 ms")
                    self.root.after(150,
                                    lambda: self.hide_window(f"start: {varför}"))
                else:
                    self._h("fönster", f"Dold start avbröts ({orsak}) - "
                            "fönstret visas i stället", "warn")
                    self._log(f"Dold start avbröts: {orsak}. Fönstret visas "
                              "så att appen alltid går att nå.", "warn")

    # -- trådsäker UI-uppdatering -----------------------------------------
    def _post(self, fn: Callable[[], None]) -> None:
        with self._ui_lock:
            self._ui_calls.append(fn)

    def _pump(self) -> None:
        with self._ui_lock:
            calls, self._ui_calls = self._ui_calls, []
        for fn in calls:
            try:
                fn()
            except Exception as exc:
                # Logga i stället för att svälja: ett UI-fel som tystas
                # här är omöjligt att felsöka i efterhand.
                session_error("ui-puls", exc)
        # Har någon försökt starta appen en andra gång? Då vill de åt
        # fönstret. Kollas var åttonde puls, alltså ungefär en gång per
        # sekund - tillräckligt snabbt utan att belasta disken.
        self._pump_varv = getattr(self, "_pump_varv", 0) + 1
        if self._pump_varv % 8 == 0:
            try:
                if consume_show_request():
                    self.show_window("en andra instans begärde fönstret")
            except Exception as exc:
                session_error("fönster", exc)
        self.root.after(120, self._pump)

    def _log_threadsafe(self, msg: str, level: str = "info") -> None:
        # Sessionsloggen skrivs direkt (trådsäker) - GUI-texten postas.
        session_log("sortering", msg, level)
        self._post(lambda: self._log_gui(msg, level))

    def _log(self, msg: str, level: str = "info") -> None:
        # Allt som visas i GUI-loggen hamnar även i sessionsloggen, så att
        # hela historiken finns i filen (användarorder: logga precis allt).
        session_log("gui", msg, level)
        self._log_gui(msg, level)

    def _log_gui(self, msg: str, level: str = "info") -> None:
        self.logbox.configure(state="normal")
        self.logbox.insert("end", f"{datetime.now():%H:%M:%S}  ", "time")
        self.logbox.insert("end", f"{msg}\n", level)
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    # -- sessionslogg: korta hjälpvägar ----------------------------------
    def _h(self, category: str, msg: str, level: str = "info") -> None:
        """En rad till sessionsloggen (kategorier: ui, fönster, inställningar,
        bevaka, motor, ...). Trådsäker."""
        session_log(category, msg, level)

    def _fel(self, exc: BaseException, var: str) -> None:
        """Logga ett undantag med spårning + visa det i GUI-loggen."""
        session_error(var, exc)
        self._log_threadsafe(f"{var}: {type(exc).__name__}: {exc}", "err")

    def _ui(self, vad: str) -> None:
        """Logga ett användarklick, så att 'vad tryckte jag på?' syns i filen."""
        session_log("ui", f"Klick: {vad}")

    # ======================================================================
    # Flik 1 - Sortera
    # ======================================================================
    def _build_sort_tab(self) -> None:
        """Den dagliga vyn: mappar, en stor knapp och loggen."""
        tk, ttk = self.tk, self.ttk
        T = self.theme
        f = self.tab_sort
        f.configure(style="TFrame")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)

        g = self.tab_opts          # tunga inställningar bor på egen flik
        g.columnconfigure(0, weight=1)

        # -- rad 1: mapparna sida vid sida --------------------------------
        top = ttk.Frame(f)
        top.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 0))
        top.columnconfigure(0, weight=3, uniform="m")
        top.columnconfigure(1, weight=2, uniform="m")

        incard = T.card(top, "Inmappar som bevakas")
        incard.grid(row=0, column=0, sticky="nsew", padx=(0, T.GAP))
        box = incard.body
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)

        self.in_list = tk.Listbox(box, height=5, exportselection=False,
                                  activestyle="none", borderwidth=0,
                                  selectmode="extended",
                                  background=self.C["surface"],
                                  foreground=self.C["text"],
                                  selectbackground=self.C["accent_light"],
                                  selectforeground=self.C["accent_dark"],
                                  highlightthickness=0, font=T.f_base)
        self.in_list.grid(row=0, column=0, sticky="nsew",
                          padx=(T.INNER, 0), pady=T.INNER)
        insb = ttk.Scrollbar(box, orient="vertical", command=self.in_list.yview)
        insb.grid(row=0, column=1, sticky="ns", pady=T.INNER)
        self.in_list.configure(yscrollcommand=insb.set)
        self.in_list.bind("<Double-1>", lambda e: self._open_selected_input())

        inbtn = ttk.Frame(box, style="CardInner.TFrame")
        inbtn.grid(row=0, column=2, sticky="n", padx=T.INNER, pady=T.INNER)
        ttk.Button(inbtn, text="Lägg till…", width=12,
                   command=self._add_input_dir).pack(fill="x")
        ttk.Button(inbtn, text="Ta bort", width=12,
                   command=self._remove_input_dir).pack(fill="x", pady=6)
        ttk.Button(inbtn, text="Öppna", width=12,
                   command=self._open_selected_input).pack(fill="x")

        outcard = T.card(top, "Utmapp", "undermapparna skapas här")
        outcard.grid(row=0, column=1, sticky="nsew")
        outbox = outcard.body
        outbox.columnconfigure(0, weight=1)
        self.var_out = tk.StringVar(value=self.settings.get("output_dir", ""))
        ttk.Entry(outbox, textvariable=self.var_out).grid(
            row=0, column=0, columnspan=2, sticky="ew",
            padx=T.INNER, pady=(T.INNER, 8))
        ttk.Button(outbox, text="Bläddra…", command=lambda: self._pick(self.var_out)
                   ).grid(row=1, column=0, sticky="ew", padx=(T.INNER, 4),
                          pady=(0, T.INNER))
        ttk.Button(outbox, text="Öppna mappen", command=self.open_output
                   ).grid(row=1, column=1, sticky="ew", padx=(0, T.INNER),
                          pady=(0, T.INNER))
        outbox.columnconfigure(0, weight=1)
        outbox.columnconfigure(1, weight=1)

        # -- rad 2: handlingsraden ----------------------------------------
        # Det viktigaste på hela fliken. Egen vit yta så att knappen
        # "Sortera nu" läses som fönstrets primära åtgärd.
        actcard = ttk.Frame(f, style="Card.TFrame")
        actcard.grid(row=1, column=0, sticky="ew", padx=T.PAD, pady=(T.GAP, 0))
        actcard.columnconfigure(2, weight=1)

        self.btn_sort = ttk.Button(actcard, text="Sortera nu",
                                   style="Accent.TButton", command=self._sort_now)
        self.btn_sort.grid(row=0, column=0, padx=(T.INNER, 8), pady=T.INNER)
        self.btn_watch = ttk.Button(actcard, text="Starta bevakning",
                                    command=self._toggle_watch)
        self.btn_watch.grid(row=0, column=1, pady=T.INNER)

        self.lbl_watch = ttk.Label(actcard, text="●  Bevakning av",
                                   style="CardMuted.TLabel")
        self.lbl_watch.grid(row=0, column=2, sticky="w", padx=14)

        # Tre siffror som svarar på "hur går det?" utan att man läser loggen.
        stats = ttk.Frame(actcard, style="CardInner.TFrame")
        stats.grid(row=0, column=3, sticky="e", padx=(0, 8))
        self.stat_labels: Dict[str, Any] = {}
        for i, (key, caption) in enumerate((("sorted", "sorterade"),
                                            ("queue", "att granska"),
                                            ("errors", "fel"))):
            cell = ttk.Frame(stats, style="CardInner.TFrame")
            cell.grid(row=0, column=i, padx=(0 if i == 0 else 22, 0))
            num = ttk.Label(cell, text="0", style="CardHead.TLabel")
            num.pack()
            ttk.Label(cell, text=caption, style="CardMuted.TLabel").pack()
            self.stat_labels[key] = num

        self.progress = ttk.Progressbar(actcard, mode="determinate", length=170)
        self.progress.grid(row=0, column=4, padx=(14, 0))

        # Statuspiller: testkörning och procent syns vid en blick, i tema-
        # systemets egna pillytor i stället för utspridda färgattribut.
        self.pill_dry = ttk.Label(actcard, text="TESTKÖRNING",
                                  style="PillWarn.TLabel")
        self.pill_dry.grid(row=0, column=5, padx=(10, 0))
        self.lbl_progress = ttk.Label(actcard, text="", width=6,
                                      style="CardMuted.TLabel")
        self.lbl_progress.grid(row=0, column=6, padx=(6, T.INNER))

        # -- rad 3: loggen -------------------------------------------------
        logcard = T.card(f, "Logg", "senaste händelserna")
        logcard.grid(row=2, column=0, sticky="nsew", padx=T.PAD,
                     pady=(T.GAP, T.GAP))
        logf = logcard.body
        logf.columnconfigure(0, weight=1)
        logf.rowconfigure(0, weight=1)
        self.logbox = tk.Text(logf, height=10, wrap="none", state="disabled",
                              font=T.f_mono, borderwidth=0,
                              background=self.C["surface"],
                              foreground=self.C["text"],
                              selectbackground=self.C["accent_light"],
                              padx=T.INNER, pady=10, highlightthickness=0,
                              spacing1=1, spacing3=1)
        self.logbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(logf, orient="vertical", command=self.logbox.yview)
        sb.grid(row=0, column=1, sticky="ns", pady=6, padx=(0, 4))
        self.logbox.configure(yscrollcommand=sb.set)
        self.logbox.tag_configure("info", foreground=self.C["text"])
        self.logbox.tag_configure("ok", foreground=self.C["ok"])
        self.logbox.tag_configure("warn", foreground=self.C["warn"])
        self.logbox.tag_configure("err", foreground=self.C["err"])
        self.logbox.tag_configure("time", foreground=self.C["text_faint"])
        self._log(f"{APP_NAME} {APP_VERSION} — {status_text()}", "info")
        self._log(f"Inställningar och regler: {config_dir()}", "info")
        if VERSIONS_BLANDADE or OLD_READ_MODULE:
            self._log("Varning: blandade modulversioner "
                      f"{_module_versions()} - kopiera ALLA fem filer "
                      "från senaste leveransen.", "warn")

        # inställningar
        optcard = T.card(g, "Vad appen gör med filerna")
        optcard.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 0))
        opt = optcard.body
        for c in range(4):
            opt.columnconfigure(c, weight=1)

        self.var_recursive = tk.BooleanVar(value=self.settings.get("recursive", True))
        self.var_ask = tk.BooleanVar(value=self.settings.get("ask_when_unsure", True))
        self.var_ocr = tk.BooleanVar(value=self.settings.get("ocr_enabled", True))
        self.var_dry = tk.BooleanVar(value=self.settings.get("dry_run", False))
        self.var_action = tk.StringVar(value=self.settings.get("action", "move"))
        self.var_popup = tk.BooleanVar(value=self.settings.get("popup_immediately", False))

        ttk.Checkbutton(opt, text="Läs även undermappar i inmappen",
                        style="Card.TCheckbutton",
                        variable=self.var_recursive).grid(row=0, column=0, columnspan=2,
                                                          sticky="w", padx=8, pady=(6, 2))
        ttk.Checkbutton(opt, text="Fråga när appen är osäker",
                        style="Card.TCheckbutton",
                        variable=self.var_ask).grid(row=0, column=2, columnspan=2,
                                                    sticky="w", padx=8, pady=(6, 2))
        self.var_learned = tk.BooleanVar(
            value=self.settings.get("learned_matching", True))
        ttk.Checkbutton(opt, text="Lärande matchning (appen lär av dina beslut)",
                        style="Card.TCheckbutton",
                        variable=self.var_learned).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=8, pady=2)
        ocr_cb = ttk.Checkbutton(opt, text="OCR för skannade PDF:er",
                                 style="Card.TCheckbutton", variable=self.var_ocr)
        ocr_cb.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=2)
        if not ocr_available():
            ocr_cb.state(["disabled"])
        # REQ-B4 AC-4.3: "Bättre OCR" som eget val när det är kritiskt att
        # det blir rätt. standard = snabbare, high = bäst avläsning.
        self.var_ocr_quality = tk.BooleanVar(
            value=str(self.settings.get("ocr_quality", "high")) == "high")
        ocr_q_cb = ttk.Checkbutton(opt, text="Bättre OCR (noggrannare, något långsammare)",
                                   style="Card.TCheckbutton",
                                   variable=self.var_ocr_quality)
        ocr_q_cb.grid(row=1, column=2, columnspan=2, sticky="w", padx=8, pady=2)
        if not ocr_available():
            ocr_q_cb.state(["disabled"])
        ttk.Checkbutton(opt, text="Poppa upp dialogen direkt under bevakning",
                        style="Card.TCheckbutton",
                        variable=self.var_popup).grid(row=2, column=2, columnspan=2,
                                                      sticky="w", padx=8, pady=2)
        self.var_rescan = tk.BooleanVar(
            value=self.settings.get("rescan_after_learn", True))
        ttk.Checkbutton(opt, text="Skanna om allt när ett nytt stödord lärts in",
                        style="Card.TCheckbutton",
                        variable=self.var_rescan).grid(row=3, column=0, columnspan=2,
                                                       sticky="w", padx=8, pady=2)
        ttk.Checkbutton(opt, text="Testkörning (visa vad som skulle hänt, flytta inget)",
                        style="Card.TCheckbutton",
                        variable=self.var_dry).grid(row=2, column=0, columnspan=2,
                                                    sticky="w", padx=8, pady=2)
        act = ttk.Frame(opt, style="CardInner.TFrame")
        act.grid(row=3, column=2, columnspan=2, sticky="w", padx=8, pady=2)
        ttk.Label(act, text="Åtgärd:", style="Card.TLabel").pack(side="left")
        ttk.Radiobutton(act, text="Flytta", value="move",
                        style="Card.TRadiobutton",
                        variable=self.var_action).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(act, text="Kopiera", value="copy",
                        style="Card.TRadiobutton",
                        variable=self.var_action).pack(side="left", padx=(8, 0))

        adv = ttk.Frame(opt, style="CardInner.TFrame")
        adv.grid(row=4, column=0, columnspan=4, sticky="w",
                 padx=8, pady=(8, T.INNER))
        self.var_unmatched = tk.StringVar(value=self.settings.get("unmatched_folder", ""))
        ttk.Label(adv, text="Osorterat-mapp:", style="Card.TLabel").pack(side="left")
        ttk.Entry(adv, textvariable=self.var_unmatched, width=18
                  ).pack(side="left", padx=(8, 8))
        ttk.Label(adv, text="tom = lämna kvar i inmappen",
                  style="CardMuted.TLabel").pack(side="left")

        # -- strikthet --
        strictcard = T.card(g, "Hur säker måste appen vara?")
        strictcard.grid(row=1, column=0, sticky="ew", padx=T.PAD, pady=(T.GAP, 0))
        strict = strictcard.body
        strict.columnconfigure(1, weight=1)

        self.var_strict = tk.StringVar(value=self.settings.get("strictness", "normal"))
        ttk.Label(strict, text="Nivå:", style="CardKey.TLabel").grid(
            row=0, column=0, sticky="w", padx=T.INNER, pady=(T.INNER, 2))
        self.strict_combo = ttk.Combobox(
            strict, state="readonly", width=42,
            values=[STRICTNESS_LEVELS[k]["label"] for k in STRICT_ORDER])
        self.strict_combo.grid(row=0, column=1, sticky="w", pady=(8, 2))
        self.strict_combo.bind("<<ComboboxSelected>>", lambda e: self._on_strictness())
        try:
            self.strict_combo.current(STRICT_ORDER.index(self.var_strict.get()))
        except ValueError:
            self.strict_combo.current(1)

        self.lbl_strict = ttk.Label(strict, text="", style="CardMuted.TLabel",
                                    wraplength=760, justify="left")
        self.lbl_strict.grid(row=1, column=0, columnspan=3, sticky="w",
                             padx=T.INNER, pady=(2, 6))

        self.strict_detail = ttk.Frame(strict, style="CardInner.TFrame")
        self.strict_detail.grid(row=2, column=0, columnspan=3, sticky="w",
                                padx=T.INNER, pady=(0, T.INNER))
        self.var_minscore = tk.StringVar(value=str(self.settings.get("min_score", 1.0)))
        self.var_margin = tk.StringVar(value=str(self.settings.get("ambiguity_margin", 0.5)))
        self.var_minkw = tk.StringVar(value=str(self.settings.get("min_keywords", 1)))
        self.var_ratio = tk.StringVar(value=str(self.settings.get("score_ratio", 1.0)))
        self.var_mintext = tk.StringVar(value=str(self.settings.get("min_text_chars", 0)))
        self.var_strong = tk.BooleanVar(value=self.settings.get("require_strong", False))

        for col, (text, var, width, tip) in enumerate((
                ("Lägsta poäng:", self.var_minscore, 5,
                 "Summan av vikterna för de stödord som träffar"),
                ("Marginal till tvåan:", self.var_margin, 5,
                 "Hur många poäng bättre än näst bästa kategori"),
                ("Antal stödord:", self.var_minkw, 4,
                 "Så många olika stödord måste träffa"))):
            ttk.Label(self.strict_detail, text=text, style="Card.TLabel").grid(
                row=0, column=col * 2, sticky="e", padx=(0 if col == 0 else 14, 3))
            e = ttk.Entry(self.strict_detail, textvariable=var, width=width)
            e.grid(row=0, column=col * 2 + 1, sticky="w")

        ttk.Label(self.strict_detail, text="Gånger starkare:",
                  style="Card.TLabel").grid(
            row=1, column=0, sticky="e", pady=(6, 0), padx=(0, 3))
        ttk.Entry(self.strict_detail, textvariable=self.var_ratio, width=5).grid(
            row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Label(self.strict_detail, text="Minst antal tecken:",
                  style="Card.TLabel").grid(
            row=1, column=2, sticky="e", pady=(6, 0), padx=(14, 3))
        ttk.Entry(self.strict_detail, textvariable=self.var_mintext, width=5).grid(
            row=1, column=3, sticky="w", pady=(6, 0))
        ttk.Checkbutton(self.strict_detail, style="Card.TCheckbutton",
                        text="Kräv org.nr, VAT, bankgiro eller domän",
                        variable=self.var_strong).grid(
            row=1, column=4, columnspan=2, sticky="w", pady=(6, 0), padx=(14, 0))

        self.var_anchor = tk.BooleanVar(value=self.settings.get("require_anchor", False))
        self.var_rejrec = tk.BooleanVar(
            value=self.settings.get("reject_recipient_only", True))
        ttk.Checkbutton(self.strict_detail, style="Card.TCheckbutton",
                        text="Stödordet måste stå i brevhuvudet eller filnamnet",
                        variable=self.var_anchor).grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Checkbutton(self.strict_detail, style="Card.TCheckbutton",
                        text="Hoppa över filer där företaget bara är mottagare",
                        variable=self.var_rejrec).grid(
            row=2, column=4, columnspan=2, sticky="w", pady=(6, 0), padx=(14, 0))
        self._on_strictness(initial=True)

        # -- datum och undermappar --
        datecard = T.card(g, "Datum och undermappar",
                          "sortera i årsmappar efter dokumentets datum")
        datecard.grid(row=2, column=0, sticky="ew", padx=T.PAD, pady=(T.GAP, 0))
        db = datecard.body
        db.columnconfigure(3, weight=1)

        self.var_date_on = tk.BooleanVar(value=self.settings.get("date_enabled", False))
        ttk.Checkbutton(db, text="Lägg filer i undermappar efter datum",
                        style="Card.TCheckbutton", variable=self.var_date_on,
                        command=self._on_date_toggle).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=8, pady=(6, 2))

        ttk.Label(db, text="Standardmall:", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", padx=8, pady=2)
        self.date_combo = ttk.Combobox(
            db, state="readonly", width=34,
            values=[e for t, e in SUBFOLDER_TEMPLATES if t])
        self.date_combo.grid(row=1, column=1, sticky="w", pady=2)
        _mallar = [t for t, _ in SUBFOLDER_TEMPLATES if t]
        _nu = self.settings.get("date_default_template", "{år}")
        self.date_combo.current(_mallar.index(_nu) if _nu in _mallar else 0)
        self.date_combo.bind("<<ComboboxSelected>>",
                             lambda e: self._collect_settings())
        ttk.Label(db, text="används av kategorier utan egen mall",
                  style="CardMuted.TLabel").grid(row=1, column=2, columnspan=2,
                                                 sticky="w", padx=10)

        self.var_year_sub = tk.BooleanVar(
            value=self.settings.get("year_subfolder", True))
        ttk.Checkbutton(db, text="Årsmapp från filens datum (automatiskt, "
                        "t.ex. Pilkington/2022)",
                        style="Card.TCheckbutton",
                        variable=self.var_year_sub).grid(
            row=3, column=0, columnspan=4, sticky="w", padx=8,
            pady=(2, T.INNER))
        ttk.Label(db, text="Utan datum:", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", padx=8, pady=(2, T.INNER))
        self.var_date_fb = tk.StringVar(
            value=self.settings.get("date_fallback", "none"))
        fbrad = ttk.Frame(db, style="CardInner.TFrame")
        fbrad.grid(row=2, column=1, columnspan=3, sticky="w", pady=(2, T.INNER))
        for txt, val in (("lägg i kategorimappen", "none"),
                         ("mappen \"Utan datum\"", "unknown"),
                         ("använd filens tid", "filedate")):
            ttk.Radiobutton(fbrad, text=txt, value=val,
                            style="Card.TRadiobutton",
                            variable=self.var_date_fb,
                            command=self._collect_settings).pack(
                side="left", padx=(0, 14))

        # -- undantagsmappar (ANVÄNDARORDER 2026-08-26) ---------------------
        # Mappar som hoppas över även när de ligger inuti en inmapp,
        # t.ex. Arkiv/ eller redan sorterade projektundermappar.
        exccard = T.card(g, "Undantagna mappar",
                         "hoppas över även när de ligger inuti inmapparna")
        exccard.grid(row=3, column=0, sticky="ew", padx=T.PAD, pady=(T.GAP, 0))
        exb = exccard.body
        exb.columnconfigure(0, weight=1)
        self.exc_list = tk.Listbox(exb, height=3, exportselection=False,
                                   activestyle="none", borderwidth=0,
                                   background=self.C["surface"],
                                   foreground=self.C["text"],
                                   highlightthickness=0, font=T.f_base)
        self.exc_list.grid(row=0, column=0, sticky="nsew",
                           padx=(T.INNER, 0), pady=T.INNER)
        exbtn = ttk.Frame(exb, style="CardInner.TFrame")
        exbtn.grid(row=0, column=1, sticky="n", padx=T.INNER, pady=T.INNER)
        ttk.Button(exbtn, text="Lägg till…", width=12,
                   command=self._add_exclude_dir).pack(fill="x")
        ttk.Button(exbtn, text="Ta bort", width=12,
                   command=self._remove_exclude_dir).pack(fill="x", pady=6)
        self._refresh_excludes()

        # -- ignorera filer (ANVÄNDARORDER 2026-08-26) ---------------------
        # Filer som innehåller vissa ord, eller heter något som mönster
        # träffar, hoppas över helt - även inne i skanningsmapparna.
        igncard = T.card(g, "Ignorera filer",
                         "innehåller ordet eller heter som mönstret")
        igncard.grid(row=4, column=0, sticky="ew", padx=T.PAD, pady=(T.GAP, 0))
        igb = igncard.body
        igb.columnconfigure(0, weight=1)
        igb.columnconfigure(1, weight=1)
        ttk.Label(igb, text="Ord i innehållet", style="CardMuted.TLabel"
                  ).grid(row=0, column=0, sticky="w", padx=(T.INNER, 0), pady=(T.INNER, 0))
        ttk.Label(igb, text="Filnamnsmönster", style="CardMuted.TLabel"
                  ).grid(row=0, column=1, sticky="w", padx=(T.GAP, 0), pady=(T.INNER, 0))
        self.ign_word_list = tk.Listbox(igb, height=3, exportselection=False,
                                        activestyle="none", borderwidth=0,
                                        background=self.C["surface"],
                                        foreground=self.C["text"],
                                        highlightthickness=0, font=T.f_base)
        self.ign_word_list.grid(row=1, column=0, sticky="nsew",
                                padx=(T.INNER, T.GAP // 2), pady=(2, T.INNER))
        self.ign_glob_list = tk.Listbox(igb, height=3, exportselection=False,
                                        activestyle="none", borderwidth=0,
                                        background=self.C["surface"],
                                        foreground=self.C["text"],
                                        highlightthickness=0, font=T.f_base)
        self.ign_glob_list.grid(row=1, column=1, sticky="nsew",
                                padx=(T.GAP // 2, T.INNER), pady=(2, T.INNER))
        ignbtn = ttk.Frame(igb, style="CardInner.TFrame")
        ignbtn.grid(row=2, column=0, columnspan=2, sticky="w",
                    padx=T.INNER, pady=(0, T.INNER))
        ttk.Button(ignbtn, text="+ Ord…",
                   command=self._add_ignore_word).pack(side="left")
        ttk.Button(ignbtn, text="+ Mönster…",
                   command=self._add_ignore_glob).pack(side="left", padx=6)
        ttk.Button(ignbtn, text="Ta bort markering",
                   command=lambda: (self._remove_ignore("ignore_words"),
                                    self._remove_ignore("ignore_filename_globs"))
                   ).pack(side="left", padx=6)
        # Individuellt markerade filer (känns igen på innehållet, ANVÄNDAR-
        # ORDER 2026-09-24). Markeras via Ignorera-knappen i granskningsrutan.
        ttk.Label(igb, text="Individuellt ignorerade filer (känns igen på innehållet)",
                  style="CardMuted.TLabel").grid(row=3, column=0, columnspan=2,
                  sticky="w", padx=(T.INNER, 0), pady=(4, 0))
        self.ign_file_list = tk.Listbox(igb, height=3, exportselection=False,
                                        activestyle="none", borderwidth=0,
                                        background=self.C["surface"],
                                        foreground=self.C["text"],
                                        highlightthickness=0, font=T.f_base)
        self.ign_file_list.grid(row=4, column=0, columnspan=2, sticky="ew",
                                padx=(T.INNER, T.INNER), pady=(2, 2))
        igb2 = ttk.Frame(igb, style="CardInner.TFrame")
        igb2.grid(row=5, column=0, columnspan=2, sticky="w",
                  padx=T.INNER, pady=(0, T.INNER))
        ttk.Button(igb2, text="Sluta ignorera markerad",
                   command=self._remove_ignored_file).pack(side="left")
        self._refresh_ignores()

        # -- start och systemfält --
        syscard = T.card(g, "Start och systemfält")
        syscard.grid(row=5, column=0, sticky="ew", padx=T.PAD, pady=(T.GAP, T.PAD))
        sysbox = syscard.body
        for c in range(4):
            sysbox.columnconfigure(c, weight=1)

        self.var_autostart = tk.BooleanVar(value=autostart_enabled())
        self.var_startmin = tk.BooleanVar(value=self.settings.get("start_minimized", False))
        self.var_tray = tk.BooleanVar(value=self.settings.get("tray_enabled", True))
        self.var_close_tray = tk.BooleanVar(value=self.settings.get("close_to_tray", True))
        self.var_autowatch = tk.BooleanVar(value=self.settings.get("autowatch_on_start", False))
        self.var_notify = tk.BooleanVar(value=self.settings.get("notify", True))
        self.var_checkupd = tk.BooleanVar(value=self.settings.get("check_updates", True))
        self.var_autoupd = tk.BooleanVar(value=self.settings.get("auto_update", False))

        cb_auto = ttk.Checkbutton(sysbox, text="Starta automatiskt med datorn",
                                  style="Card.TCheckbutton",
                                  variable=self.var_autostart,
                                  command=self._toggle_autostart)
        cb_auto.grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 2))
        if not autostart_supported():
            cb_auto.state(["disabled"])
        ttk.Checkbutton(sysbox, text="Starta bevakningen direkt",
                        style="Card.TCheckbutton",
                        variable=self.var_autowatch).grid(row=0, column=2, columnspan=2,
                                                          sticky="w", padx=8, pady=(6, 2))
        cb_tray = ttk.Checkbutton(sysbox, text="Visa ikon i systemfältet",
                        style="Card.TCheckbutton",
                                  variable=self.var_tray)
        cb_tray.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=2)
        ttk.Checkbutton(sysbox, text="Starta minimerad i systemfältet",
                        style="Card.TCheckbutton",
                        variable=self.var_startmin).grid(row=1, column=2, columnspan=2,
                                                         sticky="w", padx=8, pady=2)
        ttk.Checkbutton(sysbox, text="Krysset minimerar i stället för att avsluta",
                        style="Card.TCheckbutton",
                        variable=self.var_close_tray).grid(row=2, column=0, columnspan=2,
                                                           sticky="w", padx=8, pady=2)
        ttk.Checkbutton(sysbox, text="Visa notis när filer sorterats",
                        style="Card.TCheckbutton",
                        variable=self.var_notify).grid(row=2, column=2, columnspan=2,
                                                       sticky="w", padx=8, pady=2)
        ttk.Checkbutton(sysbox, text="Sök uppdateringar på GitHub vid start",
                        style="Card.TCheckbutton",
                        variable=self.var_checkupd).grid(row=3, column=0, columnspan=2,
                                                         sticky="w", padx=8, pady=2)
        ttk.Checkbutton(sysbox, text="Installera uppdateringar automatiskt",
                        style="Card.TCheckbutton",
                        variable=self.var_autoupd).grid(row=3, column=2, columnspan=2,
                                                        sticky="w", padx=8, pady=2)

        # -- tema: ljust eller mörkt, växlas live --
        themrad = ttk.Frame(sysbox, style="CardInner.TFrame")
        themrad.grid(row=3, column=0, columnspan=4, sticky="w",
                     padx=8, pady=(8, 2))
        self.var_theme = tk.StringVar(value=self.settings.get("theme", "ljus"))
        ttk.Label(themrad, text="Tema:", style="Card.TLabel").pack(side="left")
        for txt, val in (("Ljust", "ljus"), ("Mörkt", "mork")):
            ttk.Radiobutton(themrad, text=txt, value=val,
                            style="Card.TRadiobutton",
                            variable=self.var_theme,
                            command=self._on_theme_radio).pack(
                side="left", padx=(8, 0))
        self.var_contrast = tk.StringVar(
            value=self.settings.get("contrast", "normal"))
        ttk.Label(themrad, text="   Kontrast:", style="Card.TLabel"
                  ).pack(side="left")
        for txt, val in (("Normal", "normal"), ("Hög", "high")):
            ttk.Radiobutton(themrad, text=txt, value=val,
                            style="Card.TRadiobutton",
                            variable=self.var_contrast,
                            command=self._on_theme_radio).pack(
                side="left", padx=(8, 0))

        extra = ttk.Frame(sysbox, style="CardInner.TFrame")
        extra.grid(row=4, column=0, columnspan=4, sticky="w",
                   padx=8, pady=(8, T.INNER))
        ttk.Button(extra, text="Skapa genväg på skrivbordet",
                   command=self._make_shortcut).pack(side="left")
        ttk.Button(extra, text="Spara ikonfil",
                   command=self._save_icon).pack(side="left", padx=6)
        if not tray_available():
            cb_tray.state(["disabled"])
            ttk.Label(extra, text="Systemfältet kräver:  pip install pystray",
                      style="CardMuted.TLabel",
                      foreground=self.C["warn"]).pack(side="left", padx=12)
        # 1.1.0: språk / schema / taggning / uppslag
        self.var_lang = tk.StringVar(value=self.settings.get("ui_language", "sv"))
        self.var_tagpdf = tk.BooleanVar(value=self.settings.get("tag_pdf_metadata", True))
        self.var_orglookup = tk.BooleanVar(value=self.settings.get("orgnr_lookup", False))
        self.var_sched = tk.BooleanVar(value=self.settings.get("schedule_enabled", False))
        self.var_schedtime = tk.StringVar(value=self.settings.get("schedule_time", "07:00"))
        rad5 = ttk.Frame(sysbox, style="CardInner.TFrame")
        rad5.grid(row=5, column=0, columnspan=4, sticky="w", padx=8, pady=(6, 2))
        ttk.Label(rad5, text="Språk:", style="Card.TLabel").pack(side="left")
        ttk.Combobox(rad5, textvariable=self.var_lang, values=["sv", "en"],
                     state="readonly", width=5).pack(side="left", padx=(4, 2))
        ttk.Label(rad5, text="(gäller vid omstart)",
                  style="CardMuted.TLabel").pack(side="left")
        ttk.Checkbutton(rad5, text="Schemalagd sortering",
                        style="Card.TCheckbutton",
                        variable=self.var_sched).pack(side="left", padx=(16, 2))
        ttk.Label(rad5, text="kl.", style="Card.TLabel").pack(side="left")
        ttk.Entry(rad5, textvariable=self.var_schedtime, width=6).pack(side="left")
        rad6 = ttk.Frame(sysbox, style="CardInner.TFrame")
        rad6.grid(row=6, column=0, columnspan=4, sticky="w", padx=8, pady=(2, 6))
        ttk.Checkbutton(rad6, text="Skriv kategori som PDF-metadata vid sortering",
                        style="Card.TCheckbutton",
                        variable=self.var_tagpdf).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(rad6, text="Slå upp okända avsändare via nätet (org.nr)",
                        style="Card.TCheckbutton",
                        variable=self.var_orglookup).pack(side="left")
        self._update_pills()

    def _update_stats(self, sorted_n: Optional[int] = None,
                      errors: Optional[int] = None) -> None:
        """Håll de tre siffrorna i handlingsraden aktuella."""
        if not hasattr(self, "stat_labels"):
            return
        if sorted_n is not None:
            self._stat_sorted = sorted_n
        if errors is not None:
            self._stat_errors = errors
        vals = {
            "sorted": getattr(self, "_stat_sorted", 0),
            "queue": len(self.queue),
            "errors": getattr(self, "_stat_errors", 0),
        }
        tones = {"sorted": "ok", "queue": "warn", "errors": "err"}
        for key, lbl in self.stat_labels.items():
            n = vals[key]
            lbl.configure(text=str(n))
            # Nollor tonas ned; siffror som betyder något får sin färg.
            lbl.configure(foreground=(self.C[tones[key]] if n
                                      else self.C["text_faint"]))

    def _ask_conflict(self, src: Path, target: Path, kind: str) -> str:
        """REQ-N4: visa dubblettfrågan och vänta på svaret.

        DÖDLÄSNINGSSKYDD: anropas vi från UI-tråden (t.ex. "Sortera nu"
        eller granskningskön) får dialogen visas direkt - att posta den
        till kön och vänta skulle blockera i 120 s, eftersom kön pumpas
        av samma tråd. Workertrådar postar och väntar som förr.
        """
        return _conflict_ask_impl(self, src, target, kind)

    def _on_theme_radio(self) -> None:
        self._set_theme(self.var_theme.get() == "mork",
                        contrast=self.var_contrast.get())

    def _set_theme(self, dark: bool, contrast: str = "normal") -> None:
        """Byt tema live: ttk-stilarna är namngivna och ritas om direkt;
        de råa Tk-widgetarna (listor, logg, textfält) får nya färger här."""
        if (bool(getattr(self.theme, "dark", False)) == dark
                and getattr(self.theme, "contrast", "normal") == contrast):
            return
        self.settings["theme"] = "mork" if dark else "ljus"
        self.settings["contrast"] = contrast
        save_settings(self.settings)
        self.theme = Theme(self.root, self.ttk, dark=dark, contrast=contrast)
        self.C = self.theme.c
        self._retint_raw()
        self._update_pills()
        self.root.after(60, lambda: dark_titlebar(self.root, bool(dark)))
        self._log(f"Tema: {'mörkt' if dark else 'ljust'}, "
                  f"kontrast: {contrast}.", "info")

    def _retint_raw(self) -> None:
        """Färglägg om råa Tk-widgets efter temabyte (de följer inte ttk)."""
        c = self.C
        try:
            self.in_list.configure(
                background=c["surface"], foreground=c["text"],
                selectbackground=c["accent_light"],
                selectforeground=c["accent_dark"])
        except Exception:
            pass
        try:
            self.logbox.configure(background=c["surface"],
                                  foreground=c["text"],
                                  selectbackground=c["accent_light"])
            self.logbox.tag_configure("info", foreground=c["text"])
            self.logbox.tag_configure("ok", foreground=c["ok"])
            self.logbox.tag_configure("warn", foreground=c["warn"])
            self.logbox.tag_configure("err", foreground=c["err"])
            self.logbox.tag_configure("time", foreground=c["text_faint"])
        except Exception:
            pass
        try:
            self.json_text.configure(background=c["surface"],
                                     foreground=c["text"],
                                     insertbackground=c["text"],
                                     selectbackground=c["accent_light"])
        except Exception:
            pass
        try:
            t = self.help_text
            t.configure(background=c["surface"], foreground=c["text"])
            t.tag_configure("h1", foreground=c["accent_dark"])
            t.tag_configure("h2", foreground=c["accent_dark"])
            t.tag_configure("code", background=c["bg"],
                            foreground=c["accent_dark"])
            t.tag_configure("note", foreground=c["text_muted"])
        except Exception:
            pass
        for tree in ("cat_tree", "kw_tree", "q_tree", "h_tree"):
            try:
                self.theme.zebra(getattr(self, tree))
            except Exception:
                pass

    def _warm_patterns(self) -> None:
        """Förkompilera alla stödordsmönster en gång (snabbhet, rond 5):
        första sorteringen slipper kompilera mönster mitt i svepet."""
        for cat in self.rules.categories:
            for kw in cat["keywords"]:
                _cached_pattern(kw)

    def _update_pills(self) -> None:
        """Statuspiller på handlingsraden: bevakning och testkörning."""
        if not hasattr(self, "pill_dry"):
            return
        watching = bool(self.watcher and self.watcher.running)
        self.lbl_watch.configure(
            text="● Bevakning: PÅ" if watching else "● Bevakning: AV",
            style="PillOk.TLabel" if watching else "PillMuted.TLabel")
        if self.var_dry.get():
            self.pill_dry.grid()
        else:
            self.pill_dry.grid_remove()

    def _on_strictness(self, initial: bool = False) -> None:
        """Nivåvalet fyller i fälten och låser dem, utom vid "Egen"."""
        idx = self.strict_combo.current()
        level = STRICT_ORDER[idx] if 0 <= idx < len(STRICT_ORDER) else "normal"
        self.var_strict.set(level)
        preset = STRICTNESS_LEVELS.get(level, {})

        if level != "egen":
            self.var_minscore.set(f"{preset['min_score']:g}")
            self.var_margin.set(f"{preset['ambiguity_margin']:g}")
            self.var_minkw.set(str(preset["min_keywords"]))
            self.var_ratio.set(f"{preset['score_ratio']:g}")
            self.var_mintext.set(str(preset["min_text_chars"]))
            self.var_strong.set(bool(preset["require_strong"]))
            self.var_anchor.set(bool(preset.get("require_anchor", False)))
            self.var_rejrec.set(bool(preset.get("reject_recipient_only", True)))

        state = "normal" if level == "egen" else "disabled"
        for child in self.strict_detail.winfo_children():
            try:
                child.configure(state=state)
            except Exception:
                pass

        self.lbl_strict.configure(text=preset.get("hint", ""))
        if not initial:
            self._collect_settings()
            self._log(f"Strikthet: {preset.get('label', level)}", "info")

    def _on_date_toggle(self) -> None:
        """Slå på/av datumsorteringen och berätta vad det innebär."""
        self._collect_settings()
        if self.var_date_on.get():
            mall = self.settings.get("date_default_template", "{år}")
            ex = render_subfolder(mall, date.today())
            self._log(f"Datumsortering på - nya filer hamnar i "
                      f"undermappar som {ex}. Redan sorterade filer "
                      f"flyttas inte.", "ok")
        else:
            self._log("Datumsortering av - filer läggs direkt i "
                      "kategorimappen.", "info")
        if hasattr(self, "cat_tree"):
            self._on_cat_select()

    def _pick(self, var) -> None:
        cur = var.get() or str(Path.home())
        chosen = self.filedialog.askdirectory(initialdir=cur, parent=self.root)
        if chosen:
            var.set(chosen)

    # -- inmappar ---------------------------------------------------------
    def input_dirs(self) -> List[str]:
        return list(self.settings.get("input_dirs") or [])

    def _refresh_input_list(self) -> None:
        self.in_list.delete(0, "end")
        for d in self.input_dirs():
            exists = Path(d).is_dir()
            self.in_list.insert("end", d if exists else f"{d}   (saknas)")
            if not exists:
                self.in_list.itemconfigure("end", foreground="#b42318")
        if not self.input_dirs():
            self.in_list.insert("end", "  Ingen mapp vald - klicka \"Lägg till…\"")
            self.in_list.itemconfigure(0, foreground="#888")

    def _add_input_dir(self) -> None:
        chosen = self.filedialog.askdirectory(
            initialdir=str(Path.home()), parent=self.root,
            title="Välj en mapp som ska bevakas")
        if not chosen:
            return
        dirs = self.input_dirs()
        key = os.path.normcase(os.path.abspath(chosen))
        if any(os.path.normcase(os.path.abspath(d)) == key for d in dirs):
            self.messagebox.showinfo(APP_NAME, "Mappen bevakas redan.", parent=self.root)
            return
        out = self.var_out.get().strip()
        if out:
            if key == os.path.normcase(os.path.abspath(out)):
                self.messagebox.showwarning(
                    APP_NAME, "In- och utmapp får inte vara samma mapp.",
                    parent=self.root)
                return
            # Fånga överlappet redan här, så att användaren får veta det
            # när de pekar ut mappen - inte först när de trycker Sortera.
            ny, ut = Path(chosen), Path(out)
            if _inuti(ut, ny):
                self.messagebox.showwarning(
                    APP_NAME,
                    f"Utmappen ligger inuti den här mappen:\n\n"
                    f"    {out}\n\nDå skulle redan sorterade filer hittas "
                    f"igen och sorteras om. Välj en annan inmapp, eller "
                    f"flytta utmappen utanför.", parent=self.root)
                return
            if _inuti(ny, ut):
                self.messagebox.showwarning(
                    APP_NAME,
                    f"Mappen ligger inuti utmappen:\n\n    {out}\n\n"
                    f"Nya filer skulle landa i det appen redan betraktar "
                    f"som färdigsorterat.", parent=self.root)
                return
        dirs.append(chosen)
        self.settings["input_dirs"] = dirs
        self.settings["input_dir"] = dirs[0]
        save_settings(self.settings)
        self._refresh_input_list()
        self._log(f"Lade till inmapp: {chosen}", "info")
        if self.watcher and self.watcher.running:
            self._restart_watch()

    def _remove_input_dir(self) -> None:
        sel = list(self.in_list.curselection())
        dirs = self.input_dirs()
        if not sel or not dirs:
            return
        for i in sorted(sel, reverse=True):
            if i < len(dirs):
                self._log(f"Tog bort inmapp: {dirs[i]}", "info")
                dirs.pop(i)
        self.settings["input_dirs"] = dirs
        self.settings["input_dir"] = dirs[0] if dirs else ""
        save_settings(self.settings)
        self._refresh_input_list()
        if self.watcher and self.watcher.running:
            self._restart_watch()

    def _open_selected_input(self) -> None:
        sel = self.in_list.curselection()
        dirs = self.input_dirs()
        if sel and sel[0] < len(dirs):
            open_externally(Path(dirs[sel[0]]))

    # -- ignorera filer -----------------------------------------------------
    def _refresh_ignores(self) -> None:
        self.ign_word_list.delete(0, "end")
        for w in self.settings.get("ignore_words", []):
            self.ign_word_list.insert("end", w)
        self.ign_glob_list.delete(0, "end")
        for g in self.settings.get("ignore_filename_globs", []):
            self.ign_glob_list.insert("end", g)
        fl = getattr(self, "ign_file_list", None)
        if fl is not None:
            fl.delete(0, "end")
            for post in list_ignored_files():
                fl.insert("end", f"{post.get('name', '?')}  "
                          f"({post.get('added', '')[:16].replace('T', ' ')})")

    def _remove_ignored_file(self) -> None:
        """Sluta ignorera: markeringen tas bort och filen sorteras igen."""
        fl = getattr(self, "ign_file_list", None)
        if fl is None:
            return
        sel = list(fl.curselection())
        if not sel:
            return
        poster = list_ignored_files()
        bort = 0
        for idx in sorted(sel, reverse=True):
            if idx < len(poster):
                if unignore_file(poster[idx].get("hash", "")):
                    bort += 1
        if bort:
            self._refresh_ignores()
            self._log(f"{bort} fil(er) ignoreras inte längre - "
                      "de sorteras igen vid nästa körning", "info")

    def _add_ignore_word(self) -> None:
        w = self.simpledialog.askstring(
            APP_NAME, "Ord som gör att en fil hoppas över:",
            parent=self.root)
        if not w or not normalize(w):
            return
        lst = list(self.settings.get("ignore_words", []))
        if w not in lst:
            lst.append(w)
        self.settings["ignore_words"] = lst
        save_settings(self.settings)
        self._refresh_ignores()
        self._log(f"Ignoreringsord tillagt: {w}", "info")

    def _add_ignore_glob(self) -> None:
        g = self.simpledialog.askstring(
            APP_NAME, "Filnamnsmönster som hoppas över (t.ex. *offert*):",
            parent=self.root)
        if not g:
            return
        lst = list(self.settings.get("ignore_filename_globs", []))
        if g not in lst:
            lst.append(g)
        self.settings["ignore_filename_globs"] = lst
        save_settings(self.settings)
        self._refresh_ignores()
        self._log(f"Ignoreringsmönster tillagt: {g}", "info")

    def _remove_ignore(self, which: str) -> None:
        lst = list(self.settings.get(which, []))
        lb = (self.ign_word_list if which == "ignore_words"
              else self.ign_glob_list)
        sel = list(lb.curselection())
        if not sel or not lst:
            return
        for i in sorted(sel, reverse=True):
            if i < len(lst):
                self._log(f"Ignoreringsregel borttagen: {lst[i]}", "info")
                lst.pop(i)
        self.settings[which] = lst
        save_settings(self.settings)
        self._refresh_ignores()

    # -- undantagsmappar ---------------------------------------------------
    def _refresh_excludes(self) -> None:
        self.exc_list.delete(0, "end")
        for d in self.settings.get("exclude_dirs", []):
            self.exc_list.insert("end", d)

    def _add_exclude_dir(self) -> None:
        chosen = self.filedialog.askdirectory(
            parent=self.root, title="Välj mapp som ska hoppas över")
        if not chosen:
            return
        exc = list(self.settings.get("exclude_dirs", []))
        key = os.path.normcase(os.path.abspath(chosen))
        if any(os.path.normcase(os.path.abspath(e)) == key for e in exc):
            self.messagebox.showinfo(APP_NAME, "Mappen är redan undantagen.",
                                     parent=self.root)
            return
        exc.append(chosen)
        self.settings["exclude_dirs"] = exc
        save_settings(self.settings)
        self._refresh_excludes()
        self._log(f"Undantagen mapp (hoppas över): {chosen}", "info")
        if self.watcher and self.watcher.running:
            self._restart_watch()

    def _remove_exclude_dir(self) -> None:
        sel = list(self.exc_list.curselection())
        exc = list(self.settings.get("exclude_dirs", []))
        if not sel or not exc:
            return
        for i in sorted(sel, reverse=True):
            if i < len(exc):
                self._log(f"Undantag borttaget: {exc[i]}", "info")
                exc.pop(i)
        self.settings["exclude_dirs"] = exc
        save_settings(self.settings)
        self._refresh_excludes()
        if self.watcher and self.watcher.running:
            self._restart_watch()

    def open_output(self) -> None:
        out = (self.var_out.get() or "").strip()
        if out and Path(out).is_dir():
            open_externally(Path(out))
        else:
            self.messagebox.showinfo(APP_NAME, "Ingen giltig utmapp vald än.",
                                     parent=self.root)

    def all_input_files(self) -> List[Path]:
        """Alla PDF-filer i samtliga bevakade mappar, utan dubbletter.

        Undantagsmappar hoppas över även inuti inmapparna.
        """
        seen, files = set(), []
        exc = self.settings.get("exclude_dirs", [])
        for d in self.input_dirs():
            for f in list_pdfs(Path(d), self.settings.get("recursive", False), exc):
                key = os.path.normcase(os.path.abspath(str(f)))
                if key not in seen:
                    seen.add(key)
                    files.append(f)
        return files

    def _collect_settings(self) -> bool:
        """Läs av GUI:t till self.settings. Returnerar False vid fel."""
        def num(var, default):
            try:
                return float(var.get().replace(",", "."))
            except (ValueError, AttributeError):
                return default
        tidigare_ocr = bool(self.settings.get("ocr_enabled", True))
        tidigare_sidor = self.settings.get("max_pages_text", 0)
        tidigare_kvalitet = self.settings.get("ocr_quality", "high")
        self.settings.update({
            "output_dir": self.var_out.get().strip(),
            "recursive": bool(self.var_recursive.get()),
            "learned_matching": bool(self.var_learned.get()),
            "year_subfolder": bool(self.var_year_sub.get()),
            "ask_when_unsure": bool(self.var_ask.get()),
            "ocr_enabled": bool(self.var_ocr.get()),
            "ocr_quality": ("high" if self.var_ocr_quality.get()
                            else "standard"),
            "dry_run": bool(self.var_dry.get()),
            "action": self.var_action.get(),
            "popup_immediately": bool(self.var_popup.get()),
            "rescan_after_learn": bool(self.var_rescan.get()),
            "unmatched_folder": self.var_unmatched.get().strip(),
            "min_score": num(self.var_minscore, 1.0),
            "ambiguity_margin": num(self.var_margin, 0.5),
            "strictness": self.var_strict.get(),
            "min_keywords": max(1, int(num(self.var_minkw, 1))),
            "score_ratio": max(1.0, num(self.var_ratio, 1.0)),
            "min_text_chars": max(0, int(num(self.var_mintext, 0))),
            "require_strong": bool(self.var_strong.get()),
            "require_anchor": bool(self.var_anchor.get()),
            "reject_recipient_only": bool(self.var_rejrec.get()),
            "tray_enabled": bool(self.var_tray.get()),
            "close_to_tray": bool(self.var_close_tray.get()),
            "start_minimized": bool(self.var_startmin.get()),
            "autowatch_on_start": bool(self.var_autowatch.get()),
            "notify": bool(self.var_notify.get()),
            "autostart": bool(self.var_autostart.get()),
            "check_updates": bool(self.var_checkupd.get()),
            "auto_update": bool(self.var_autoupd.get()),
        })
        if hasattr(self, "var_lang"):
            self.settings.update({
                "ui_language": self.var_lang.get(),
                "tag_pdf_metadata": bool(self.var_tagpdf.get()),
                "orgnr_lookup": bool(self.var_orglookup.get()),
                "schedule_enabled": bool(self.var_sched.get()),
                "schedule_time": self.var_schedtime.get().strip() or "07:00",
            })
        if hasattr(self, "var_date_on"):
            idx = self.date_combo.current()
            mallar = [t for t, _ in SUBFOLDER_TEMPLATES if t]
            self.settings.update({
                "date_enabled": bool(self.var_date_on.get()),
                "date_default_template": mallar[idx] if 0 <= idx < len(mallar) else "{år}",
                "date_fallback": self.var_date_fb.get(),
            })
        # Ändras hur filerna läses blir den cachade texten inaktuell.
        if (bool(self.var_ocr.get()) != tidigare_ocr
                or self.settings["max_pages_text"] != tidigare_sidor
                or self.settings.get("ocr_quality", "high") != tidigare_kvalitet):
            TEXT_CACHE.clear()
        save_settings(self.settings)
        self._update_pills()
        session_log("inställningar",
                    f"Sparade: strikthet={self.settings.get('strictness')}, "
                    f"min_keywords={self.settings.get('min_keywords')}, "
                    f"action={self.settings.get('action')}, "
                    f"dry_run={self.settings.get('dry_run')}, "
                    f"recursive={self.settings.get('recursive')}, "
                    f"ocr={self.settings.get('ocr_enabled')}, "
                    f"tray={self.settings.get('tray_enabled')}, "
                    f"close_to_tray={self.settings.get('close_to_tray')}, "
                    f"exkluderade={list(self.settings.get('exclude_dirs', []))}")
        return True

    def _validate_dirs(self, quiet: bool = False) -> bool:
        self._collect_settings()

        def warn(msg: str) -> bool:
            session_log("mappar", f"Mappkontroll stoppar: {msg}", "warn")
            if not quiet:
                self.messagebox.showwarning(APP_NAME, msg, parent=self.root)
            return False

        dirs = [d for d in self.input_dirs() if Path(d).is_dir()]
        if not self.input_dirs():
            return warn("Lägg till minst en inmapp som ska bevakas.")
        if not dirs:
            return warn("Ingen av de valda inmapparna finns kvar på disken.")
        if not self.settings["output_dir"]:
            return warn("Välj en utmapp.")

        outdir = Path(self.settings["output_dir"])
        try:
            outdir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            if not quiet:
                self.messagebox.showerror(APP_NAME, f"Kan inte skapa utmappen:\n{exc}",
                                          parent=self.root)
            return False
        # In- och utmapp får inte överlappa. Tre fall, alla lika illa:
        #
        #   samma mapp      filen flyttas till sig själv
        #   ut inuti in     med "läs undermappar" hittas redan sorterade
        #                   filer igen vid nästa svep och sorteras om, i
        #                   all oändlighet
        #   in inuti ut     nya filer landar i något som appen behandlar
        #                   som färdigsorterat
        #
        # Den mellersta smyger sig lätt på: "Skannat/" som inmapp och
        # "Skannat/Sorterat/" som utmapp känns fullkomligt rimligt.
        try:
            resolved_out = outdir.resolve()
            for d in dirs:
                rd = Path(d).resolve()
                if rd == resolved_out:
                    return warn(f"In- och utmapp får inte vara samma mapp:\n{d}")
                if _inuti(resolved_out, rd):
                    djup = "" if not self.settings.get("recursive") else (
                        "\n\nEftersom \"Läs även undermappar\" är påslaget "
                        "skulle appen hitta de redan sorterade filerna igen "
                        "vid nästa svep och sortera om dem i all oändlighet.")
                    return warn(
                        f"Utmappen ligger inuti inmappen:\n\n"
                        f"    in:  {d}\n    ut:  {outdir}\n\n"
                        f"Välj en utmapp som ligger utanför inmappen.{djup}")
                if _inuti(rd, resolved_out):
                    return warn(
                        f"Inmappen ligger inuti utmappen:\n\n"
                        f"    in:  {d}\n    ut:  {outdir}\n\n"
                        f"Nya filer skulle landa i mappen appen redan "
                        f"betraktar som färdigsorterad. Välj en inmapp "
                        f"utanför utmappen.")
        except OSError:
            pass
        return True

    # -- körning -----------------------------------------------------------
    def _undermapps_pdf_count(self) -> int:
        """Antal PDF-filer i undermappar till inmapparna (ej toppnivå).

        Används för att upptäcka 'tom mapp'-scenariot: allt ligger en
        nivå ner. Återanvänder list_pdfs så att undantagsmappar och
        ignoreringsregler gäller lika dan här.
        """
        exc = self.settings.get("exclude_dirs", []) or []
        total = 0
        for d in self.input_dirs():
            rec = list_pdfs(Path(d), True, exc)
            topp = list_pdfs(Path(d), False, exc)
            total += max(0, len(rec) - len(topp))
            if total >= 500:
                break
        return total

    def _sort_now(self) -> None:
        self._ui("Sortera nu")
        if self._busy:
            self._h("sortering", "Sortera nu ignorerad - en sortering pågår redan",
                    "warn")
            return
        if not self._validate_dirs():
            self._h("sortering", "Sortera nu stoppad - mapparna godkändes inte",
                    "warn")
            return
        files = self.all_input_files()
        if not files and not self.settings.get("recursive", True):
            # Screenshot-scenariot 2026-09-28: användaren pekade på en mapp
            # där allt ligger i undermappar. Fråga i stället för att bara
            # säga "inga filer".
            n_sub = self._undermapps_pdf_count()
            if n_sub:
                svar = self.messagebox.askyesno(
                    APP_NAME,
                    f"Det finns inga PDF-filer i toppnivån på de bevakade "
                    f"mapparna,\nmen {n_sub} st i undermappar.\n\n"
                    f"Söka i undermappar också?", parent=self.root)
                self._h("sortering", f"Undermappsfråga: {n_sub} PDF:er i "
                        f"undermappar -> svar {'ja' if svar else 'nej'}")
                if svar:
                    self.var_recursive.set(True)
                    self._collect_settings()
                    files = self.all_input_files()
        if not files:
            self._log("Inga PDF-filer i de bevakade mapparna.", "warn")
            return
        self._busy = True
        self.btn_sort.configure(state="disabled", text="Sorterar…")
        self.progress.configure(maximum=len(files), value=0)
        self.lbl_progress.configure(text="0 %")
        self._log(f"— Startar: {len(files)} filer "
                  f"{'(TESTKÖRNING)' if self.settings['dry_run'] else ''} —", "info")
        threading.Thread(target=self._sort_worker, args=(files,), daemon=True).start()

    def _sort_worker(self, files: List[Path]) -> None:
        # Parallell analys: PDF-läsningen är den långsamma delen och är
        # oberoende mellan filer, så flera läses samtidigt. Själva flytten
        # serialiserar motorn internt - "skriv aldrig över" gäller alltså
        # även när trådar tävlade om samma målnamn.
        total = len(files)
        workers = max(2, min(8, os.cpu_count() or 2))
        done = 0
        done_lock = threading.Lock()

        def job(path: Path) -> None:
            nonlocal done
            if not path.exists():
                return
            try:
                decision = self.engine.analyze(path)
                self._handle(decision, from_watch=False)
            except Exception as exc:
                self._log_threadsafe(f"{path.name}  ✖ {type(exc).__name__}: {exc}", "err")
            with done_lock:
                done += 1
                v = done
            self._post(lambda v=v: (
                self.progress.configure(value=v),
                self.lbl_progress.configure(text=f"{v * 100 // total} %")))

        # Hängningsskydd: även om något oväntat kastas här måste
        # _finish_run nås, annars förblir _busy sann och "Sortera nu"
        # låses för alltid.
        with LogContext("tid", f"batchsortering {total} filer, "
                        f"{workers} trådar"):
            try:
                with concurrent.futures.ThreadPoolExecutor(
                        max_workers=workers,
                        thread_name_prefix="pdfsorter-sort") as pool:
                    for _ in pool.map(job, files):
                        pass
            except Exception as exc:
                self._fel(exc, "batchsortering")
                self._log_threadsafe(f"Sorteringen avbröts: {exc}", "err")
            finally:
                self._post(self._finish_run)

    def _finish_run(self) -> None:
        self._busy = False
        self.btn_sort.configure(state="normal", text="Sortera nu")
        self.lbl_progress.configure(text="")
        self.engine.flush_rules()          # debouncade skrivningar i hamn
        self._log(f"    Textcache: {TEXT_CACHE.stats()}", "info")
        s = self.engine.stats
        self._log(f"— Klart: {s['sorted']} sorterade, {len(self.queue)} väntar på granskning, "
                  f"{s['error']} fel —", "info")
        sorted_n = s["sorted"]
        self._update_stats(sorted_n=sorted_n, errors=s["error"])
        self.engine.stats.clear()
        self._refresh_queue()
        self._refresh_categories()
        self._refresh_history()
        self._sync_tray()
        if sorted_n and self.settings.get("notify", True) and not self.visible:
            self._notify(f"{sorted_n} filer sorterade"
                         + (f", {len(self.queue)} väntar på granskning"
                            if self.queue else ""))
        if self.queue and self.settings.get("ask_when_unsure", True) and self.visible:
            self._process_queue()

    def _handle(self, decision: Decision, from_watch: bool) -> None:
        """Ta hand om ett beslut (körs i bakgrundstråd)."""
        name = decision.path.name
        if decision.status == "ignored":
            self._log_threadsafe(f"{name}  ⊘ {decision.reason} - lämnas orörd",
                                 "info")
            return
        if decision.status == "error":
            self._log_threadsafe(f"{name}  ✖ {decision.reason}", "err")
            return
        if decision.status == "auto":
            best = decision.best
            ok, msg = self.engine.apply(decision, best.name, best.matched, "auto")
            if ok:
                tag = " (OCR)" if decision.extraction.used_ocr else ""
                # Felsökningsdesign: logga VAR träffarna satt, så att en
                # felregisterad kategori syns direkt i loggen.
                zon = ", ".join(f"{w}:{best.zone_of(w)}"
                                for w in best.matched[:3])
                mp = getattr(best, "multipage", None)
                flersidig = f"  [flersidig: {', '.join(mp)}]" if mp else ""
                self._log_threadsafe(
                    f"{name}  →  {best.name}   poäng {best.score:g}{tag}  "
                    f"[{zon}]{flersidig}",
                    "ok")
                if from_watch:
                    self._post(self._sync_tray)
                    if not self.visible:
                        self._post(lambda n=name, c=best.name:
                                   self._notify(f"{n} → {c}"))
            else:
                self._log_threadsafe(f"{name}  ✖ {msg}", "err")
            return

        # osäker
        if not self.settings.get("ask_when_unsure", True):
            ok, msg = self.engine.send_to_unmatched(decision)
            self._log_threadsafe(f"{name}  ⚠ {decision.reason} → "
                                 f"{'_Osorterat' if ok else msg}", "warn")
            return

        key = str(decision.path)
        if key not in self._queued_paths:
            self._queued_paths.add(key)
            self.queue.append(decision)
        self._log_threadsafe(f"{name}  ⚠ osäker → granskning ({decision.reason})", "warn")
        self._post(self._refresh_queue)
        self._post(self._sync_tray)
        if from_watch and self.settings.get("popup_immediately", False):
            self._post(self.show_window)
            self._post(self._process_queue)
        elif from_watch and not self.visible:
            self._post(lambda n=name: self._notify(
                f"{n} behöver granskas - {len(self.queue)} i kön"))

    # ======================================================================
    # Bevakning
    # ======================================================================
    def _toggle_watch(self) -> None:
        self._ui("Bevaka på/av")
        if self.watcher and self.watcher.running:
            self._stop_watch()
        else:
            self._start_watch()

    def _start_watch(self, quiet: bool = False) -> bool:
        if not self._validate_dirs(quiet=quiet):
            return False
        dirs = [Path(d) for d in self.input_dirs() if Path(d).is_dir()]
        self.watcher = MultiFolderWatcher(
            dirs,
            on_file=self._on_watched_file,
            interval=float(self.settings.get("watch_interval", 5.0)),
            stable_seconds=float(self.settings.get("stable_seconds", 3.0)),
            recursive=bool(self.settings.get("recursive", False)),
            excludes=self.settings.get("exclude_dirs", []),
        )
        self.watcher.start()
        self.btn_watch.configure(text="Stoppa bevakning")
        self._update_pills()
        every = self.settings.get("watch_interval", 5)
        self._log(f"Bevakar {len(dirs)} mapp(ar) var {every:g}:e sekund:", "info")
        for d in dirs:
            self._log(f"    {d}", "info")
        if not self.settings.get("recursive", True):
            n_sub = self._undermapps_pdf_count()
            if n_sub:
                self._log(f"Obs: {n_sub} PDF-filer ligger i undermappar och "
                          "bevakas INTE.\nKryssa i 'Läs även undermappar' "
                          "i Inställningar för att ta med dem.", "warn")
        self._sync_tray()
        return True

    def _stop_watch(self) -> None:
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        self.btn_watch.configure(text="Starta bevakning")
        self._update_pills()
        self._log("Bevakning stoppad.", "info")
        self._sync_tray()

    def _restart_watch(self) -> None:
        """Starta om bevakningen så att ändrade mappar slår igenom."""
        if self.watcher and self.watcher.running:
            self.watcher.stop()
            self.watcher = None
            self._start_watch(quiet=True)

    def _on_watched_file(self, path: Path) -> None:
        session_log("bevaka", f"Ny stabil fil upptäckt: {path}")
        try:
            decision = self.engine.analyze(path)
            self._handle(decision, from_watch=True)
        except Exception as exc:
            self._fel(exc, f"bevaka {path.name}")
            self._log_threadsafe(f"{path.name}  ✖ {exc}", "err")

    # ======================================================================
    # Flik 2 - Matchningar
    # ======================================================================
    def _build_cats_tab(self) -> None:
        """Matchningsvyn: kategorier till vänster, deras stödord till höger.

        Allt går att göra härifrån - lägga till, ändra vikt och ta bort -
        utan att öppna någon JSON-fil.
        """
        tk, ttk = self.tk, self.ttk
        T = self.theme
        f = self.tab_cats
        f.columnconfigure(1, weight=1)
        f.rowconfigure(1, weight=1)

        # -- sökrad över hela fliken --
        bar = ttk.Frame(f, style="Card.TFrame")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew",
                 padx=T.PAD, pady=(T.PAD, 0))
        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, text="Sök stödord", style="CardKey.TLabel").grid(
            row=0, column=0, sticky="w", padx=(T.INNER, 0), pady=T.INNER)
        self.var_kwsearch = tk.StringVar()
        ent = ttk.Entry(bar, textvariable=self.var_kwsearch)
        ent.grid(row=0, column=1, sticky="ew", padx=10, pady=T.INNER)
        ent.bind("<KeyRelease>", lambda e: self._refresh_keyword_view())
        ttk.Button(bar, text="Rensa", style="CardLink.TButton",
                   command=lambda: (self.var_kwsearch.set(""),
                                    self._refresh_keyword_view())
                   ).grid(row=0, column=2)
        self.lbl_kwcount = ttk.Label(bar, text="", style="CardMuted.TLabel")
        self.lbl_kwcount.grid(row=0, column=3, padx=16)
        ttk.Separator(bar, orient="vertical").grid(row=0, column=4, sticky="ns",
                                                   pady=10)
        ttk.Button(bar, text="Exportera…", style="CardLink.TButton",
                   command=self._export).grid(row=0, column=5, padx=(12, 0))
        ttk.Button(bar, text="Importera…", style="CardLink.TButton",
                   command=self._import).grid(row=0, column=6, padx=(4, T.INNER))

        # -- vänster: kategorier --
        leftcard = T.card(f, "Kategorier")
        leftcard.grid(row=1, column=0, sticky="nsew",
                      padx=(T.PAD, T.GAP // 2), pady=T.GAP)
        left = leftcard.body
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        cat_cols = ("name", "count", "regel")
        self.cat_tree = ttk.Treeview(left, columns=cat_cols, show="headings",
                                     selectmode="browse", height=14)
        T.fit_columns(self.cat_tree, (
            ("name", "KATEGORI", 16, "w", True),
            ("count", "ORD", 3, "center", False),
            # Visar avvikelser från standard: "3 ord" eller "{år}". Utan
            # den måste man klicka på varje kategori för att se om någon
            # har egna regler.
            ("regel", "REGEL", 7, "w", False)))
        self.cat_tree.grid(row=0, column=0, sticky="nsew", padx=(1, 0), pady=(1, 0))
        self.cat_tree.bind("<<TreeviewSelect>>", lambda e: self._on_cat_select())
        # Ta bort en kategori med Delete-tangenten, som en bekväm genväg
        # vid sidan av knappen "Ta bort".
        self.cat_tree.bind("<Delete>", lambda e: self._cat_delete())
        self.theme.zebra(self.cat_tree)
        csb = ttk.Scrollbar(left, orient="vertical", command=self.cat_tree.yview)
        csb.grid(row=0, column=1, sticky="ns", pady=(1, 0), padx=(0, 1))
        self.cat_tree.configure(yscrollcommand=csb.set)

        # Högerklicksmeny på kategorilistan: samla alla kategorival på ett
        # ställe, precis som för stödorden. Gör det tydligt att en hel
        # kategori (med alla dess stödord) går att ta bort.
        self.cat_menu = tk.Menu(self.cat_tree, tearoff=0)
        self.cat_menu.add_command(label="+ Ny kategori…", command=self._cat_new)
        self.cat_menu.add_command(label="Byt namn…", command=self._cat_rename)
        self.cat_menu.add_separator()
        self.cat_menu.add_command(label="Ta bort kategori",
                                  command=self._cat_delete)
        self.cat_tree.bind("<Button-3>", self._cat_context)
        self.cat_tree.bind("<Button-2>", self._cat_context)   # macOS

        cbtn = ttk.Frame(left, style="CardInner.TFrame")
        cbtn.grid(row=1, column=0, columnspan=2, sticky="ew",
                  padx=T.INNER, pady=T.INNER)
        ttk.Button(cbtn, text="+ Ny", command=self._cat_new).pack(side="left")
        ttk.Button(cbtn, text="Byt namn", command=self._cat_rename
                   ).pack(side="left", padx=5)
        ttk.Button(cbtn, text="Ta bort", style="Danger.TButton",
                   command=self._cat_delete).pack(side="left")

        # -- höger: stödorden --
        rightcard = T.card(f, "Stödord")
        rightcard.grid(row=1, column=1, sticky="nsew",
                       padx=(T.GAP // 2, T.PAD), pady=T.GAP)
        right = rightcard.body
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        head = ttk.Frame(right, style="CardInner.TFrame")
        head.grid(row=0, column=0, columnspan=2, sticky="ew",
                  padx=T.INNER, pady=(T.INNER, 2))
        head.columnconfigure(0, weight=1)
        self.lbl_cat_title = ttk.Label(head, text="—", style="CardTitle.TLabel")
        self.lbl_cat_title.grid(row=0, column=0, sticky="w")
        self.lbl_cat_stats = ttk.Label(head, text="", style="CardMuted.TLabel")
        self.lbl_cat_stats.grid(row=1, column=0, sticky="w", pady=(1, 0))

        meta = ttk.Frame(right, style="CardInner.TFrame")
        meta.grid(row=1, column=0, columnspan=2, sticky="ew",
                  padx=T.INNER, pady=(10, 8))
        meta.columnconfigure(1, weight=1)
        ttk.Label(meta, text="Mappnamn:", style="Card.TLabel").grid(
            row=0, column=0, sticky="w")
        self.var_folder = tk.StringVar()
        ttk.Entry(meta, textvariable=self.var_folder).grid(
            row=0, column=1, sticky="ew", padx=8)
        self.var_cat_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(meta, text="Aktiv", variable=self.var_cat_enabled,
                        style="Card.TCheckbutton",
                        command=self._cat_save_meta).grid(row=0, column=2, padx=6)
        ttk.Button(meta, text="Spara", command=self._cat_save_meta
                   ).grid(row=0, column=3)

        # -- undermapp per datum --
        ttk.Label(meta, text="Undermapp:", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        self.sub_combo = ttk.Combobox(
            meta, state="readonly", width=34,
            values=[etikett for _, etikett in SUBFOLDER_TEMPLATES])
        self.sub_combo.grid(row=1, column=1, sticky="w", padx=8, pady=(8, 0))
        self.sub_combo.bind("<<ComboboxSelected>>", lambda e: self._cat_save_sub())
        self.lbl_sub_ex = ttk.Label(meta, text="", style="CardMuted.TLabel")
        self.lbl_sub_ex.grid(row=1, column=2, columnspan=2, sticky="w",
                             pady=(8, 0))

        # -- eget krav på antal stödord --
        ttk.Label(meta, text="Kräver:", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", pady=(8, 0))
        krav = ttk.Frame(meta, style="CardInner.TFrame")
        krav.grid(row=2, column=1, columnspan=3, sticky="w",
                  padx=8, pady=(8, 0))
        self.var_catkw = tk.StringVar(value="0")
        self.spin_catkw = ttk.Spinbox(krav, from_=0, to=9, width=4,
                                      textvariable=self.var_catkw,
                                      command=self._cat_save_kw)
        self.spin_catkw.pack(side="left")
        self.spin_catkw.bind("<FocusOut>", lambda e: self._cat_save_kw())
        self.lbl_catkw = ttk.Label(krav, text="", style="CardMuted.TLabel")
        self.lbl_catkw.pack(side="left", padx=10)

        cols = ("word", "kind", "weight", "whole", "hits")
        self.kw_tree = ttk.Treeview(right, columns=cols, show="headings",
                                    selectmode="extended")
        T.fit_columns(self.kw_tree, (
            ("word", "STÖDORD", 20, "w", True),
            ("kind", "TYP", 20, "w", False),
            ("weight", "VIKT", 4, "center", False),
            ("whole", "HELT ORD", 4, "center", False),
            ("hits", "TRÄFFAR", 5, "center", False)))
        for col in ("word", "kind", "weight", "whole", "hits"):
            self.kw_tree.heading(col, command=lambda c=col: self._sort_keywords(c))
        self.kw_tree.grid(row=2, column=0, sticky="nsew", padx=(1, 0), pady=4)
        self.theme.zebra(self.kw_tree)
        self.kw_tree.bind("<Delete>", lambda e: self._kw_remove())
        self.kw_tree.bind("<Double-1>", lambda e: self._kw_edit())

        # Högerklick: allt man kan göra med ett stödord, på ett ställe.
        self.kw_menu = tk.Menu(self.kw_tree, tearoff=0)
        self.kw_menu.add_command(label="Ändra ord…", command=self._kw_edit)
        self.kw_menu.add_command(label="Ändra vikt…", command=self._kw_weight)
        self.kw_menu.add_command(label="Flytta till annan kategori…",
                                 command=self._kw_move)
        self.kw_menu.add_separator()
        self.kw_menu.add_command(label="Ta bort", command=self._kw_remove)
        self.kw_menu.add_command(label="Rensa oanvända ord i kategorin…",
                                 command=self._kw_prune)
        self.kw_tree.bind("<Button-3>", self._kw_context)
        self.kw_tree.bind("<Button-2>", self._kw_context)   # macOS
        ksb = ttk.Scrollbar(right, orient="vertical", command=self.kw_tree.yview)
        ksb.grid(row=2, column=1, sticky="ns", pady=4, padx=(0, 1))
        self.kw_tree.configure(yscrollcommand=ksb.set)

        # Sammanfattning av kategorins styrka - syns direkt utan att man
        # behöver räkna raderna i tabellen.
        self.lbl_kw_sum = ttk.Label(right, style="CardMuted.TLabel",
                                    justify="left")
        self.lbl_kw_sum.grid(row=3, column=0, columnspan=2, sticky="w",
                             padx=T.INNER, pady=(6, 0))

        hint = ttk.Label(right, style="CardMuted.TLabel", justify="left",
                         text="Dubbelklicka ändrar ordet  ·  högerklick ger "
                              "fler val  ·  Delete tar bort  ·  klicka på en "
                              "rubrik för att sortera")
        hint.grid(row=4, column=0, columnspan=2, sticky="w",
                  padx=T.INNER, pady=(2, 0))

        kbtn = ttk.Frame(right, style="CardInner.TFrame")
        kbtn.grid(row=5, column=0, columnspan=2, sticky="ew",
                  padx=T.INNER, pady=(8, T.INNER))
        # grid i stället för pack: med pack konkurrerar vänster- och
        # högerpackade knappar om samma utrymme, och den sista klipps tyst
        # till "Ta bor". Här får varje knapp sin egen kolumn, och kolumn 4
        # sväller så att grupperna skjuts isär.
        for _i, (_txt, _cmd, _stil) in enumerate((
                ("+ Lägg till ord", self._kw_add, "Accent.TButton"),
                ("Ändra ord", self._kw_edit, "TButton"),
                ("Vikt", self._kw_weight, "TButton"),
                ("Flytta…", self._kw_move, "TButton"))):
            ttk.Button(kbtn, text=_txt, command=_cmd, style=_stil).grid(
                row=0, column=_i, padx=(0, 6), sticky="w")
        kbtn.columnconfigure(4, weight=1)
        # "Rensa oanvända" bor i högerklicksmenyn: den används sällan, och
        # en sjätte knapp gör att raden inte får plats i kortet.
        ttk.Button(kbtn, text="Ta bort", style="Danger.TButton",
                   command=self._kw_remove).grid(row=0, column=5)

        self._kw_sort = ("hits", True)
        self._kw_rows: List[Dict[str, Any]] = []

    # -- visning ----------------------------------------------------------
    def _refresh_categories(self, keep: Optional[str] = None) -> None:
        keep = keep or self._selected_cat()
        for row in self.cat_tree.get_children():
            self.cat_tree.delete(row)
        for i, cat in enumerate(self.rules.categories):
            tags = ["odd" if i % 2 else "even"]
            if not cat.get("enabled", True):
                tags.append("off")
            name = cat["name"] + ("   (av)" if not cat.get("enabled", True) else "")
            märken = []
            n_kw = int(cat.get("min_keywords", 0) or 0)
            if n_kw:
                märken.append(f"{n_kw} ord")
            if cat.get("subfolder"):
                märken.append(cat["subfolder"])
            self.cat_tree.insert("", "end", iid=cat["name"], tags=tags,
                                 values=(name, len(cat["keywords"]),
                                         " · ".join(märken)))
        names = self.rules.names()
        target = keep if keep in names else (names[0] if names else None)
        if target:
            self.cat_tree.selection_set(target)
            self.cat_tree.see(target)
        total_words = sum(len(c["keywords"]) for c in self.rules.categories)
        self.lbl_kwcount.configure(
            text=f"{len(names)} kategorier · {total_words} stödord")
        self._on_cat_select()

    def _selected_cat(self) -> Optional[str]:
        sel = self.cat_tree.selection()
        return sel[0] if sel else None

    def _sort_keywords(self, col: str) -> None:
        current, desc = self._kw_sort
        self._kw_sort = (col, not desc if col == current else True)
        self._refresh_keyword_view()

    def _on_cat_select(self) -> None:
        name = self._selected_cat()
        cat = self.rules.get(name) if name else None
        if not cat:
            self.var_folder.set("")
            self.lbl_cat_title.configure(text="Ingen kategori vald")
            self.lbl_cat_stats.configure(text="")
            for row in self.kw_tree.get_children():
                self.kw_tree.delete(row)
            return
        self.var_folder.set(cat["folder"])
        self.var_cat_enabled.set(cat.get("enabled", True))
        mall = cat.get("subfolder", "")
        nycklar = [t for t, _ in SUBFOLDER_TEMPLATES]
        self.sub_combo.current(nycklar.index(mall) if mall in nycklar else 0)
        self._show_sub_example(cat)
        self.var_catkw.set(str(int(cat.get("min_keywords", 0) or 0)))
        self._show_kw_krav(cat)
        self.lbl_cat_title.configure(text=cat["name"])
        used = sum(1 for k in cat["keywords"] if k.get("hits", 0))
        self.lbl_cat_stats.configure(
            text=f"{len(cat['keywords'])} stödord, varav {used} har använts  ·  "
                 f"{cat.get('files_sorted', 0)} filer sorterade  ·  "
                 f"mapp: {cat['folder']}")
        self._refresh_keyword_view()

    def _refresh_keyword_view(self) -> None:
        """Rita om stödordslistan med aktuell sortering och sökfilter."""
        for row in self.kw_tree.get_children():
            self.kw_tree.delete(row)
        name = self._selected_cat()
        cat = self.rules.get(name) if name else None
        if not cat:
            return

        needle = normalize(self.var_kwsearch.get())
        words = [k for k in cat["keywords"]
                 if not needle or needle in k["text"]]

        col, desc = self._kw_sort
        keyfn = {
            "word": lambda k: k["text"],
            "kind": lambda k: keyword_strength(k["text"]) or "zzz",
            "weight": lambda k: k["weight"],
            "whole": lambda k: k.get("whole_word", True),
            "hits": lambda k: k.get("hits", 0),
            "source": lambda k: k.get("source", ""),
        }.get(col, lambda k: k.get("hits", 0))
        words.sort(key=keyfn, reverse=desc)

        for i, kw in enumerate(words):
            strength = keyword_strength(kw["text"])
            label = STRONG_LABELS.get(strength, "vanligt ord") if strength \
                else "vanligt ord"
            tags = ["odd" if i % 2 else "even"]
            if strength:
                tags.append("strong")
            elif not kw.get("hits", 0):
                tags.append("weak")
            self.kw_tree.insert("", "end", iid=kw["text"], tags=tags, values=(
                kw["text"], label, f"{kw['weight']:g}",
                "ja" if kw.get("whole_word", True) else "nej",
                kw.get("hits", 0)))

        if needle:
            self.lbl_cat_stats.configure(
                text=f"{len(words)} av {len(cat['keywords'])} stödord "
                     f'matchar "{self.var_kwsearch.get()}"')

        if hasattr(self, "lbl_kw_sum"):
            starka = sum(1 for k in cat["keywords"] if keyword_strength(k["text"]))
            oanvända = sum(1 for k in cat["keywords"] if not k.get("hits", 0))
            behov = max(effective_thresholds(self.settings)["min_keywords"],
                        int(cat.get("min_keywords", 0) or 0))
            delar = [f"{starka} starka bevis (org.nr, VAT, giro, domän)"]
            if oanvända:
                delar.append(f"{oanvända} har aldrig träffat")
            delar.append(f"kräver {behov} för automatisk flytt")
            self.lbl_kw_sum.configure(text="   ·   ".join(delar))


    def _cat_new(self) -> None:
        name = self.simpledialog.askstring(APP_NAME, "Namn på ny kategori:", parent=self.root)
        if not name or not name.strip():
            return
        if self.rules.get(name):
            self.messagebox.showinfo(APP_NAME, "Kategorin finns redan.", parent=self.root)
            return
        self.rules.ensure_category(name.strip())
        self.rules.save()
        self._refresh_categories(name.strip())

    def _cat_rename(self) -> None:
        old = self._selected_cat()
        if not old:
            return
        new = self.simpledialog.askstring(APP_NAME, "Nytt namn:", initialvalue=old, parent=self.root)
        if not new or not new.strip() or new.strip() == old:
            return
        self.rules.rename_category(old, new.strip())
        self.rules.save()
        self._refresh_categories(new.strip())

    def _cat_delete(self) -> None:
        name = self._selected_cat()
        if not name:
            return
        if not self.messagebox.askyesno(
                APP_NAME, f"Ta bort kategorin \"{name}\" och alla dess stödord?\n\n"
                          "Redan sorterade filer påverkas inte.", parent=self.root):
            return
        self.rules.remove_category(name)
        self.rules.save()
        _PATTERN_CACHE.clear()
        self._refresh_categories()

    def _cat_context(self, event) -> None:
        """Visa kategorins högerklicksmeny, med raden under pekaren markerad."""
        rad = self.cat_tree.identify_row(event.y)
        if rad and rad not in self.cat_tree.selection():
            self.cat_tree.selection_set(rad)
        if not self.cat_tree.selection():
            return
        try:
            self.cat_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.cat_menu.grab_release()

    def _cat_save_sub(self) -> None:
        """Spara vald undermappsmall och visa ett exempel med dagens datum."""
        name = self._selected_cat()
        cat = self.rules.get(name) if name else None
        if not cat:
            return
        idx = self.sub_combo.current()
        mall = SUBFOLDER_TEMPLATES[idx][0] if 0 <= idx < len(SUBFOLDER_TEMPLATES) else ""
        cat["subfolder"] = mall
        self.rules.save()
        self._show_sub_example(cat)
        if mall and not self.settings.get("date_enabled", False):
            self._log("Undermappen sparad, men datumsortering är avstängd. "
                      "Slå på den under Inställningar.", "warn")

    def _show_sub_example(self, cat: Dict[str, Any]) -> None:
        """Grå exempelrad: så här hamnar en fil som sorteras idag."""
        mall = cat.get("subfolder", "")
        if not mall:
            self.lbl_sub_ex.configure(text="")
            return
        ex = render_subfolder(mall, date.today())
        på = self.settings.get("date_enabled", False)
        self.lbl_sub_ex.configure(
            text=f"idag → {cat['folder']}/{ex}/"
                 + ("" if på else "   (datumsortering är av)"))

    def _cat_save_kw(self) -> None:
        """Spara kategorins eget krav på antal matchade stödord."""
        name = self._selected_cat()
        cat = self.rules.get(name) if name else None
        if not cat:
            return
        try:
            n = max(0, min(9, int(float(self.var_catkw.get() or 0))))
        except ValueError:
            n = 0
        self.var_catkw.set(str(n))
        if n == int(cat.get("min_keywords", 0) or 0):
            return
        cat["min_keywords"] = n
        self.rules.save()
        self._show_kw_krav(cat)
        self._log(f"\"{cat['name']}\" kräver nu "
                  + (f"{n} olika stödord" if n else "nivåns vanliga antal"),
                  "info")

    def _show_kw_krav(self, cat: Dict[str, Any]) -> None:
        """Förklara vad siffran betyder, med nivåns värde som jämförelse."""
        n = int(cat.get("min_keywords", 0) or 0)
        nivå = effective_thresholds(self.settings)["min_keywords"]
        if n == 0:
            self.lbl_catkw.configure(
                text=f"olika stödord — 0 = följ nivån (just nu {nivå})")
        elif n <= nivå:
            self.lbl_catkw.configure(
                text=f"olika stödord — nivån kräver redan {nivå}")
        else:
            self.lbl_catkw.configure(
                text=f"olika stödord innan filen flyttas hit "
                     f"(nivån kräver {nivå})")

    def _cat_save_meta(self) -> None:
        name = self._selected_cat()
        cat = self.rules.get(name) if name else None
        if not cat:
            return
        cat["folder"] = safe_folder_name(self.var_folder.get() or cat["name"])
        cat["enabled"] = bool(self.var_cat_enabled.get())
        self.rules.save()
        self.var_folder.set(cat["folder"])
        self._refresh_categories(name)

    def _kw_add(self) -> None:
        name = self._selected_cat()
        if not name:
            self.messagebox.showinfo(APP_NAME, "Välj en kategori först.", parent=self.root)
            return
        word = self.simpledialog.askstring(
            APP_NAME, "Stödord eller fras (ett per rad går också):", parent=self.root)
        if not word:
            return
        words = [w for w in re.split(r"[\n;,]", word) if normalize(w)]
        owners = []
        for w in words:
            owners += [o for o in self.rules.keyword_owners(w) if normalize(o) != normalize(name)]
        if owners and not self.messagebox.askyesno(
                APP_NAME, f"Ordet används redan av: {', '.join(sorted(set(owners)))}.\n"
                          "Det kan ge krockar vid matchning. Lägg till ändå?", parent=self.root):
            return
        self.rules.add_keywords(name, words, source="user")
        self.rules.save()
        _PATTERN_CACHE.clear()
        self._refresh_categories(name)

    def _kw_remove(self) -> None:
        """Ta bort markerade stödord, med bekräftelse."""
        name = self._selected_cat()
        sel = self.kw_tree.selection()
        if not name or not sel:
            self.messagebox.showinfo(
                APP_NAME, "Markera ett eller flera stödord först.", parent=self.root)
            return
        words = [self.kw_tree.item(i, "values")[0] for i in sel]
        visning = ", ".join(words[:5]) + ("…" if len(words) > 5 else "")
        if not self.messagebox.askyesno(
                APP_NAME,
                f"Ta bort {len(words)} stödord från \"{name}\"?\n\n{visning}\n\n"
                "Redan sorterade filer påverkas inte, men framtida filer "
                "matchas inte längre på dessa ord.", parent=self.root):
            return
        for w in words:
            self.rules.remove_keyword(name, w)
        self.rules.save()
        _PATTERN_CACHE.clear()
        self._log(f"Tog bort {len(words)} stödord från \"{name}\"", "info")
        self._refresh_categories(name)

    def _kw_prune(self) -> None:
        """Rensa stödord som aldrig gett en träff.

        Efter en tids användning samlas ord som visade sig värdelösa. De
        gör ingen skada, men skräpar ned listan och kan i värsta fall
        krocka med andra kategorier.
        """
        name = self._selected_cat()
        cat = self.rules.get(name) if name else None
        if not cat:
            return
        unused = [k for k in cat["keywords"] if not k.get("hits", 0)]
        if not unused:
            self.messagebox.showinfo(
                APP_NAME, f"Alla stödord i \"{name}\" har använts minst en gång.",
                parent=self.root)
            return
        visning = ", ".join(k["text"] for k in unused[:8])
        if len(unused) > 8:
            visning += f" … och {len(unused) - 8} till"
        if not self.messagebox.askyesno(
                APP_NAME,
                f"{len(unused)} av {len(cat['keywords'])} stödord i \"{name}\" "
                f"har aldrig gett en träff:\n\n{visning}\n\nTa bort dem?",
                parent=self.root):
            return
        for k in unused:
            self.rules.remove_keyword(name, k["text"])
        self.rules.save()
        _PATTERN_CACHE.clear()
        self._log(f"Rensade {len(unused)} oanvända stödord från \"{name}\"", "info")
        self._refresh_categories(name)

    def _kw_context(self, event) -> None:
        """Visa högerklicksmenyn, med raden under pekaren markerad."""
        rad = self.kw_tree.identify_row(event.y)
        if rad and rad not in self.kw_tree.selection():
            self.kw_tree.selection_set(rad)
        if not self.kw_tree.selection():
            return
        try:
            self.kw_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.kw_menu.grab_release()

    def _kw_edit(self) -> None:
        """Ändra själva texten i ett stödord.

        Utan detta måste man ta bort ordet och lägga till ett nytt, vilket
        nollställer träffräknaren och när det lades till. Här behålls all
        historik - det är samma ord, bara stavat rätt.
        """
        name = self._selected_cat()
        sel = self.kw_tree.selection()
        if not name or not sel:
            self.messagebox.showinfo(
                APP_NAME, "Markera ett stödord först.", parent=self.root)
            return
        if len(sel) > 1:
            self.messagebox.showinfo(
                APP_NAME, "Markera bara ett ord i taget när du ändrar text.",
                parent=self.root)
            return
        gammalt = self.kw_tree.item(sel[0], "values")[0]
        nytt = self.simpledialog.askstring(
            APP_NAME, "Ändra stödordet:", initialvalue=gammalt,
            parent=self.root)
        if not nytt or normalize(nytt) == gammalt:
            return
        text = normalize(nytt)
        if not text:
            return
        cat = self.rules.get(name)
        if any(k["text"] == text for k in cat["keywords"]):
            self.messagebox.showwarning(
                APP_NAME, f"\"{text}\" finns redan i den här kategorin.",
                parent=self.root)
            return
        ägare = [o for o in self.rules.keyword_owners(text)
                 if normalize(o) != normalize(name)]
        if ägare and not self.messagebox.askyesno(
                APP_NAME, f"Ordet används redan av: {', '.join(sorted(set(ägare)))}.\n"
                          "Ändra ändå?", parent=self.root):
            return
        for kw in cat["keywords"]:
            if kw["text"] == gammalt:
                kw["text"] = text
                break
        self.rules.save()
        _PATTERN_CACHE.clear()
        self._log(f"Ändrade stödordet \"{gammalt}\" till \"{text}\"", "info")
        self._refresh_categories(name)

    def _kw_move(self) -> None:
        """Flytta markerade stödord till en annan kategori.

        Vanligt när man först lagt ett företagsnamn under fel mapp, eller
        när en kategori delas upp i två.
        """
        name = self._selected_cat()
        sel = self.kw_tree.selection()
        if not name or not sel:
            self.messagebox.showinfo(
                APP_NAME, "Markera ett eller flera stödord först.",
                parent=self.root)
            return
        andra = [n for n in self.rules.names() if n != name]
        if not andra:
            self.messagebox.showinfo(
                APP_NAME, "Det finns ingen annan kategori att flytta till.",
                parent=self.root)
            return
        ord_ = [self.kw_tree.item(i, "values")[0] for i in sel]
        mål = self._ask_choice(
            "Flytta stödord",
            f"Flytta {len(ord_)} stödord från \"{name}\" till:", andra)
        if not mål:
            return
        cat = self.rules.get(name)
        flyttade = []
        for w in ord_:
            kw = next((k for k in cat["keywords"] if k["text"] == w), None)
            if kw is None:
                continue
            målcat = self.rules.get(mål)
            if any(k["text"] == w for k in målcat["keywords"]):
                continue                     # finns redan där
            målcat["keywords"].append(dict(kw))   # behåll vikt och träffar
            cat["keywords"] = [k for k in cat["keywords"] if k["text"] != w]
            flyttade.append(w)
        self.rules.save()
        _PATTERN_CACHE.clear()
        self._log(f"Flyttade {len(flyttade)} stödord från \"{name}\" "
                  f"till \"{mål}\"", "info")
        self._refresh_categories(name)

    def _ask_choice(self, titel: str, fråga: str,
                    val: List[str]) -> Optional[str]:
        """Liten dialog med en rullgardin. Returnerar valt värde."""
        tk, ttk = self.tk, self.ttk
        win = tk.Toplevel(self.root)
        win.title(titel)
        win.configure(background=self.C["bg"])
        win.transient(self.root)
        win.resizable(False, False)
        ttk.Label(win, text=fråga).pack(padx=18, pady=(16, 8), anchor="w")
        combo = ttk.Combobox(win, state="readonly", values=val, width=34)
        combo.current(0)
        combo.pack(padx=18, fill="x")
        resultat: Dict[str, Optional[str]] = {"v": None}

        def ok() -> None:
            resultat["v"] = combo.get()
            win.destroy()

        rad = ttk.Frame(win)
        rad.pack(padx=18, pady=16, fill="x")
        ttk.Button(rad, text="Avbryt", command=win.destroy).pack(side="right")
        ttk.Button(rad, text="Flytta", style="Accent.TButton",
                   command=ok).pack(side="right", padx=6)
        win.bind("<Return>", lambda e: ok())
        win.bind("<Escape>", lambda e: win.destroy())
        win.update_idletasks()
        try:
            win.grab_set()
        except Exception:
            pass
        win.wait_window()
        return resultat["v"]

    def _kw_weight(self) -> None:
        name = self._selected_cat()
        sel = self.kw_tree.selection()
        if not name or not sel:
            return
        current = self.kw_tree.item(sel[0], "values")[2]
        try:
            current = float(current)
        except (TypeError, ValueError):
            current = 1.0
        val = self.simpledialog.askfloat(
            APP_NAME,
            f"Vikt för {len(sel)} stödord\n\n"
            "1.0 = normalt ord\n"
            "2.0 = företagsnamn\n"
            "3.0 = org.nr, VAT eller domän",
            initialvalue=current, minvalue=0.1, maxvalue=10.0, parent=self.root)
        if val is None:
            return
        cat = self.rules.get(name)
        targets = {self.kw_tree.item(i, "values")[0] for i in sel}
        for kw in cat["keywords"]:
            if kw["text"] in targets:
                kw["weight"] = float(val)
        self.rules.save()
        _PATTERN_CACHE.clear()
        self._refresh_categories(name)

    def _export(self) -> None:
        path = self.filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".json",
            initialfile="pdfsorter-rules.json",
            filetypes=[("JSON", "*.json")])
        if not path:
            return
        _write_json(Path(path), {"schema_version": SCHEMA_VERSION, "updated": now_iso(),
                                 "categories": self.rules.categories})
        self.messagebox.showinfo(APP_NAME, f"Sparade till:\n{path}", parent=self.root)

    def _import(self) -> None:
        path = self.filedialog.askopenfilename(parent=self.root,
                                               filetypes=[("JSON", "*.json")])
        if not path:
            return
        incoming = Rules(_read_json(Path(path), {}), self.rules.path)
        if not incoming.categories:
            self.messagebox.showwarning(APP_NAME, "Filen innehöll inga kategorier.", parent=self.root)
            return
        merge = self.messagebox.askyesnocancel(
            APP_NAME, f"{len(incoming.categories)} kategorier hittades.\n\n"
                      "Ja = slå ihop med befintliga\nNej = ersätt allt", parent=self.root)
        if merge is None:
            return
        if merge:
            for cat in incoming.categories:
                self.rules.ensure_category(cat["name"], cat["folder"])
                self.rules.add_keywords(cat["name"], [k["text"] for k in cat["keywords"]],
                                        source="import")
        else:
            self.rules.categories = incoming.categories
        self.rules.save()
        _PATTERN_CACHE.clear()
        self._warm_patterns()
        self._refresh_categories()

    # ======================================================================
    # Flik 3 - Granska
    # ======================================================================
    def _build_review_tab(self) -> None:
        ttk = self.ttk
        T = self.theme
        f = self.tab_review
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)

        top = ttk.Frame(f, style="Card.TFrame")
        top.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 0))
        self.lbl_queue = ttk.Label(top, text="Inga filer väntar på granskning.",
                                   style="CardHead.TLabel")
        self.lbl_queue.pack(side="left", padx=T.INNER, pady=T.INNER)
        ttk.Button(top, text="Granska alla…", style="Accent.TButton",
                   command=self._process_queue).pack(side="right",
                                                     padx=(0, T.INNER),
                                                     pady=T.INNER)
        ttk.Button(top, text="Skanna om alla",
                   command=self._manual_rescan).pack(side="right", padx=6)
        ttk.Button(top, text="Töm kön", style="Danger.TButton",
                   command=self._clear_queue).pack(side="right", padx=6)

        cols = ("file", "reason", "guess", "ocr")
        self.q_tree = ttk.Treeview(f, columns=cols, show="headings")
        T.fit_columns(self.q_tree, (
            ("file", "FIL", 26, "w", False),
            ("reason", "VARFÖR OSÄKER", 34, "w", True),
            ("guess", "GISSNING", 16, "w", False),
            ("ocr", "LÄST VIA", 9, "w", False)))
        self.q_tree.grid(row=1, column=0, sticky="nsew", padx=T.PAD,
                         pady=(T.GAP, T.PAD))
        self.theme.zebra(self.q_tree)
        self.q_tree.bind("<Double-1>", lambda e: self._process_queue(self._queue_index()))

    def _queue_index(self) -> int:
        sel = self.q_tree.selection()
        if not sel:
            return 0
        return max(0, self.q_tree.index(sel[0]))

    def _refresh_queue(self) -> None:
        for row in self.q_tree.get_children():
            self.q_tree.delete(row)
        for i, d in enumerate(self.queue):
            best = d.best
            läst = "OCR" if d.extraction.used_ocr else (
                "text + logga" if getattr(d.extraction, "ocr_logo", False) else "text")
            self.q_tree.insert("", "end", tags=("odd" if i % 2 else "even",), values=(
                d.path.name, d.reason,
                f"{best.name} ({best.score:g})" if best else "—", läst))
        n = len(self.queue)
        self.nb.tab(self.tab_review, text=f"Granska ({n})" if n else "Granska")
        self.lbl_queue.configure(
            text=f"{n} filer väntar på granskning." if n
            else "Inga filer väntar på granskning.")
        self._update_stats()
        self._sync_tray()

    def _manual_rescan(self) -> None:
        self._ui("Omskanning")
        """Kör om matchningen mot alla osorterade filer.

        Praktiskt sedan man redigerat stödord under Kategorier eller i
        JSON-fliken - då slipper man vänta på nästa inlärning.
        """
        if self._rescanning:
            self.messagebox.showinfo(APP_NAME, "En omskanning pågår redan.",
                                     parent=self.root)
            return
        if not self._validate_dirs():
            return
        files = self.rescan_targets()
        if not files:
            self.messagebox.showinfo(APP_NAME, "Inga osorterade filer att skanna om.",
                                     parent=self.root)
            return
        if not self.messagebox.askyesno(
                APP_NAME, f"Kör om matchningen mot {len(files)} filer?\n\n"
                          "De som nu matchar en kategori flyttas dit. Övriga "
                          "ligger kvar.", parent=self.root):
            return
        self._rescanning = True
        self._log(f"Skannar om {len(files)} filer…", "info")
        threading.Thread(target=self._rescan_worker, args=(files, ""),
                         daemon=True, name="pdfsorter-rescan").start()

    def _clear_queue(self) -> None:
        if self.queue and self.messagebox.askyesno(
                APP_NAME, "Töm kön? Filerna ligger kvar i inmappen.", parent=self.root):
            self.queue.clear()
            self._queued_paths.clear()
            self._refresh_queue()

    def _process_queue(self, start: int = 0) -> None:
        """Visa granskningsdialogen för varje kvarvarande fil."""
        if not self.queue:
            return
        try:
            if not self.root.winfo_exists():
                return          # fönstret rivet - ingen dialog att visa
        except Exception:
            return
        existing = self.rules.all_keyword_texts()
        all_learned: List[str] = []
        last_category = ""
        i = start
        while i < len(self.queue):
            decision = self.queue[i]
            if not decision.path.exists():
                self.queue.pop(i)
                self._queued_paths.discard(str(decision.path))
                continue
            cands = suggest_keywords(
                decision.extraction.combined, decision.path.name,
                limit=int(self.settings.get("keywords_per_file", 10)),
                existing=existing)
            session_log("granska",
                        f"Dialog öppnas för {decision.path.name} "
                        f"({i + 1}/{len(self.queue)}): {decision.reason}; "
                        f"{len(cands)} stödordsförslag")
            _hint = (self._lookup_sender_hint(decision)
                     if self.settings.get("orgnr_lookup", False) else "")
            res = ReviewDialog(self.root, decision, self.rules, cands,
                               index=i + 1, total=len(self.queue),
                               theme=self.theme,
                               preview=bool(self.settings.get(
                                   "preview_in_dialog", False)),
                               suggested_sender=_hint).show()
            if res is None:                        # hoppa över
                session_log("granska", f"Hoppade över {decision.path.name} "
                            "- filen ligger kvar i kön")
                i += 1
                continue
            if res.get("ignored_file"):            # ignorera permanent
                redan = is_ignored_file(decision.path)
                post = None if redan else mark_ignored_file(decision.path)
                if redan or post:
                    self._log(f"{decision.path.name}  ⊘ ignorerad permanent - "
                              "känns igen på innehållet"
                              + ("" if post else " (var redan markerad)"), "info")
                    self.queue.pop(i)
                    self._queued_paths.discard(str(decision.path))
                    self._refresh_queue()
                    self._refresh_ignores()
                    self._sync_tray()
                    if self.watcher:
                        self.watcher.forget(decision.path)
                    continue
                # gick inte att läsa/hashen: behandla som hoppa över
                self._log(f"{decision.path.name}  ✖ kunde inte ignoreras "
                          "(filen kan inte läsas)", "err")
                i += 1
                continue
            learned_now: List[str] = []
            if res.get("unmatched"):
                ok, msg = self.engine.send_to_unmatched(decision)
                self._log(f"{decision.path.name}  →  _Osorterat" if ok
                          else f"{decision.path.name}  ✖ {msg}", "warn" if ok else "err")
            else:
                cat, words = res["category"], res["words"]
                if res.get("save_rule") and words:
                    self.engine.learn(cat, words)
                    existing = self.rules.all_keyword_texts()
                    learned_now = list(words)
                    all_learned.extend(words)
                    last_category = cat
                    self._log(f"Lärde in {len(words)} stödord för \"{cat}\": "
                              f"{', '.join(words[:4])}{'…' if len(words) > 4 else ''}", "info")
                else:
                    self.engine.learn(cat, [])
                ok, msg = self.engine.apply(decision, cat, words, "user", learned=words)
                self._log(f"{decision.path.name}  →  {cat}   (ditt val)" if ok
                          else f"{decision.path.name}  ✖ {msg}", "ok" if ok else "err")
                if self.watcher:
                    self.watcher.forget(decision.path)
            self.queue.pop(i)
            self._queued_paths.discard(str(decision.path))

            # Den nya regeln kan täcka filer som ligger kvar i kön. Plocka
            # bort dem direkt så användaren slipper svara på samma sak igen.
            if learned_now:
                i -= self._apply_rule_to_queue(i)

            self._refresh_queue()
            self.root.update_idletasks()

        self._refresh_queue()
        self._refresh_categories()
        self._refresh_history()

        # Skanna om resten i bakgrunden - inmappar och _Osorterat
        if all_learned and self.settings.get("rescan_after_learn", True):
            self.rescan_after_learn(all_learned, last_category)

    def _apply_rule_to_queue(self, upto: int) -> int:
        """Flytta de filer i kön som den nyss inlärda regeln nu täcker.

        Returnerar hur många som togs bort före index `upto`, så att
        anroparens loopräknare kan justeras.
        """
        removed_before = 0
        idx = 0
        while idx < len(self.queue):
            decision = self.queue[idx]
            if not decision.path.exists():
                self.queue.pop(idx)
                self._queued_paths.discard(str(decision.path))
                if idx < upto:
                    removed_before += 1
                continue
            fresh = decide(self.rules, decision.extraction, self.settings)
            if fresh.status != "auto":
                idx += 1
                continue
            best = fresh.best
            ok, _ = self.engine.apply(fresh, best.name, best.matched, "rescan")
            if not ok:
                idx += 1
                continue
            self._log(f"{decision.path.name}  →  {best.name}   "
                      f"(samma regel)", "ok")
            if self.watcher:
                self.watcher.forget(decision.path)
            self.queue.pop(idx)
            self._queued_paths.discard(str(decision.path))
            if idx < upto:
                removed_before += 1
        return removed_before

    # ======================================================================
    # Omskanning efter inlärning
    # ======================================================================
    def rescan_targets(self) -> List[Path]:
        """Alla filer som kan tänkas passa en nyinlärd regel.

        Tre källor: granskningskön, inmapparna och _Osorterat. Sådant som
        redan sorterats rörs inte - det ligger ju i rätt mapp och skulle
        bara flyttas fram och tillbaka.
        """
        seen, out = set(), []

        def add(path: Path) -> None:
            try:
                key = os.path.normcase(os.path.abspath(str(path)))
            except Exception:
                return
            if key not in seen and path.exists():
                seen.add(key)
                out.append(path)

        for d in self.queue:
            add(d.path)
        exc = self.settings.get("exclude_dirs", [])
        for folder in self.input_dirs():
            for f in list_pdfs(Path(folder),
                               self.settings.get("recursive", False), exc):
                add(f)
        unmatched = (self.settings.get("unmatched_folder") or "").strip()
        outdir = (self.settings.get("output_dir") or "").strip()
        if unmatched and outdir:
            for f in list_pdfs(Path(outdir) / safe_folder_name(unmatched), True):
                add(f)
        return out

    def rescan_after_learn(self, learned: List[str], category: str) -> None:
        """Skanna om allt osorterat sedan användaren lärt appen ett nytt ord.

        Poängen med att svara på en fråga är att slippa svara på samma sak
        igen. Lär man appen att "offert" betyder Offerter ska alla väntande
        offerter flyttas dit på en gång, inte en i taget.

        Körs i bakgrunden så gränssnittet inte fryser.
        """
        if self._rescanning or not learned:
            return
        files = self.rescan_targets()
        if not files:
            return
        self._rescanning = True
        words = ", ".join(learned[:3]) + ("…" if len(learned) > 3 else "")
        self._log(f"Skannar om {len(files)} filer med det nya stödordet "
                  f"({words})…", "info")
        threading.Thread(target=self._rescan_worker, args=(files, category),
                         daemon=True, name="pdfsorter-rescan").start()

    def _rescan_worker(self, files: List[Path], category: str) -> None:
        # Samma parallellmönster som _sort_worker: läsningen delas upp på
        # trådar, flytten serialiseras av motorn.
        counters = {"moved": 0, "still": 0}
        lock = threading.Lock()
        workers = max(2, min(8, os.cpu_count() or 2))

        def job(path: Path) -> None:
            if not path.exists():
                return
            try:
                decision = self.engine.analyze(path)
            except Exception:
                return
            if decision.status != "auto":
                with lock:
                    counters["still"] += 1
                return
            best = decision.best
            ok, msg = self.engine.apply(decision, best.name, best.matched, "rescan")
            if ok:
                with lock:
                    counters["moved"] += 1
                self._log_threadsafe(
                    f"{path.name}  →  {best.name}   (omskanning)", "ok")
                self._post(lambda pth=path: self._drop_from_queue(pth))
                if self.watcher:
                    self.watcher.forget(path)
            else:
                with lock:
                    counters["still"] += 1

        try:
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=workers,
                    thread_name_prefix="pdfsorter-rescan") as pool:
                for _ in pool.map(job, files):
                    pass
        except Exception as exc:
            self._log_threadsafe(f"Omskanningen avbröts: {exc}", "err")
        finally:
            # _rescanning måste nollställas oavsett vad som händer, annars
            # låser sig knappen "Skanna om alla" för alltid.
            self._post(lambda: self._rescan_done(
                counters["moved"], counters["still"], category))

    def _drop_from_queue(self, path: Path) -> None:
        """Ta bort en fil ur granskningskön sedan omskanningen flyttat den."""
        key = str(path)
        self.queue = [d for d in self.queue if str(d.path) != key]
        self._queued_paths.discard(key)

    def _rescan_done(self, moved: int, still: int, category: str) -> None:
        self._rescanning = False
        self.engine.flush_rules()
        if moved:
            self._log(f"— Omskanning klar: {moved} filer flyttade, "
                      f"{still} väntar fortfarande —", "ok")
            if not self.visible:
                self._notify(f"{moved} filer flyttades av den nya regeln")
        else:
            self._log("— Omskanning klar: inga fler filer matchade —", "info")
        self._log(f"    Textcache: {TEXT_CACHE.stats()}", "info")
        self._refresh_queue()
        self._refresh_categories()
        self._refresh_history()

    # ======================================================================
    # Flik 4 - Historik
    # ======================================================================
    def _build_hist_tab(self) -> None:
        tk, ttk = self.tk, self.ttk
        T = self.theme
        f = self.tab_hist
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)

        top = ttk.Frame(f, style="Card.TFrame")
        top.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 0))
        ttk.Label(top, text="Alla flyttade filer", style="CardHead.TLabel"
                  ).pack(side="left", padx=T.INNER, pady=T.INNER)
        ttk.Label(top, text="Markera rader och klicka Ångra för att flytta tillbaka",
                  style="CardMuted.TLabel").pack(side="left")
        ttk.Button(top, text="Uppdatera", command=self._refresh_history
                   ).pack(side="right", padx=(0, T.INNER), pady=T.INNER)
        ttk.Button(top, text="Ångra valda", style="Accent.TButton",
                   command=self._undo_selected).pack(side="right", padx=6)
        ttk.Button(top, text="Exportera rapport (MD)", style="CardLink.TButton",
                   command=self._export_report).pack(side="right", padx=6)
        ttk.Button(top, text="Exportera årsarkiv…", style="CardLink.TButton",
                   command=self._export_archive_gui).pack(side="right", padx=6)
        # Hur många dagar rapporten ska täcka. Standard 10.
        ttk.Label(top, text="Dagar:", style="CardMuted.TLabel").pack(
            side="right", padx=(0, 4))
        self.var_report_days = tk.StringVar(
            value=str(max(1, int(self.settings.get("report_days", 10) or 10))))
        days_box = ttk.Spinbox(top, from_=1, to=365, width=4,
                               textvariable=self.var_report_days)
        days_box.pack(side="right", padx=(0, 6))

        cols = ("time", "file", "category", "score", "by", "matched")
        self.h_tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="extended")
        T.fit_columns(self.h_tree, (
            ("time", "TID", 17, "w", False),
            ("file", "FIL", 24, "w", False),
            ("category", "KATEGORI", 15, "w", False),
            ("score", "POÄNG", 5, "center", False),
            ("by", "BESLUT", 7, "w", False),
            ("matched", "MATCHADE ORD", 24, "w", True)))
        self.h_tree.grid(row=1, column=0, sticky="nsew", padx=T.PAD,
                         pady=(T.GAP, T.PAD))
        self.theme.zebra(self.h_tree)
        self.h_tree.bind("<Double-1>", lambda e: self._open_hist_target())
        self._history: List[Dict[str, Any]] = []

    def _refresh_history(self) -> None:
        for row in self.h_tree.get_children():
            self.h_tree.delete(row)
        self._history = load_history()
        for i, ev in enumerate(reversed(self._history[-500:])):
            t = ev.get("time", "")[:19].replace("T", "  ")
            self.h_tree.insert("", "end", tags=("odd" if i % 2 else "even",), values=(
                t, Path(ev.get("source", "")).name, ev.get("category", ""),
                f"{ev.get('score', 0):g}", ev.get("decided_by", ""),
                ", ".join(ev.get("matched", []))[:80]))

    def _selected_events(self) -> List[Dict[str, Any]]:
        recent = list(reversed(self._history[-500:]))
        out = []
        for item in self.h_tree.selection():
            idx = self.h_tree.index(item)
            if idx < len(recent):
                out.append(recent[idx])
        return out

    def _open_hist_target(self) -> None:
        for ev in self._selected_events():
            p = Path(ev.get("target", ""))
            if p.exists():
                open_externally(p)
            break

    def _undo_selected(self) -> None:
        events = self._selected_events()
        if not events:
            return
        if not self.messagebox.askyesno(
                APP_NAME, f"Flytta tillbaka {len(events)} fil(er) till ursprunglig plats?",
                parent=self.root):
            return
        ok_count = 0
        remaining = list(self._history)
        for ev in events:
            ok, msg = undo_event(ev)
            if ok:
                ok_count += 1
                if ev in remaining:
                    remaining.remove(ev)
                self._log(f"Ångrade: {Path(ev.get('source','')).name}", "info")
            else:
                self._log(f"Kunde inte ångra {Path(ev.get('source','')).name}: {msg}", "err")
        replace_history(remaining)
        self._refresh_history()
        self.messagebox.showinfo(APP_NAME, f"{ok_count} av {len(events)} filer flyttades tillbaka.",
                                 parent=self.root)

    def _export_report(self) -> None:
        """Exportera en Markdown-rapport över matchningen de senaste N dagarna.

        Föreslår `report_days` (standard 10) dagar, och sparar en .md-fil
        som sammanfattar hur sorteringen gått. Den är bra att visa upp när
        man vill analysera stödord, tvetydiga fall och döda ord.
        """
        try:
            days = max(1, int(float(self.var_report_days.get() or 10)))
        except ValueError:
            days = 10
        self.settings["report_days"] = days
        save_settings(self.settings)
        path = self.filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".md",
            initialfile=report_path().name,
            filetypes=[("Markdown", "*.md"), ("Alla filer", "*.*")])
        if not path:
            return
        try:
            Path(path).write_text(build_matching_report(days), encoding="utf-8")
            self._log(f"Rapport exporterad ({days} dagar): {path}", "ok")
            self.messagebox.showinfo(
                APP_NAME,
                f"Matchningsrapport sparad:\n{path}\n\n"
                f"Den sammanfattar de senaste {days} dagarna. Öppna den och "
                f"visa mig, så vet jag exakt vad jag ska leta efter.",
                parent=self.root)
            open_externally(Path(path))
        except OSError as exc:
            self.messagebox.showerror(APP_NAME, f"Kunde inte spara:\n{exc}",
                                      parent=self.root)

    # ======================================================================
    # -- autostart och genvägar -------------------------------------------
    def _toggle_autostart(self) -> None:
        self._ui("Autostart på/av")
        want = bool(self.var_autostart.get())
        self._h("autostart", f"Före ändring: klass {classify_autostart()}")
        ok, msg = set_autostart(want)
        for namn, varde in get_autostart_conflicts():
            self._h("autostart", f"Konflikt: {namn} -> {varde}", "warn")
        if not ok:
            self.var_autostart.set(not want)
            self.messagebox.showerror(
                APP_NAME, f"Kunde inte ändra autostart:\n{msg}", parent=self.root)
            return
        self.settings["autostart"] = want
        save_settings(self.settings)
        self._log("Autostart påslagen - appen startar med datorn, minimerad "
                  "i systemfältet." if want else "Autostart avstängd.", "ok")

    def _make_shortcut(self) -> None:
        ok, msg = create_desktop_shortcut()
        if ok:
            self.messagebox.showinfo(APP_NAME, f"Genväg skapad:\n{msg}", parent=self.root)
        else:
            self.messagebox.showwarning(APP_NAME, f"Kunde inte skapa genväg:\n{msg}",
                                        parent=self.root)

    def _save_icon(self) -> None:
        ext = ".ico" if sys.platform.startswith("win") else ".png"
        path = self.filedialog.asksaveasfilename(
            parent=self.root, defaultextension=ext,
            initialfile=f"pdfsorter{ext}",
            filetypes=[("Ikon", f"*{ext}"), ("PNG", "*.png")])
        if not path:
            return
        result = write_icon_file(Path(path))
        if result:
            self.messagebox.showinfo(APP_NAME, f"Ikonen sparad:\n{result}", parent=self.root)
        else:
            self.messagebox.showwarning(APP_NAME, "Kunde inte spara ikonen "
                                                  "(kräver Pillow).", parent=self.root)

    # ======================================================================
    # Flik 5 - Matchningar (JSON)
    # ======================================================================
    def _build_json_tab(self) -> None:
        tk, ttk = self.tk, self.ttk
        T = self.theme
        f = self.tab_json
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)

        top = ttk.Frame(f)
        top.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 4))
        ttk.Label(top, text="Rådata", style="Head.TLabel").pack(side="left")
        ttk.Label(top, text="   För dig som vill redigera filerna direkt. "
                            "Vanlig hantering sker under Matchningar.",
                  style="Muted.TLabel").pack(side="left")

        bar = ttk.Frame(f)
        bar.grid(row=1, column=0, sticky="ew", padx=T.PAD, pady=(0, 8))
        self.json_file = tk.StringVar(value="rules")
        for label, key in (("Matchningar (rules.json)", "rules"),
                           ("Inställningar (settings.json)", "settings"),
                           ("Historik (history.json)", "history")):
            ttk.Radiobutton(bar, text=label, value=key, variable=self.json_file,
                            command=self._json_load).pack(side="left", padx=(0, 12))

        self.json_text = tk.Text(f, wrap="none", undo=True,
                                 font=self.theme.f_mono, borderwidth=0,
                                 background=self.C["surface"],
                                 foreground=self.C["text"],
                                 selectbackground=self.C["accent_light"],
                                 insertbackground=self.C["text"],
                                 padx=12, pady=10, highlightthickness=0)
        self.json_text.grid(row=2, column=0, sticky="nsew", padx=(T.PAD, 0), pady=4)
        jsb = ttk.Scrollbar(f, orient="vertical", command=self.json_text.yview)
        jsb.grid(row=2, column=1, sticky="ns", pady=4)
        jsbx = ttk.Scrollbar(f, orient="horizontal", command=self.json_text.xview)
        jsbx.grid(row=3, column=0, sticky="ew", padx=(10, 0))
        self.json_text.configure(yscrollcommand=jsb.set, xscrollcommand=jsbx.set)

        btns = ttk.Frame(f)
        btns.grid(row=4, column=0, columnspan=2, sticky="ew",
                  padx=T.PAD, pady=(8, 10))
        ttk.Button(btns, text="Läs om", command=self._json_load).pack(side="left")
        ttk.Button(btns, text="Kontrollera",
                   command=self._json_validate).pack(side="left", padx=4)
        self.btn_json_save = ttk.Button(btns, text="Spara ändringar",
                                        command=self._json_save)
        self.btn_json_save.pack(side="left")
        ttk.Button(btns, text="Öppna mappen",
                   command=lambda: open_externally(config_dir())).pack(side="right")
        ttk.Button(btns, text="Importera…",
                   command=self._import).pack(side="right", padx=4)
        ttk.Button(btns, text="Exportera…",
                   command=self._export).pack(side="right")

        self.json_status = ttk.Label(f, text="", anchor="w", style="Muted.TLabel")
        self.json_status.grid(row=5, column=0, columnspan=2, sticky="ew",
                              padx=T.PAD, pady=(0, 10))
        self._json_load()

    def _json_path(self) -> Path:
        return {"rules": rules_path(), "settings": settings_path(),
                "history": history_path()}[self.json_file.get()]

    def _json_load(self) -> None:
        path = self._json_path()
        try:
            text = path.read_text(encoding="utf-8") if path.exists() else "{}"
        except OSError as exc:
            text = f"// Kunde inte läsa filen: {exc}"
        self.json_text.delete("1.0", "end")
        self.json_text.insert("1.0", text)
        self.json_text.edit_reset()
        editable = self.json_file.get() != "history"
        self.json_text.configure(state="normal" if editable else "disabled")
        self.btn_json_save.configure(state="normal" if editable else "disabled")
        size = path.stat().st_size if path.exists() else 0
        self.json_status.configure(
            text=f"{path}    ({human_size(size)})"
                 + ("" if editable else "   ·   historiken redigeras inte här"),
            foreground="#555")

    def _json_validate(self) -> Optional[Any]:
        raw = self.json_text.get("1.0", "end")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.json_status.configure(
                text=f"Fel i JSON på rad {exc.lineno}, tecken {exc.colno}: {exc.msg}",
                foreground="#b42318")
            try:
                self.json_text.tag_remove("err", "1.0", "end")
                self.json_text.tag_add("err", f"{exc.lineno}.0", f"{exc.lineno}.end")
                self.json_text.tag_configure("err", background="#ffe0e0")
                self.json_text.see(f"{exc.lineno}.0")
            except Exception:
                pass
            return None
        self.json_text.tag_remove("err", "1.0", "end")
        if self.json_file.get() == "rules":
            cats = data.get("categories", []) if isinstance(data, dict) else []
            words = sum(len(c.get("keywords", [])) for c in cats
                        if isinstance(c, dict))
            self.json_status.configure(
                text=f"JSON är giltig  ·  {len(cats)} kategorier, {words} stödord",
                foreground="#1a7f37")
        else:
            self.json_status.configure(text="JSON är giltig", foreground="#1a7f37")
        return data

    def _json_save(self) -> None:
        data = self._json_validate()
        if data is None:
            self.messagebox.showerror(
                APP_NAME, "Filen sparades inte - rätta felet först.\n\n"
                          + self.json_status.cget("text"), parent=self.root)
            return
        which = self.json_file.get()
        if which == "rules":
            incoming = Rules(data if isinstance(data, dict) else {})
            if not incoming.categories and not self.messagebox.askyesno(
                    APP_NAME, "Filen innehåller inga kategorier alls.\n"
                              "Spara ändå? All matchning försvinner.",
                    parent=self.root):
                return
            self.rules.categories = incoming.categories
            self.rules.save()
            _PATTERN_CACHE.clear()
            self._warm_patterns()
            self._refresh_categories()
            self._log(f"Matchningar sparade: {len(incoming.categories)} kategorier",
                      "ok")
        else:
            if not isinstance(data, dict):
                self.messagebox.showerror(APP_NAME, "Inställningarna måste vara ett JSON-objekt.",
                                          parent=self.root)
                return
            save_settings(data)
            self.settings = load_settings()
            self.engine.settings = self.settings
            self._reload_settings_into_gui()
            self._log("Inställningar sparade från JSON-fliken", "ok")
        self._json_load()

    def _reload_settings_into_gui(self) -> None:
        """Spegla self.settings tillbaka till kryssrutorna."""
        try:
            self.var_out.set(self.settings.get("output_dir", ""))
            self.var_recursive.set(self.settings.get("recursive", False))
            self.var_ask.set(self.settings.get("ask_when_unsure", True))
            self.var_ocr.set(self.settings.get("ocr_enabled", True))
            self.var_ocr_quality.set(
                str(self.settings.get("ocr_quality", "high")) == "high")
            self.var_dry.set(self.settings.get("dry_run", False))
            self.var_action.set(self.settings.get("action", "move"))
            self.var_popup.set(self.settings.get("popup_immediately", False))
            self.var_rescan.set(self.settings.get("rescan_after_learn", True))
            self.var_unmatched.set(self.settings.get("unmatched_folder", ""))
            self.var_minscore.set(str(self.settings.get("min_score", 1.0)))
            self.var_margin.set(str(self.settings.get("ambiguity_margin", 0.5)))
            self.var_minkw.set(str(self.settings.get("min_keywords", 1)))
            self.var_ratio.set(str(self.settings.get("score_ratio", 1.0)))
            self.var_mintext.set(str(self.settings.get("min_text_chars", 0)))
            self.var_strong.set(self.settings.get("require_strong", False))
            self.var_anchor.set(self.settings.get("require_anchor", False))
            self.var_rejrec.set(self.settings.get("reject_recipient_only", True))
            lvl = self.settings.get("strictness", "normal")
            if lvl in STRICT_ORDER:
                self.strict_combo.current(STRICT_ORDER.index(lvl))
                self._on_strictness(initial=True)
            if hasattr(self, "var_theme"):
                self.var_theme.set(self.settings.get("theme", "ljus"))
            self.var_tray.set(self.settings.get("tray_enabled", True))
            self.var_close_tray.set(self.settings.get("close_to_tray", True))
            self.var_startmin.set(self.settings.get("start_minimized", False))
            self.var_autowatch.set(self.settings.get("autowatch_on_start", False))
            self.var_notify.set(self.settings.get("notify", True))
            self.var_date_on.set(self.settings.get("date_enabled", False))
            self.var_date_fb.set(self.settings.get("date_fallback", "none"))
            mallar = [t for t, _ in SUBFOLDER_TEMPLATES if t]
            dm = self.settings.get("date_default_template", "{år}")
            if dm in mallar:
                self.date_combo.current(mallar.index(dm))
            self._refresh_input_list()
        except Exception:
            pass

    # ======================================================================
    # Flik 6 - Hjälp
    # ======================================================================
    def _build_help_tab(self) -> None:
        tk, ttk = self.tk, self.ttk
        f = self.tab_help
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        wrap = ttk.Frame(f, style="Card.TFrame")
        wrap.grid(row=0, column=0, sticky="nsew",
                  padx=self.theme.PAD, pady=(self.theme.PAD, 0))
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)

        txt = tk.Text(wrap, wrap="word", borderwidth=0, padx=26, pady=20,
                      state="disabled", cursor="arrow",
                      background=self.C["surface"], foreground=self.C["text"],
                      highlightthickness=0, spacing1=1, spacing2=2)
        txt.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=txt.yview)
        sb.grid(row=0, column=1, sticky="ns")
        txt.configure(yscrollcommand=sb.set)
        self.help_text = txt

        base = self.theme.f_base
        txt.tag_configure("h1", font=self.theme.f_title,
                          spacing1=4, spacing3=12, foreground=self.C["accent_dark"])
        txt.tag_configure("h2", font=self.theme.f_head,
                          spacing1=18, spacing3=7, foreground=self.C["accent_dark"])
        txt.tag_configure("body", font=base, spacing3=5, lmargin1=2, lmargin2=2)
        txt.tag_configure("bullet", font=base, spacing3=3,
                          lmargin1=18, lmargin2=32)
        txt.tag_configure("code", font=self.theme.f_mono,
                          background=self.C["bg"], lmargin1=20, lmargin2=20,
                          spacing1=5, spacing3=5, foreground=self.C["accent_dark"])
        txt.tag_configure("note", font=self.theme.f_small,
                          foreground=self.C["text_muted"],
                          lmargin1=20, lmargin2=20, spacing3=8)
        txt.tag_configure("key", font=self.theme.f_bold)

        for kind, text in HELP_CONTENT:
            txt.configure(state="normal")
            txt.insert("end", text + "\n", kind)
            txt.configure(state="disabled")

        bar = ttk.Frame(f)
        bar.grid(row=1, column=0, sticky="ew",
                 padx=self.theme.PAD, pady=(self.theme.GAP, self.theme.GAP))
        ttk.Button(bar, text="Spara hjälpen som textfil…",
                   command=self._save_help).pack(side="left")
        ttk.Button(bar, text="Öppna inställningsmappen",
                   command=lambda: open_externally(config_dir())).pack(side="left", padx=6)
        ttk.Button(bar, text="Kopiera diagnostik för support",
                   command=self._copy_support_log).pack(side="left", padx=6)
        ttk.Button(bar, text="Öppna log-mappen",
                   command=self._open_log_dir).pack(side="left", padx=6)
        ttk.Button(bar, text="Stöd projektet 💖",
                   command=self._visa_stod).pack(side="left", padx=6)
        ttk.Button(bar, text="Sök efter uppdateringar…",
                   command=lambda: self._check_updates_gui(manual=True)).pack(side="left", padx=6)
        ttk.Label(bar, text=f"{APP_NAME} {APP_VERSION}",
                  style="Faint.TLabel").pack(side="right")

    # -- uppdatering från Git (2026-10-16) ------------------------------
    def _schedule_tick(self) -> None:
        """1.1.0: schemalagd sortering - kör en sortering per dag vid
        inställt klockslag medan appen är igång (även i systemfältet)."""
        try:
            if self.settings.get("schedule_enabled", False) and not self._busy:
                tid = str(self.settings.get("schedule_time", "07:00"))[:5]
                idag = time.strftime("%Y-%m-%d")
                if (time.strftime("%H:%M") >= tid
                        and self.settings.get("schedule_last_run", "") != idag):
                    self.settings["schedule_last_run"] = idag
                    save_settings(self.settings)
                    self._log(f"⏰ Schemalagd sortering (kl. {tid}) startar", "info")
                    self._sort_now()
        except Exception:
            pass
        try:
            self.root.after(30000, self._schedule_tick)
        except Exception:
            pass

    def _export_archive_gui(self) -> None:
        """1.1.0 (#7): exportera årsarkiv som öppen mapp + HTML-index."""
        dest = self.filedialog.askdirectory(
            title="Välj mapp att exportera arkivet till")
        if not dest:
            return
        out = self.settings.get("output_dir", "")
        if not out or not Path(out).is_dir():
            self.messagebox.showwarning(
                APP_NAME, "Utmappen finns inte - ställ in den först.")
            return

        def work() -> None:
            res = export_year_archive(
                Path(out), Path(dest),
                log=lambda m: self._log_threadsafe(m, "info"))
            def klar() -> None:
                self.messagebox.showinfo(
                    APP_NAME,
                    f"{res['filer']} filer exporterade till:\n{res['mapp']}"
                    "\n\nÖppna index.html där för att söka i arkivet.")
            with self._ui_lock:
                self._ui_calls.append(klar)

        threading.Thread(target=work, daemon=True,
                         name="arkiv-export").start()
        self._log("📦 Årsarkivexport startad…", "info")

    def _lookup_sender_hint(self, decision) -> str:
        """1.1.0 (#9): slå upp firmanamn för dokumentets org.nr (bara när
        inställningen är på och org.nr:t inte redan är ett stödord)."""
        try:
            text = decision.extraction.combined or decision.extraction.text or ""
            funna = []
            for m in re.finditer(r"\b(\d{6})-?(\d{4})\b", text):
                siffror = m.group(1) + m.group(2)
                if _luhn_ok(siffror):
                    funna.append(siffror)
            if not funna:
                return ""
            kända = {"".join(c for c in t if c.isdigit())
                     for t in self.rules.all_keyword_texts()}
            orgnr = next((o for o in funna if o not in kända), "")
            if not orgnr:
                return ""
            låda: Dict[str, Any] = {}

            def kör() -> None:
                låda["namn"] = lookup_company_name_online(orgnr)

            tråd = threading.Thread(target=kör, daemon=True)
            tråd.start()
            tråd.join(6.5)
            namn = låda.get("namn")
            if namn:
                self._log(f"🔎 Org.nr {orgnr}: föreslagen avsändare "
                          f"\"{namn}\" (uppslag via nätet)", "info")
                return str(namn)
        except Exception:
            pass
        return ""

    def _check_updates_gui(self, manual: bool = False) -> None:
        """Sök uppdatering i bakgrunden (GitHub Releases först)."""
        def work():
            info = check_for_update()
            self.root.after(0, lambda: self._update_prompt(info, manual))
        threading.Thread(target=work, daemon=True).start()

    def _update_prompt(self, info: dict, manual: bool) -> None:
        if not info.get("ok"):
            self._h("uppdatering", "Kunde inte söka uppdatering: "
                    + str(info.get("error", "okänt fel")), "warn")
            if manual:
                self.messagebox.showwarning(
                    APP_NAME, "Kunde inte söka efter uppdateringar:\n"
                    + str(info.get("error", "okänt fel")))
            return
        if not info.get("available"):
            self._h("uppdatering",
                    f"Ingen nyare version (kör {APP_VERSION}, "
                    f"GitHub: {info.get('remote')})")
            if manual:
                self.messagebox.showinfo(
                    APP_NAME, f"Du har den senaste versionen ({APP_VERSION}).")
            return
        kalla = ("GitHub Releases" if info.get("source") == "release"
                 else "GitHub (main-grenen)")
        verifierad = bool(info.get("sha256_url") or info.get("sha256"))
        if info.get("source") == "release" and not verifierad:
            self._h("uppdatering",
                    f"Releasen {info.get('remote')} saknar kontrollsumma - "
                    "uppdateringen kan inte verifieras", "warn")
            if manual:
                self.messagebox.showwarning(
                    APP_NAME,
                    f"Releasen {info.get('remote')} saknar kontrollsumma "
                    "(SHA256SUMS.txt eller SHA-256 i release-texten).\n\n"
                    "Appen installerar inte ett paket som inte kan "
                    "verifieras. Ladda ner den manuellt från releasesidan.")
            return
        # Autouppdatering: installera tyst bara när paketet kan verifieras
        # mot release-postens kontrollsumma. Utan kontrollsumma frågar vi.
        tyst = (bool(self.settings.get("auto_update", False)) and not manual
                and verifierad)
        if tyst:
            svar = True
            self._h("uppdatering",
                    f"Autouppdatering: {info['remote']} hittad på {kalla} - "
                    "verifierar SHA-256 och installerar", "ok")
        else:
            svar = self.messagebox.askyesno(
                APP_NAME,
                f"En ny version finns: {info['remote']} "
                f"(du har {APP_VERSION}).\n\n"
                f"Källa: {kalla}."
                + ("\nPaketet verifieras med SHA-256 före installation."
                   if verifierad else
                   "\nVarning: releasen saknar kontrollsumma.")
                + "\n\nAppen uppdateras i sin egen mapp, dina "
                "inställningar, regler och historik rörs inte. "
                "En säkerhetskopia tas först.")
        if not svar:
            self._h("uppdatering", "Uppdateringen avböjd av användaren")
            return

        def install():
            ok, msg = perform_update()
            if ok:
                update_python_packages()
            def done():
                self._h("uppdatering", msg, "ok" if ok else "warn")
                if ok:
                    if self.messagebox.askyesno(
                            APP_NAME, msg + "\n\nStarta om appen nu "
                            "för att köra den nya versionen?"):
                        self._restart_app()
                else:
                    self.messagebox.showwarning(APP_NAME, msg)
            self.root.after(0, done)
        threading.Thread(target=install, daemon=True).start()

    def _restart_app(self) -> None:
        """Starta om appen efter uppdatering (samma startväg som vanligt)."""
        try:
            import subprocess as _sp
            rot = Path(__file__).resolve().parent
            pyw = rot / "pdfsorter.pyw"
            exe = sys.executable or "python3"
            if sys.platform.startswith("win") and pyw.is_file():
                exe_w = Path(exe).with_name("pythonw.exe")
                _sp.Popen([str(exe_w if exe_w.exists() else exe), str(pyw)],
                          cwd=str(rot))
            else:
                _sp.Popen([exe, str(rot / "pdfsorter.py")], cwd=str(rot))
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # -- donationsvy (N15, ANVÄNDARORDER 2026-10-15) -------------------
    STOD_TEXT = {
        "sv": {
            "titel": "Stöd ArkivPiloten 💖",
            "undre": "Gratis, utan reklam. Din donation håller sortering, "
                     "OCR och matchning vid liv.",
            "t1": "☕ En kaffe — 39 kr",
            "t1d": "Ett litet tack som ger energi till kvällskodning.",
            "t2": "📚 Bokvän — 99 kr (mest vald)",
            "t2d": "Täcker en månads underhåll och testfiler.",
            "t3": "🌟 Hjälte — 299 kr",
            "t3d": "Bär projektet en extra bit; din idé hamnar högt i kön.",
            "paypal": "💙 PayPal", "kofi": "☕ Ko-fi",
            "valfritt": "Valfritt belopp",
            "nr": "Ditt Swish-nummer (12 siffror):",
            "qr": "Skanna med Swish — jämför med originalet: båda ska "
                  "öppna samma betalning.",
            "payload": "Payload (kopiera för jämförelse med original-QR):",
            "kopiera_nr": "Kopiera nummer",
            "kopiera_payload": "Kopiera payload",
            "utan_nr": "Fyll i ditt Swish-nummer så ritas QR-koden direkt "
                       "(beroendefri QR, verifierad mot oberoende avkodare).",
            "tack": "Tack för att du håller appen gratis för alla! ✨",
        },
        "en": {
            "titel": "Support ArkivPiloten 💖",
            "undre": "Free, ad-free. Your donation keeps sorting, OCR and "
                     "matching alive.",
            "t1": "☕ A coffee — 39 SEK",
            "t1d": "A small thanks that fuels evening coding.",
            "t2": "📚 Book friend — 99 SEK (most picked)",
            "t2d": "Covers a month of maintenance and test files.",
            "t3": "🌟 Hero — 299 SEK",
            "t3d": "Carries the project further; your idea jumps the queue.",
            "paypal": "💙 PayPal", "kofi": "☕ Ko-fi",
            "valfritt": "Custom amount",
            "nr": "Your Swish number (12 digits):",
            "qr": "Scan with Swish — compare with the original: both should "
                  "open the same payment.",
            "payload": "Payload (copy to compare with the original QR):",
            "kopiera_nr": "Copy number",
            "kopiera_payload": "Copy payload",
            "utan_nr": "Enter your Swish number and the QR is drawn "
                       "instantly (dependency-free QR, verified against an "
                       "independent decoder).",
            "tack": "Thanks for keeping the app free for everyone! ✨",
        },
    }

    def _visa_stod(self) -> None:
        """Donationsvy med SV/EN-växel, nivåer, PayPal/Ko-fi och Swish-QR
        (N15). QR-koden ritas beroendefritt; payloaden visas för jämförelse
        med originalkoden."""
        tk, ttk = self.tk, self.ttk
        win = tk.Toplevel(self.root)
        win.title("ArkivPiloten — stöd")
        win.transient(self.root)
        win.resizable(False, False)
        try:
            win.configure(background=self.C["bg"])
            win.after(80, lambda: dark_titlebar(win, bool(self.theme.dark)))
        except Exception:
            pass
        lang = tk.StringVar(value="sv")

        def T_(nyckel):
            return self.STOD_TEXT[lang.get()][nyckel]

        rub = ttk.Label(win, text="", style="Head.TLabel")
        rub.pack(anchor="w", padx=18, pady=(16, 2))
        und = ttk.Label(win, text="", style="CardMuted.TLabel",
                        wraplength=430)
        und.pack(anchor="w", padx=18)
        sprakrad = ttk.Frame(win)
        sprakrad.pack(anchor="w", padx=18, pady=(10, 0))
        ttk.Label(sprakrad, text="Språk / Language:",
                  style="CardMuted.TLabel").pack(side="left")
        ttk.Radiobutton(sprakrad, text="SV", value="sv",
                        variable=lang).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(sprakrad, text="EN", value="en",
                        variable=lang).pack(side="left")

        body = ttk.Frame(win)
        body.pack(fill="both", padx=18, pady=10)
        tiers = []
        for nyckel in ("t1", "t2", "t3"):
            f = ttk.Frame(body, style="Card.TFrame")
            f.pack(fill="x", pady=4)
            lbl = ttk.Label(f, text="", style="TLabel")
            lbl.pack(anchor="w", padx=10, pady=(8, 0))
            desc = ttk.Label(f, text="", style="CardMuted.TLabel",
                             wraplength=380)
            desc.pack(anchor="w", padx=10, pady=(0, 8))
            tiers.append((nyckel, lbl, desc))
        btnrad = ttk.Frame(body)
        btnrad.pack(fill="x", pady=8)
        b_pay = ttk.Button(btnrad, text="", style="Accent.TButton",
                           command=lambda: open_externally(
                               Path("https://paypal.me/Rickard3dPrint")))
        b_pay.pack(side="left")
        b_kofi = ttk.Button(btnrad, text="",
                            command=lambda: open_externally(
                                Path("https://ko-fi.com/tokke2")))
        b_kofi.pack(side="left", padx=6)
        b_fri = ttk.Button(btnrad, text="",
                           command=lambda: open_externally(
                               Path("https://paypal.me/Rickard3dPrint")))
        b_fri.pack(side="left")

        swf = ttk.Frame(body, style="Card.TFrame")
        swf.pack(fill="x", pady=(4, 8))
        qr_lbl = ttk.Label(swf, background=self.C["surface"])
        qr_lbl.pack(pady=14)
        state = {"foto": None}

        def rita_qr(*_):
            """Samma som HTML-sidan (2026-10-15): endast QR-koden,
            ingen nummertext, ingen payload, inga knappar."""
            nr = "".join(ch for ch in
                         self.settings.get("swish_number", "")
                         if ch.isdigit())
            if len(nr) < 10:
                state["foto"] = None
                qr_lbl.configure(image="", text="")
                return
            try:
                png = qr_png_bytes(swish_payload(nr))
                import base64
                foto = tk.PhotoImage(data=base64.b64encode(png).decode())
                state["foto"] = foto
                qr_lbl.configure(image=foto, text="")
            except Exception as exc:
                qr_lbl.configure(image="", text=f"QR-fel: {exc}")

        tack = ttk.Label(win, text="", style="TLabel")
        tack.pack(anchor="w", padx=18, pady=(0, 14))

        def oversatt(*_):
            T = self.STOD_TEXT[lang.get()]
            win.title(T["titel"])
            rub.configure(text=T["titel"])
            und.configure(text=T["undre"])
            for nyckel, lbl, desc in tiers:
                lbl.configure(text=T[nyckel])
                desc.configure(text=T[nyckel + "d"])
            b_pay.configure(text=T["paypal"])
            b_kofi.configure(text=T["kofi"])
            b_fri.configure(text=T["valfritt"])
            tack.configure(text=T["tack"])
            rita_qr()

        lang.trace_add("write", oversatt)
        oversatt()

    # -- autoinstall av Python-tillägg vid start (2026-10-06) ---------
    PIP_PAKET = ("PyMuPDF", "pypdf", "pdfminer.six", "Pillow",
                 "pytesseract", "pystray")

    def _pip_jobba(self, paket: tuple, status_etikett, progress, win,
                   uppgradera: bool = False):
        """Kör pip i bakgrundstråd med live-rader till progressfönstret."""
        import subprocess
        args = [sys.executable, "-m", "pip", "install",
                "--disable-pip-version-check"]
        args += (["--upgrade"] if uppgradera else []) + list(paket)
        try:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace")
            sista = ""
            for rad in proc.stdout or []:
                rad = rad.strip()
                if rad:
                    sista = rad
                    self._post(lambda r=rad: status_etikett.configure(text=r[:90]))
            proc.wait(timeout=900)
            ok = proc.returncode == 0
        except Exception as exc:
            ok, sista = False, str(exc)
        self._h("tillägg", f"pip {'upgrade' if uppgradera else 'install'} "
                f"{list(paket)}: {'klart' if ok else 'MISSLYCKADES'} | {sista[:120]}",
                "ok" if ok else "err")

        def _klar():
            try:
                progress.stop()
            except Exception:
                pass
            status_etikett.configure(
                text=("Klart! Paket på plats." if ok
                      else f"Misslyckades: {sista[:70]}"))
            self.root.after(1600, win.destroy)
            if ok and self.tray is None and self.settings.get("tray_enabled", True) \
                    and TrayIcon is not None and tray_available():
                self.tray = TrayIcon(self)
                if self.tray.start():
                    self._h("systemfält", "Systemfältsikon startad efter "
                            "autoinstallation")
                else:
                    self.tray = None
            if ok:
                self._log("Python-tillägg installerade/uppdaterade: "
                          + ", ".join(paket), "ok")
        self._post(_klar)

    def _visa_progress(self, rubrik: str):
        tk, ttk = self.tk, self.ttk
        win = tk.Toplevel(self.root)
        win.after(80, lambda: dark_titlebar(win, bool(self.theme.dark)))
        win.title(rubrik)
        win.transient(self.root)
        win.resizable(False, False)
        try:
            win.configure(background=self.C["bg"])
        except Exception:
            pass
        ttk.Label(win, text=rubrik, style="TLabel").pack(
            anchor="w", padx=16, pady=(14, 6))
        bar = ttk.Progressbar(win, mode="indeterminate", length=380)
        bar.pack(padx=16)
        bar.start(12)
        etikett = ttk.Label(win, text="Startar …", style="Faint.TLabel",
                            wraplength=400)
        etikett.pack(anchor="w", padx=16, pady=(8, 14))
        return win, bar, etikett

    def _autoinstallera_tillagg(self) -> None:
        """Installera saknade pip-paket automatiskt vid start, med
        progress bar. Uppdatering via knappen i tilläggsdialogen."""
        try:
            st = backend_status()
            saknas = []
            if not st["pypdf"]:
                saknas.append("pypdf")
            try:
                from PIL import Image  # noqa: F401
            except Exception:
                saknas.append("Pillow")
            if not st["pytesseract"]:
                saknas.append("pytesseract")
            if not tray_available():
                saknas.append("pystray")
            if not saknas:
                self._tillaggserbjudande()
                return
            self._h("tillägg", f"Autoinstallerar saknade paket: {saknas}")
            win, bar, etikett = self._visa_progress(
                f"Installerar Python-tillägg ({', '.join(saknas)}) …")
            threading.Thread(target=self._pip_jobba,
                             args=(tuple(saknas), etikett, bar, win),
                             daemon=True, name="pdfsorter-autopip").start()
            self.root.after(4000, self._tillaggserbjudande)
        except Exception as exc:
            self._h("tillägg", f"Autoinstall kunde inte starta: {exc}", "warn")
            self._tillaggserbjudande()

    # -- tilläggserbjudande vid start (ANVÄNDARORDER 2026-09-28) -------
    def _tillaggserbjudande(self) -> None:
        """Erbjud installation av saknade tillägg vid start.

        Skannade PDF:er kräver Tesseract; utan det ser användaren bara
        röda felrader. Dialogen erbjuder pip-installation av Python-
        paketen och hämtlänk till Tesseract, med ny kontroll efteråt.
        Aldrig blockerande: hela bygget ligger i try/except och kan
        stängas av med 'Visa inte igen'.
        """
        try:
            saknade = missing_extensions()
            if not saknade or self.settings.get("extensions_offer_hidden"):
                return
            tk, ttk = self.tk, self.ttk
            win = tk.Toplevel(self.root)
            win.title(f"{APP_NAME} - komplettera installationen")
            win.transient(self.root)
            win.resizable(False, False)
            try:
                win.configure(background=self.C["bg"])
            except Exception:
                pass
            ttk.Label(win, text="Dessa tillägg saknas - appen fungerar "
                      "bättre med dem:", style="TLabel").pack(
                anchor="w", padx=16, pady=(14, 4))
            lista = tk.Listbox(win, height=min(6, len(saknade) + 1),
                               exportselection=False, activestyle="none",
                               background=self.C["surface"],
                               foreground=self.C["text"],
                               highlightthickness=0)
            lista.pack(fill="x", padx=16)
            for e in saknade:
                lista.insert("end", f"{e['namn']}  -  {e['beskr']}")
            ttk.Label(win, text="Tesseract: installera med standardsökväg "
                      "och bocka i Swedish under språkvalet.",
                      style="Faint.TLabel", wraplength=420).pack(
                anchor="w", padx=16, pady=(6, 0))
            status = tk.StringVar(value="")
            ttk.Label(win, textvariable=status, style="Faint.TLabel",
                      wraplength=440).pack(anchor="w", padx=16, pady=(4, 0))
            dolda = tk.BooleanVar(value=False)

            def _pip_installera():
                paket = [e["nyckel"] for e in missing_extensions()
                         if e["slag"] == "pip"]
                if not paket:
                    status.set("Inga Python-paket saknas - hämta Tesseract "
                               "och klicka sedan 'Kontrollera igen'.")
                    return
                status.set(f"Installerar {', '.join(paket)} …")

                def _jobb():
                    try:
                        r = subprocess.run(
                            [sys.executable, "-m", "pip", "install"] + paket,
                            capture_output=True, text=True, timeout=600)
                        sv = "klart" if r.returncode == 0 else "misslyckades"
                        tail = (r.stdout or r.stderr or "").strip().splitlines()
                        self._h("tillägg", f"pip install {paket}: {sv} "
                                f"| {tail[-1] if tail else ''}",
                                "ok" if r.returncode == 0 else "err")
                    except Exception as exc:
                        sv, tail = "misslyckades", [str(exc)]
                        self._h("tillägg", f"pip-installation: {exc}", "err")
                    def _uppd():
                        status.set(f"pip-installationen {sv}: "
                                   f"{tail[-1] if tail else ''}  "
                                   "Klicka 'Kontrollera igen'.")
                    self._post(_uppd)
                threading.Thread(target=_jobb, daemon=True,
                                 name="pdfsorter-pip").start()

            def _kolla_igen():
                kvar = missing_extensions()
                if not kvar:
                    status.set("Alla tillägg på plats! Stäng dialogen och "
                               "kör Sortera nu igen.")
                    self._log("Alla valfria tillägg är nu installerade.", "ok")
                else:
                    lista.delete(0, "end")
                    for e in kvar:
                        lista.insert("end", f"{e['namn']}  -  {e['beskr']}")
                    status.set(f"Kvar att installera: "
                               f"{', '.join(e['nyckel'] for e in kvar)}")

            def _stang():
                if dolda.get():
                    self.settings["extensions_offer_hidden"] = True
                    save_settings(self.settings)
                    self._h("tillägg", "Tilläggsdialogen avstängd permanent")
                win.destroy()

            btns = ttk.Frame(win)
            btns.pack(fill="x", padx=16, pady=12)
            ttk.Button(btns, text="Installera Python-paket",
                       command=_pip_installera).pack(side="left")

            def _auto_tess():
                status.set("Installerar Tesseract + svenska … detta kan ta "
                           "några minuter. Eventuellt UAC-fönster visas.")

                def _jobb():
                    ok, msg = auto_install_tesseract()
                    self._h("tillägg", f"autoinstall Tesseract: {msg}",
                            "ok" if ok else "err")
                    self._post(lambda: status.set(
                        f"{msg}  Klicka sedan 'Kontrollera igen'."))
                threading.Thread(target=_jobb, daemon=True,
                                 name="pdfsorter-tessinstall").start()

            def _uppdatera_paket():
                win2, bar2, et2 = self._visa_progress("Uppdaterar Python-paket …")
                threading.Thread(
                    target=self._pip_jobba,
                    args=(self.PIP_PAKET, et2, bar2, win2, True),
                    daemon=True, name="pdfsorter-pipupgrade").start()

            ttk.Button(btns, text="Uppdatera Python-paket",
                       command=_uppdatera_paket).pack(side="left", padx=8)
            if sys.platform.startswith("win"):
                ttk.Button(btns, text="Installera Tesseract automatiskt",
                           command=_auto_tess).pack(side="left", padx=8)

                def _hamta_svenska():
                    status.set("Hämtar svenskt språkpaket …")

                    def _jobb():
                        _sys_mod._se_till_svenska()
                        kvar = "klart" if not svenska_saknas() else "missades"
                        self._h("tillägg", f"swe.traineddata: {kvar}",
                                "ok" if kvar == "klart" else "err")
                        self._post(lambda: status.set(
                            f"Svenska: {kvar}. Klicka 'Kontrollera igen'."))
                    threading.Thread(target=_jobb, daemon=True,
                                     name="pdfsorter-swe").start()

                if any(e["slag"] == "sprak" for e in saknade):
                    ttk.Button(btns, text="Hämta svenska",
                               command=_hamta_svenska).pack(
                        side="left", padx=8)

                def _spara_tess(hit: str) -> None:
                    self.settings["tesseract_path"] = hit
                    save_settings(self.settings)
                    set_tesseract_path(hit)
                    self._h("tillägg", f"Tesseract hittad och sparad: {hit}",
                            "ok")
                    status.set(f"Hittad: {hit}  Klicka 'Kontrollera igen'.")

                def _bladdra():
                    hit = self.filedialog.askopenfilename(
                        parent=win, title="Välj tesseract.exe",
                        filetypes=[("Program", "*.exe"), ("Alla", "*.*")])
                    if not hit:
                        return
                    if Path(hit).name.lower() != "tesseract.exe":
                        status.set("Välj själva tesseract.exe-filen.")
                        return
                    _spara_tess(hit)

                def _sok_datorn():
                    status.set("Söker igenom sannolika installationsställen …")

                    def _jobb():
                        hit = search_tesseract()
                        self._h("tillägg",
                                f"sökning efter tesseract.exe: "
                                f"{hit or 'ingen träff'}")
                        self._post(lambda: (
                            _spara_tess(hit) if hit else status.set(
                                "Hittade ingen tesseract.exe på vanliga "
                                "ställen - använd 'Bläddra…' eller "
                                "'Installera Tesseract automatiskt'.")))
                    threading.Thread(target=_jobb, daemon=True,
                                     name="pdfsorter-tesssok").start()

                if any(e["nyckel"] == "tesseract" for e in saknade):
                    ttk.Button(btns, text="Sök datorn",
                               command=_sok_datorn).pack(side="left", padx=8)
                    ttk.Button(btns, text="Bläddra…",
                               command=_bladdra).pack(side="left")
            ttk.Button(btns, text="Hämta Tesseract…",
                       command=lambda: open_externally(
                           Path(TESSERACT_URL)) or None).pack(side="left", padx=8)
            ttk.Button(btns, text="Kontrollera igen",
                       command=_kolla_igen).pack(side="left")
            ttk.Button(btns, text="Stäng", command=_stang).pack(
                side="right", padx=(8, 0))
            ttk.Checkbutton(win, variable=dolda,
                            text="Visa inte detta igen").pack(
                anchor="w", padx=16, pady=(0, 12))
            self._h("tillägg", f"Tilläggsdialog visad: "
                    f"{', '.join(e['nyckel'] for e in saknade)}")
        except Exception as exc:
            self._h("tillägg", f"Tilläggsdialogen kunde inte visas: {exc}",
                    "warn")

    def _copy_support_log(self) -> None:
        """Kopiera ett komplett diagnostikpaket till urklipp (LÅNAT MÖNSTER
        L1): systeminfo + inställningar + motorstatus + autostart + hela
        sessionsloggen + svansarna från errors/krasch. Klistra in i en
        felanmälan så syns exakt vad som körde och vad som hände."""
        self._ui("Kopiera diagnostik för support")
        try:
            paket = build_diagnostics()
        except Exception as exc:
            self._fel(exc, "diagnostik")
            self.messagebox.showerror(APP_NAME,
                                      f"Kunde inte bygga diagnostiken:\n{exc}",
                                      parent=self.root)
            return
        fil = session_path() or latest_session_log()
        if not fil:
            self.messagebox.showwarning(APP_NAME, "Ingen loggfil hittades.",
                                        parent=self.root)
            return
        try:
            logg = fil.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.messagebox.showerror(APP_NAME, f"Kunde inte läsa loggen:\n{exc}",
                                      parent=self.root)
            return
        innehåll = paket + "\n\n" + logg
        # Kappta aldrig slutet: de sista raderna är där felet syns.
        if len(innehåll) > 400_000:
            innehåll = ("(början avkapad för urklippets skull)\n"
                        + innehåll[-400_000:])
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(innehåll)
        except Exception as exc:
            self._fel(exc, "urklipp")
            self.messagebox.showerror(
                APP_NAME,
                f"Kunde inte nå urklippet. Loggen ligger här:\n{fil}",
                parent=self.root)
            return
        self._h("support", f"Diagnostik kopierad till urklipp: {fil} "
                f"({len(innehåll)} tecken)")
        self.messagebox.showinfo(
            APP_NAME,
            f"Diagnostiken är kopierad ({len(innehåll):,} tecken):\n"
            f"systeminfo, inställningar, motorstatus och hela loggen.\n\n"
            f"Klistra in den i felanmälan - mottagaren ser direkt vad "
            f"som hände.\n\nLogfilen: {fil}", parent=self.root)

    def _open_log_dir(self) -> None:
        self._ui("Öppna log-mappen")
        try:
            d = session_dir()
            d.mkdir(parents=True, exist_ok=True)
            open_externally(d)
        except Exception as exc:
            self._fel(exc, "öppna log-mappen")

    def _save_help(self) -> None:
        path = self.filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".txt",
            initialfile="ArkivPiloten - hjalp.txt",
            filetypes=[("Textfil", "*.txt")])
        if not path:
            return
        try:
            Path(path).write_text(help_as_text(), encoding="utf-8")
            self.messagebox.showinfo(APP_NAME, f"Hjälpen sparad:\n{path}",
                                     parent=self.root)
        except OSError as exc:
            self.messagebox.showerror(APP_NAME, f"Kunde inte spara:\n{exc}",
                                      parent=self.root)

    # ======================================================================
    # Fönster och systemfält
    # ======================================================================
    def show_window(self, reason: str = "") -> None:
        """Visa fönstret igen från systemfältet."""
        try:
            lever = self.root.winfo_exists()
        except Exception:
            lever = False
        if not lever:
            self._h("fönster", f"KAN INTE visa fönstret ({reason}): "
                    "huvudfönstret finns inte längre - starta om appen",
                    "err")
            return
        self._h("fönster",
                f"Fönstret visas ({reason or 'anledning ej angiven'})")
        try:
            self.root.deiconify()
            self.root.state("normal")
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(300, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        except Exception as exc:
            self._fel(exc, "show_window")
        self.visible = True
        self._sync_tray()
        # Beta av kön som samlats medan fönstret var gömt
        if self.queue and self.settings.get("ask_when_unsure", True):
            self.root.after(250, self._process_queue)

    def hide_window(self, reason: str = "") -> None:
        """Göm fönstret - appen fortsätter i systemfältet."""
        if not self.tray:
            self._h("fönster", f"Fönstret minimeras till aktivitetsfältet "
                    f"({reason or 'anledning ej angiven'}) - systemfält saknas, "
                    "kan inte gömmas helt")
            self.root.iconify()
            return
        try:
            self.root.withdraw()
        except Exception as exc:
            self._fel(exc, "hide_window")
            return
        self._h("fönster", f"Fönstret döljs ({reason or 'anledning ej angiven'}) - "
                "appen fortsätter i systemfältet")
        self.visible = False
        self._sync_tray()
        if not getattr(self, "_hide_hint_shown", False):
            self._hide_hint_shown = True
            self._notify("Fortsätter i bakgrunden. Klicka på ikonen i "
                         "systemfältet för att öppna igen.")

    def show_review(self) -> None:
        """Öppna granskningsfliken från systemfältet."""
        self.show_window()
        self.nb.select(self.tab_review)

    def _on_unmap(self, event=None) -> None:
        """Minimering ska hamna i systemfältet i stället för aktivitetsfältet."""
        if (event is not None and event.widget is not self.root):
            return
        if self.tray and self.settings.get("close_to_tray", True) \
                and self.root.state() == "iconic":
            self._h("fönster", "Användaren minimerade - flyttas till systemfältet")
            self.root.after(10, lambda: self.hide_window("minimering"))
        elif self.root.state() == "iconic":
            self._h("fönster", "Användaren minimerade - blir kvar i "
                    "aktivitetsfältet (close_to_tray av eller inget systemfält)")

    def _sync_tray(self) -> None:
        if self.tray:
            self.tray.refresh()

    def _notify(self, message: str) -> None:
        if self.tray and self.settings.get("notify", True):
            self.tray.notify(message)

    def quit_app(self) -> None:
        """Avsluta appen på riktigt."""
        self._h("avslut", "Avsluta begärt (quit_app)")
        self._quitting = True
        self._on_close()

    def _on_close(self) -> None:
        # Krysset minimerar till systemfältet om det är påslaget
        if not self._quitting and self.tray and self.settings.get("close_to_tray", True):
            self.hide_window("krysset - close_to_tray är påslaget")
            return
        self._h("avslut", "Appen avslutas: inställningar samlas, bevakning "
                "stoppas, regler och historik sparas")
        try:
            self._collect_settings()
            if self.watcher:
                self.watcher.stop()
            self.rules.save()
            try:
                flush_history()
            except Exception as exc:
                session_error("avslut", exc)
        except Exception as exc:
            session_error("avslut", exc)
        if self.tray:
            self.tray.stop()
            self.tray = None
        try:
            close_session()      # stäng sessionsloggen snyggt
        except Exception:
            pass
        try:
            self.root.quit()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self) -> None:
        self.root.mainloop()
        # Zombieskydd (buggfix 2026-10-15): om huvudfönstret rivits
        # (t.ex. av en felrapport) men en tray-tråd fortfarande håller
        # processen vid liv, skulle instanslåset hållas av en zombie som
        # inte kan visa sitt fönster ("går inte att öppna efter tray").
        # Avsluta då hårt - låset med dött PID övertas ändå korrekt.
        try:
            lever = self.root.winfo_exists()
        except Exception:
            lever = False
        if not lever or self._quitting:
            try:
                flush_history()
                flush_learned()
                self.rules.save()
            except Exception:
                pass
            session_log("avslut", "Mainloop slut med dött fönster - "
                        "avslutar processen (zombieskydd)", "warn")
            os._exit(0)


# ==========================================================================
# DEL 6 - KOMMANDORAD
# ==========================================================================

def _self_check() -> int:
    """Självtest (2026-10-16): fångar hela buggklassen "namn som används
    men aldrig importerades" (json_dir/search_tesseract/shutil) plus
    matchningsregressioner - utan att röra användardata."""
    fel = 0

    def rad(namn: str, ok: bool, detalj: str = "") -> None:
        nonlocal fel
        print(f"  {'OK  ' if ok else 'FEL '} {namn}{(' - ' + detalj) if detalj and not ok else ''}")
        if not ok:
            fel += 1

    print(f"{APP_NAME} {APP_VERSION} - självtest")
    versioner = _module_versions()
    rad("alla fem moduler har samma version", len(set(versioner.values())) == 1,
        str(versioner))
    # Importytan mot systemmodulen: varje namn GUI/CLI anropar måste finnas.
    for namn in ("search_tesseract", "auto_install_tesseract",
                 "check_for_update", "perform_update",
                 "update_python_packages", "autostart_status",
                 "tag_pdf_metadata", "export_year_archive",
                 "lookup_company_name_online",
                 "sync_autostart", "set_autostart", "brand_window",
                 "ensure_icon_file", "write_icon_file", "svenska_saknas"):
        rad(f"namn finns: {namn}", callable(globals().get(namn)))
    # Matchningsregressioner (samma fall som testsuiten):
    regler = Rules()
    regler.add_keywords("Pilkington", ["pilkington", "glas"], weight=1.0)
    loptext = Extraction(path=Path("x.pdf"), text=(
        "Kund AB\nStorgatan 1\n\nVi monterade glas från Pilkington i "
        "förra veckan. Deras glas nämns här i text. Detta kommer från Kund AB."))
    rad("bara löptext -> fråga", decide(regler, loptext, dict(DEFAULT_SETTINGS)).status == "ask")
    huvud = Extraction(path=Path("x.pdf"), text=(
        "Pilkington Sverige AB\nStorgatan 1\n\nFaktura\nVi hänvisar till "
        "ert glas och er montering. Belopp att betala inom trettio dagar. Tack!"))
    rad("avsändarhuvud -> auto", decide(regler, huvud, dict(DEFAULT_SETTINGS)).status == "auto")
    org = next(f"556033908{d}" for d in "0123456789"
               if _luhn_ok(f"556033908{d}"))
    regler2 = Rules(); regler2.add_keywords("Pilkington", [f"{org[:6]}-{org[6:]}"])
    dok = Extraction(path=Path("x.pdf"), text=(
        f"Annan Firma\nRad två\n\nFaktura\nOrg.nr {org[:6]}-{org[6:]}\n" + "Text " * 20))
    rad("bevisat org.nr -> auto", decide(regler2, dok, dict(DEFAULT_SETTINGS)).status == "auto")
    if SYSTEM_MODULE:
        rad("ikon 16px renderas", make_icon_image(16) is not None)
        st = autostart_status()
        rad("autostart-status svarar", isinstance(st, dict) and "klass" in st)
    print("SJÄLVTEST:", "ALLT OK" if not fel else f"{fel} FEL")
    return 1 if fel else 0


def build_diagnostics() -> str:
    """ETT klistra-in-block för support (LÅNAT MÖNSTER L1).

    Systeminfo + inställningar + motorstatus + autostart + loggsvansar.
    Användaren kopierar blocket och klistrar in det i en felanmälan -
    mottagaren ser direkt vad som kör, hur det är konfigurerat och vad
    som hände precis innan felet.
    """
    rader: List[str] = []
    rader.append("=" * 72)
    rader.append(f"{APP_NAME} {APP_VERSION} - DIAGNOSTIK "
                 f"(klistra in detta i felanmälan)")
    rader.append("=" * 72)
    rader.append(f"Python:      {sys.version.split()[0]}  "
                 f"Plattform: {sys.platform}")
    rader.append(f"Moduler:     {_module_versions()}")
    rader.append(f"Konfiguration: {config_dir()} ({config_dir_mode()})")
    try:
        s = load_settings()
        rader.append("Inställningar:")
        for k in sorted(s):
            v = s[k]
            if isinstance(v, list) and len(str(v)) > 200:
                v = f"[{len(v)} st]"
            rader.append(f"    {k} = {v}")
    except Exception as exc:
        rader.append(f"Inställningar: KUNDE INTE LÄSAS ({exc})")
    try:
        regler = Rules.load()
        rader.append(f"Regler:      {len(regler.categories)} kategorier, "
                     f"{sum(len(c['keywords']) for c in regler.categories)} stödord")
    except Exception as exc:
        rader.append(f"Regler:      KUNDE INTE LÄSAS ({exc})")
    try:
        rader.append("Läsmotorer:  " + ", ".join(
            f"{k}={'ja' if v else 'nej'}" for k, v in backend_status().items()))
        h = reading_health()
        if h["senaste_ocr_konfidens"] >= 0:
            rader.append(f"Senaste OCR: {h['senaste_ocr_sekunder']} s, "
                         f"konfidens {h['senaste_ocr_konfidens']}")
    except Exception:
        pass
    try:
        rader.append(f"Autostart:   {'på' if autostart_enabled() else 'av'}, "
                     f"klass: {classify_autostart()}, "
                     f"källa: {autostart_status().get('source') or '-'}, "
                     f"session: {'ja' if autostart_session_available() else 'nej'}")
        for namn, varde in get_autostart_conflicts():
            rader.append(f"  KONFLIKT:  {namn} -> {varde[:100]}")
    except Exception:
        pass

    def _svans(fil: Path, antal: int, etikett: str) -> None:
        try:
            if fil and fil.exists():
                rader.append("")
                rader.append(f"--- {etikett}: {fil} (sista {antal} raderna) ---")
                rader.extend(fil.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()[-antal:])
        except OSError:
            pass

    _svans(session_path() or latest_session_log(), 150, "Sessionslogg")
    try:
        import pdfsorter_system as _s
        _svans(_s._month_log_path("errors"), 50, "errors.log")
    except Exception:
        pass
    try:
        _svans(session_dir() / "krasch.log", 50, "krasch.log")
    except Exception:
        pass
    return "\n".join(rader)


def run_cli(args: argparse.Namespace) -> int:
    settings = load_settings()
    if args.input:
        settings["input_dir"] = args.input
    if args.output:
        settings["output_dir"] = args.output
    if args.no_ask:
        settings["ask_when_unsure"] = False
    if args.dry_run:
        settings["dry_run"] = True
    if args.copy:
        settings["action"] = "copy"
    excludes = list(args.exclude or []) + list(settings.get("exclude_dirs", []))

    rules = Rules.load(Path(args.rules) if args.rules else None)
    indir, outdir = Path(settings["input_dir"]), Path(settings["output_dir"])
    if not indir.is_dir():
        print(f"Inmappen finns inte: {indir}", file=sys.stderr)
        return 2
    if not settings["output_dir"]:
        print("Ingen utmapp angiven (--output).", file=sys.stderr)
        return 2
    outdir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    flush_learned()   # N14: eventuell träning från tidigare process i hamn

    def emit(msg: str) -> None:
        if not args.json:
            print(msg, flush=True)

    engine = SortEngine(rules, settings,
                        log=lambda m, lvl="info": (
                            session_log("sortering", m, lvl),
                            emit(f"  [{lvl}] {m}")))

    def handle(path: Path) -> None:
        decision = engine.analyze(path)
        row = {"file": str(path), "status": decision.status, "reason": decision.reason}
        if decision.status == "auto":
            best = decision.best
            zon = ", ".join(f"{w}:{best.zone_of(w)}" for w in best.matched[:4])
            mp = getattr(best, "multipage", None)
            session_log("sortering",
                        f"{path.name} -> {best.name}  poäng {best.score:g}  "
                        f"[{zon}]" + (f"  [flersidig: {', '.join(mp)}]" if mp else ""))
            ok, msg = engine.apply(decision, best.name, best.matched, "auto")
            row.update({"category": best.name, "score": best.score, "ok": ok, "target": msg})
            emit(f"{'[TEST] ' if settings['dry_run'] else ''}{path.name}"
                 f"  ->  {best.name}  ({best.score:g})"
                 + ("  [OCR]" if decision.extraction.used_ocr else "")
                 + ("" if ok else f"   FEL: {msg}"))
        elif decision.status == "error":
            row["ok"] = False
            session_log("sortering", f"{path.name}  FEL: {decision.reason}", "err")
            emit(f"{path.name}  FEL: {decision.reason}")
        elif decision.status == "ignored":
            row["ok"] = True
            session_log("sortering", f"{path.name}  ignorerad: {decision.reason}")
            emit(f"{path.name}  ⊘ {decision.reason} - lämnas orörd")
        else:
            ok, msg = engine.send_to_unmatched(decision)
            row.update({"category": None, "ok": ok, "target": msg})
            session_log("sortering", f"{path.name}  OSÄKER: {decision.reason} -> "
                        f"{'_Osorterat' if ok else 'lämnad'}", "warn")
            emit(f"{path.name}  OSÄKER: {decision.reason}"
                 f"  -> {'_Osorterat' if ok else 'lämnad i inmappen'}")
            if args.verbose:
                cands = suggest_keywords(decision.extraction.combined, path.name,
                                         limit=int(settings.get("keywords_per_file", 10)),
                                         existing=rules.all_keyword_texts())
                for c in cands:
                    emit(f"      förslag: {c.display}   ({c.label}, {c.count} ggr, {c.score:.2f})")
        results.append(row)

    if args.watch:
        emit(f"Bevakar {indir} — avsluta med Ctrl+C")
        watcher = FolderWatcher(indir, handle,
                                interval=float(settings.get("watch_interval", 5.0)),
                                stable_seconds=float(settings.get("stable_seconds", 3.0)),
                                recursive=bool(settings.get("recursive", False)),
                                excludes=excludes)
        watcher.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            watcher.stop()
            emit("\nAvslutad.")
        return 0

    files = list_pdfs(indir, bool(settings.get("recursive", False)), excludes)
    emit(f"{len(files)} PDF-filer i {indir}")
    for path in files:
        try:
            handle(path)
        except Exception as exc:
            emit(f"{path.name}  FEL: {exc}")
    if args.json:
        print(json.dumps({"results": results, "stats": dict(engine.stats)},
                         ensure_ascii=False, indent=2))
    else:
        s = engine.stats
        emit(f"\nKlart: {s['sorted']} sorterade, {s['unmatched'] + s['left']} osäkra, {s['error']} fel")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    # Sätts före första fönstret så att Windows visar vår egen ikon i
    # aktivitetsfältet i stället för Pythons fjäder - även vid autostart
    # (pythonw ... --tray), som inte går via pdfsorter.pyw. Ofarligt no-op
    # utanför Windows.
    set_app_user_model_id()
    # Före första fönstret: DPI-medvetenhet på Windows, annars blir
    # typsnitt/färger suddiga på HiDPI-skärmar (multi-OS-design).
    set_process_dpi_aware()

    # LOGGA ALLT (användarorder 2026-09-07): sessionsloggen öppnas först
    # av allt, så att varje händelse i den här körningen hamnar i filen.
    # excepthookarna fångar dessutom fel i ALLA trådar till loggen.
    start_session([
        f"Kommandorad:   {' '.join(sys.argv)}",
        f"Arbetskatalog: {Path.cwd()}",
    ])
    install_excepthooks()
    if compact_history_if_large():
        session_log("start", "Historikjournalen kompakterades vid start "
                    "(>200 rader) - snabbare start", "ok")
    flyttade = migrate_to_portable()
    if flyttade:
        session_log("start", f"Portabel start: kopierade data från gamla "
                    f"OS-platsen till appmappen: {', '.join(flyttade)}", "ok")
    session_log("start", f"Datamapp: {config_dir()}")
    session_log("start", "main() börjar - argument tolkas")

    p = argparse.ArgumentParser(
        prog="pdfsorter",
        description=f"{APP_NAME} {APP_VERSION} - sorterar PDF-filer till undermappar.",
        epilog="Utan argument öppnas det grafiska gränssnittet. "
               "Du kan alltså bara dubbelklicka på filen.")
    p.add_argument("--input", "-i", help="Inmapp med PDF-filer")
    p.add_argument("--output", "-o", help="Utmapp där undermappar skapas")
    p.add_argument("--rules", help="Sökväg till en egen rules.json")
    p.add_argument("--watch", action="store_true", help="Bevaka mappen kontinuerligt")
    p.add_argument("--no-ask", action="store_true",
                   help="Fråga aldrig; osäkra filer lämnas eller går till _Osorterat")
    p.add_argument("--dry-run", action="store_true", help="Testkör, ändra inget på disk")
    p.add_argument("--copy", action="store_true", help="Kopiera i stället för att flytta")
    p.add_argument("--exclude", action="append", default=None,
                   metavar="MAPP",
                   help="Mapp som hoppas över (även inuti inmappen); "
                        "kan upprepas")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Visa stödordsförslag för osäkra filer")
    p.add_argument("--json", action="store_true", help="Skriv ut resultatet som JSON")
    p.add_argument("--status", action="store_true",
                   help="Visa vilka PDF-motorer och tillägg som hittats")
    p.add_argument("--diagnostik", action="store_true",
                   help="Skriv ut ett komplett diagnostikpaket för support")
    p.add_argument("--tray", action="store_true",
                   help="Starta minimerad i systemfältet (används vid autostart)")
    p.add_argument("--install-autostart", action="store_true",
                   help="Slå på autostart med operativsystemet och avsluta")
    p.add_argument("--remove-autostart", action="store_true",
                   help="Stäng av autostart och avsluta")
    p.add_argument("--make-shortcut", action="store_true",
                   help="Skapa en genväg på skrivbordet och avsluta")
    p.add_argument("--save-icon", metavar="FIL",
                   help="Spara appikonen till en fil och avsluta")
    p.add_argument("--report", action="store_true",
                   help="Skapa en Markdown-rapport över matchningen och avsluta")
    p.add_argument("--report-days", type=int, default=10,
                   help="Hur många dagar rapporten ska täcka (standard 10)")
    p.add_argument("--check", action="store_true",
                   help="Kör självtest (importer, matchning, ikon) och avsluta")
    p.add_argument("--check-update", action="store_true",
                   help="Kontrollera om en nyare version finns på GitHub och avsluta")
    p.add_argument("--update", action="store_true",
                   help="Uppdatera appen från GitHub (appmappen) + Python-paketen och avsluta")
    p.add_argument("--export-archive", metavar="MAPP",
                   help="exportera årsarkiv (öppen mapp + index.html) till MAPP")
    p.add_argument("--lookup-orgnr", metavar="ORGNR",
                   help="slå upp firmanamn för ett organisationsnummer")
    p.add_argument("--install-packages", action="store_true",
                   help="Installera/uppdatera alla Python-tillägg från requirements.txt och avsluta")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    args = p.parse_args(argv)

    if args.diagnostik:
        print(build_diagnostics())
        return 0

    if args.status:
        print(f"{APP_NAME} {APP_VERSION}")
        print(status_text())
        print(f"Läsmodul:    {'pdfsorter_read.py laddad' if READ_MODULE else 'SAKNAS'}")
        print(f"Datamodul:   {'pdfsorter_data.py laddad' if DATA_MODULE else 'SAKNAS'}")
        print(f"Systemmodul: {'pdfsorter_system.py laddad' if SYSTEM_MODULE else 'SAKNAS - ikon, systemfält och autostart avstängda'}")
        print(f"Temamodul:   {'pdfsorter_theme.py laddad' if THEME_MODULE else 'SAKNAS - grått standardutseende'}")
        print(f"Systemfält: {'ja' if tray_available() else 'nej (pip install pystray)'}")
        _as = autostart_status()
        print(f"Autostart:  {'på' if _as['enabled'] else 'av'}"
              f" (klass: {_as['klass']}, källa: {_as.get('source') or '-'}, "
              f"session: {'ja' if _as.get('session', True) else 'nej'}, "
              f"{_as['platform']})")
        print(f"Konfiguration: {config_dir()} ({config_dir_mode()})")
        print(f"Versioner:  {_module_versions()}")
        if VERSIONS_BLANDADE:
            print("VARNING: blandade modulversioner - kopiera ALLA fem "
                  "filer från senaste leveransen.")
        if OLD_READ_MODULE:
            print("VARNING: gammal pdfsorter_read.py - OCR-brustolerans "
                  "och nya läsforbättringar är avstängda.")
        _lås = InstanceLock()
        if _lås.acquire():
            _lås.release()
            print("Instans:    ingen annan kör")
        else:
            print(f"Instans:    KÖR REDAN (PID {_lås.other_pid}, "
                  f"startad {_lås.other_started or 'okänt'})")
            print(f"            lås: {lock_path()}")
        for k, v in backend_status().items():
            print(f"  {k:16s} {'ja' if v else 'nej'}")
        hälsa = reading_health()
        if hälsa["senaste_ocr_konfidens"] >= 0:
            print(f"  Senaste OCR:     {hälsa['senaste_ocr_sekunder']} s, "
                  f"konfidens {hälsa['senaste_ocr_konfidens']}")
        senaste = latest_session_log()
        if senaste:
            print(f"Sessionslogg: {senaste}")
        return 0

    if args.check:
        return _self_check()

    if args.check_update or args.update:
        info = check_for_update()
        if not info.get("ok"):
            print(f"Kunde inte söka uppdatering: {info.get('error', '?')}")
            return 1
        kalla = ("GitHub Releases" if info.get("source") == "release"
                 else "GitHub main-grenen")
        print(f"Installerad version: {info['current']}  |  "
              f"Senaste på GitHub: {info['remote']}  ({kalla})")
        if info.get("release_url"):
            print(f"Release: {info['release_url']}")
        if info.get("source") == "release":
            print("Kontrollsumma: "
                  + ("ja (verifieras före installation)"
                     if info.get("sha256_url") else "SAKNAS - frågar i GUI"))
        if not info.get("available"):
            print("Du har redan den senaste versionen.")
            return 0
        if not args.update:
            print("En uppdatering finns! Kör med --update för att installera den.")
            return 0
        ok, msg = perform_update()
        print(msg)
        if not ok:
            return 1
        ok2, msg2 = update_python_packages()
        print(msg2)
        session_log("uppdatering", "Klar via --update (starta om appen)", "ok")
        return 0 if ok2 else 1

    if args.export_archive:
        out = Path(load_settings().get("output_dir", "") or "")
        if not out.is_dir():
            print("Utmappen är inte inställd eller saknas.")
            return 1
        res = export_year_archive(out, Path(args.export_archive),
                                  log=lambda m: print(m))
        print(f"Export klart: {res['filer']} filer -> {res['mapp']} "
              f"({res['fel']} fel)")
        return 0 if res["fel"] == 0 else 1
    if args.lookup_orgnr:
        namn = lookup_company_name_online(args.lookup_orgnr)
        print(f"{args.lookup_orgnr}: {namn or '(inget namn hittades)'}")
        return 0 if namn else 1
    if args.install_packages:
        ok, msg = update_python_packages()
        print(msg)
        return 0 if ok else 1

    if args.install_autostart or args.remove_autostart:
        vill = bool(args.install_autostart)
        ok, msg = set_autostart(vill)
        # Inställningen måste sparas också: annars tar GUI:ts självläkande
        # synk (settings.autostart=False) bort posten vid nästa start -
        # --install-autostart blev i praktiken en engångsstart.
        if ok:
            try:
                s = load_settings()
                s["autostart"] = vill
                save_settings(s)
                msg += " (inställningen sparad)"
            except Exception as exc:
                session_error("autostart", exc)
                print(("Autostart påslagen: " if vill
                       else "Autostart avstängd: ") + msg)
                print("VARNING: inställningen kunde inte sparas, så appens "
                      "synk kan ändra autostarten vid nästa start.\n"
                      f"Fel: {type(exc).__name__}: {exc}")
                return 1
        session_log("autostart", ("Påslagen: " if vill else "Avstängd: ")
                    + msg, "ok" if ok else "err")
        print(("Autostart påslagen: " if vill else "Autostart avstängd: ")
              + msg)
        return 0 if ok else 1

    if args.make_shortcut:
        ok, msg = create_desktop_shortcut()
        session_log("genväg", ("Skapad: " if ok else "Misslyckades: ") + msg,
                    "ok" if ok else "err")
        print(("Genväg skapad: " if ok else "Misslyckades: ") + msg)
        return 0 if ok else 1

    if args.save_icon:
        result = write_icon_file(Path(args.save_icon))
        session_log("ikon", f"Sparad: {result}" if result
                    else "Kunde inte sparas (kräver Pillow)",
                    "ok" if result else "err")
        print(f"Ikon sparad: {result}" if result else "Kunde inte spara ikonen (kräver Pillow)")
        return 0 if result else 1

    if args.report:
        days = max(1, args.report_days or 10)
        text = build_matching_report(days)
        out = report_path()
        try:
            out.write_text(text, encoding="utf-8")
            session_log("rapport", f"Matchningsrapport sparad: {out} ({days} dagar)")
            print(f"Matchningsrapport sparad i:\n{out}\n")
            print(text)
            return 0
        except OSError as exc:
            print(f"Kunde inte skriva rapporten: {exc}", file=sys.stderr)
            return 1

    headless = any([args.input, args.output, args.watch, args.no_ask,
                    args.dry_run, args.json, args.copy])
    if headless:
        session_log("cli", "Kommandoradskörning (headless) startar")
        kod = run_cli(args)
        session_log("cli", f"Kommandoradskörning klar, slutkod {kod}")
        return kod

    try:
        import tkinter  # noqa: F401
    except Exception:
        msg = ("Det grafiska gränssnittet kräver Tkinter, som saknas.\n\n"
               "Debian/Ubuntu:  sudo apt install python3-tk\n"
               "Fedora:         sudo dnf install python3-tkinter\n\n"
               "Du kan ändå köra utan fönster:\n"
               "  python pdfsorter.py --input MAPP --output MAPP --no-ask")
        session_log("start", "Tkinter saknas - GUI kan inte startas", "err")
        print(msg, file=sys.stderr)
        return 1

    # Bara en instans åt gången får äga rules.json. Kör en redan, be den
    # visa sitt fönster i stället för att starta en andra kopia - två appar
    # skriver över varandras regler utan att någon märker det.
    lås = InstanceLock()
    if not lås.acquire():
        session_log("start", f"En instans kör redan (PID {lås.other_pid}) - "
                    "ber den visa fönstret; den här processen avslutas")
        request_show()
        print(f"{APP_NAME} kör redan (PID {lås.other_pid}).\n"
              f"Det befintliga fönstret öppnas i stället.")
        try:
            import tkinter as _tk_l
            from tkinter import messagebox as _mb_l
            _r = _tk_l.Tk(); _r.withdraw()
            brand_window(_r)
            _mb_l.showinfo(
                APP_NAME,
                f"{APP_NAME} kör redan.\n\n"
                f"Det fönstret öppnas nu. Leta annars efter ikonen i "
                f"systemfältet.")
            _r.destroy()
        except Exception:
            pass
        return 0

    hjälpare = install_helpers()   # skapa .pyw / .command vid första start
    if hjälpare:
        session_log("start", f"Starthjälpfiler skapade: {', '.join(hjälpare)}")
    session_log("start", f"GUI startar (startar gömd i systemfältet: {args.tray})")
    try:
        App(start_hidden=args.tray).run()
    finally:
        lås.release()
    session_log("avslut", "main() avslutas normalt")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except KeyboardInterrupt:
        sys.exit(130)
    except BaseException as _exc:       # noqa: BLE001 - sista utvägen
        _crash_report(_exc)
        sys.exit(1)
