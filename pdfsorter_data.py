#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lagring och filhantering för ArkivPiloten.
========================================

Allt som rör disken: var inställningarna bor, hur JSON-filerna läses och
skrivs, reglerna som styr matchningen, historiken - och själva flytten av
en PDF till rätt mapp.

Modulen känner inte till vare sig matchning eller gränssnitt. Den vet bara
hur data sparas och hur en fil hamnar där den ska, vilket gör den möjlig
att testa och återanvända helt utan Tkinter.

    python3 pdfsorter_data.py --check      självtest
    python3 pdfsorter_data.py --var        visa var filerna sparas
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unicodedata
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Reglerna lagras med normaliserad text, så modulen behöver samma
# normalisering som läsmodulen använder. Saknas läsmodulen kan appen ändå
# inte läsa PDF, men lagringen ska gå att importera och testa ändå - därför
# en enkel reserv i stället för ett hårt krav.
try:
    from pdfsorter_read import normalize
except ImportError:                                  # pragma: no cover
    def normalize(text: str) -> str:                 # type: ignore[misc]
        """Reserv: gemener, ihopdragna mellanslag, borttagna diacritics."""
        text = unicodedata.normalize("NFKD", str(text or ""))
        text = "".join(c for c in text if not unicodedata.combining(c))
        return re.sub(r"\s+", " ", text).strip().lower()

#: Höjs bara om formatet på JSON-filerna ändras på ett icke bakåtkompatibelt
#: sätt. Läskoden tål okända fält, så tillägg kräver ingen höjning.
SCHEMA_VERSION = 1

#: Programmets version. Höjs vid varje leverans.
VERSION = "1.4.9"


# ==========================================================================
# JSON-LAGRING
# ==========================================================================


_IO_LOCK = threading.RLock()


def _diag(msg: str) -> None:
    """Diagmeddelande som ALDRIG kraschar - pythonw (autostart!) har
    ingen konsol, där är sys.stderr None."""
    try:
        if sys.stderr is not None:
            sys.stderr.write(msg)
    except Exception:
        pass


@contextmanager
def _io_lock(timeout: float = 15.0):
    """Lås med tak (ANVÄNDARORDER: förhindra att det låser sig).

    Väntar högst `timeout` sekunder. Slår någon tråd knut på sig är det
    bättre att fortsätta med en liten kapplöpningsrisk (skrivningarna är
    atomiska) än att frysa hela appen.
    """
    got = _IO_LOCK.acquire(timeout=timeout)
    if not got:
        _diag("pdfsorter_data: låst väntan > %gs - fortsätter "
              "utan lås (atomiska skrivningar skyddar)\n" % timeout)
    try:
        yield
    finally:
        if got:
            _IO_LOCK.release()


def _with_retry(fn, tries: int = 3):
    """Transiente I/O-fel (nätverksdisk, antivirus) prövas igen med
    backoff - appen ska varken krascha eller hänga på en tillfällig
    störning."""
    delay = 0.05
    for i in range(tries):
        try:
            return fn()
        except OSError:
            if i == tries - 1:
                raise
            time.sleep(delay)
            delay *= 2


# -- JSON-snabbspår (ANVÄNDARORDER 2026-08-26: snabbhet) -------------------
# orjson är 3-5x snabbare än stdlib json när det finns; annars fallback.
try:
    import orjson as _orjson

    def _json_loads(raw):
        return _orjson.loads(raw)

    def _json_dumps(obj) -> str:
        return _orjson.dumps(
            obj, option=_orjson.OPT_INDENT_2 | _orjson.OPT_NON_STR_KEYS
        ).decode("utf-8")

    def _json_dumps_line(obj) -> str:
        # Kompakt EN-radsversion för journalen (radbaserad parsning).
        return _orjson.dumps(obj, option=_orjson.OPT_NON_STR_KEYS).decode("utf-8")
except Exception:                                   # pragma: no cover
    def _json_loads(raw):
        return json.loads(raw)

    def _json_dumps(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, indent=2)

    def _json_dumps_line(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

#: Cache: config_dir() anropas i princip vid varje filoperation; att
#: göra om beräkningen + mkdir varje gång är onödigt (snabbhet).
#: Nyckel = (PDFSORTER_HOME, appmapp), värde = (sökväg, läge).
_CONFIG_DIR_CACHE: Dict[Tuple[str, str], Tuple[Path, str]] = {}


def _app_dir() -> Path:
    """Mappen där modulerna ligger = appmappen (fungerar överallt)."""
    return Path(__file__).resolve().parent


def _skrivbar(p: Path) -> bool:
    """Kan appen skriva i mappen? (USB/read-only ska falla tillbaka.)"""
    try:
        t = p / ".pdfsorter_write_test"
        t.write_text("ok", encoding="utf-8")
        t.unlink()
        return True
    except OSError:
        return False


def _os_config_dir() -> Path:
    """Gamla OS-platsen - numera bara fallback och migrationskälla."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "ArkivPiloten"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ArkivPiloten"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "pdfsorter"


def config_dir() -> Path:
    """VAR allt rörande appen sparas.

    Ordning:
      1) PDFSORTER_HOME om användaren uttryckligen satt den.
      2) Appmappen när den är skrivbar - portabelt, följer med på USB
         och nätverksdisk (användarorder 2026-10-05/2026-10-16).
      3) Användarens data-mapp när appmappen är skrivskyddad
         (/Applications, /opt, paketerad .app eller en låst USB-sticka).

    Punkt 3 tillkom 2026-10-20 för multi-OS: en app som installeras
    systembrett måste kunna spara regler, loggar och inställningar utan
    att kräva skrivrättighet i programmappen. Så länge appmappen går att
    skriva i ändras ingenting - portabelt beteende är fortfarande
    standard. Gamla OS-platsen läses dessutom som migrationskälla
    (se migrate_to_portable).
    """
    env = os.environ.get("PDFSORTER_HOME", "")
    app = _app_dir()
    nyckel = (env, str(app))
    hit = _CONFIG_DIR_CACHE.get(nyckel)
    if hit is not None:
        return hit[0]
    if env:
        p, läge = Path(env).expanduser(), "override"
    elif _skrivbar(app):
        p, läge = app, "portable"
    else:
        p, läge = _os_config_dir(), "user"
    p.mkdir(parents=True, exist_ok=True)
    _CONFIG_DIR_CACHE[nyckel] = (p, läge)
    return p


def config_dir_mode() -> str:
    """'override' | 'portable' | 'user' - visas i status/diagnostik."""
    config_dir()
    env = os.environ.get("PDFSORTER_HOME", "")
    hit = _CONFIG_DIR_CACHE.get((env, str(_app_dir())))
    return hit[1] if hit else "portable"


_PORTABEL_MIGRERAD = False

#: Alla data-JSON:er samlas i appmappens json/-undermapp
#: (ANVÄNDARORDER 2026-10-06: "allt ska sparas i appmappen, logs, json").
_JSON_DIR_CACHE: Path = None
_JSON_FLYTTAD = False

DATA_FILER = ("settings.json", "rules.json", "history.json",
              "history.journal", "ignored_files.json",
              "learned_model.json", "arkivpiloten.lock", "visa-fonstret")


def json_dir() -> Path:
    """appmappen/json/ - skapas vid behov; flyttar en gång kvarlämnade
    datafiler från appmappens rot (tidigare portabla layouten)."""
    global _JSON_DIR_CACHE, _JSON_FLYTTAD
    if _JSON_DIR_CACHE is None:
        p = config_dir() / "json"
        p.mkdir(parents=True, exist_ok=True)
        _JSON_DIR_CACHE = p
    if not _JSON_FLYTTAD:
        _JSON_FLYTTAD = True
        rot = config_dir()
        for namn in DATA_FILER:
            gammal = rot / namn
            ny = _JSON_DIR_CACHE / namn
            try:
                if gammal.is_file() and not ny.exists():
                    shutil.move(str(gammal), str(ny))
            except OSError:
                continue
    return _JSON_DIR_CACHE


def migrate_to_portable() -> List[str]:
    """Engångskopiera data från gamla OS-platsen till appmappen.

    När appen första gången körs portabelt och gamla configen har data
    (regler, historik ...) kopieras filerna över så att användaren inte
    börjar om från noll. Kopiering, inte flytt - inget kan försvinna.
    """
    global _PORTABEL_MIGRERAD
    if _PORTABEL_MIGRERAD:
        return []
    _PORTABEL_MIGRERAD = True
    ny = config_dir()
    gammal = _os_config_dir()
    if ny == gammal or not gammal.is_dir():
        return []
    kopierade = []
    for namn in DATA_FILER[:6]:
        src_f = gammal / namn
        # gamla OS-layouten hade json i roten; nya layouten i json/
        dst_f = json_dir() / namn
        if not src_f.is_file():
            src_f = gammal / "json" / namn
        try:
            if src_f.is_file() and not dst_f.exists():
                shutil.copy2(src_f, dst_f)
                kopierade.append(namn)
        except OSError:
            continue
    return kopierade


def rules_path() -> Path:
    return json_dir() / "rules.json"


def settings_path() -> Path:
    return json_dir() / "settings.json"


def history_path() -> Path:
    return json_dir() / "history.json"


def lock_path() -> Path:
    return json_dir() / "arkivpiloten.lock"


# ==========================================================================
# ENKELINSTANS - bara en app åt gången får äga reglerna
# ==========================================================================
#
# Utan lås kan två fönster köras samtidigt: autostart öppnar ett, och sedan
# dubbelklickar användaren på ikonen. Båda läser rules.json vid start och
# skriver tillbaka hela filen när något ändras - den som sparar sist vinner,
# och den andres kategorier försvinner utan felmeddelande.
#
# Låset är en fil med PID och starttid. Att bara kolla om filen finns räcker
# inte: efter en krasch ligger den kvar och skulle låsa ute användaren för
# alltid. Därför kontrolleras att processen faktiskt lever.

def _process_lever(pid: int) -> bool:
    """Kör processen med det här PID:et fortfarande?

    Ett återanvänt PID kan ge falskt positivt, men konsekvensen är bara att
    appen ber användaren stänga det andra fönstret - inte dataförlust.
    """
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        try:
            import ctypes
            PROCESS_QUERY_LIMITED = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED, False, pid)
            if not h:
                return False
            kod = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(kod))
            ctypes.windll.kernel32.CloseHandle(h)
            return kod.value == 259          # STILL_ACTIVE
        except Exception:
            return False
    try:
        os.kill(pid, 0)                      # signal 0 = finns processen?
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                          # finns, men ägs av någon annan
    except OSError:
        return False


class InstanceLock:
    """Ser till att bara en ArkivPiloten kör mot samma konfiguration.

    Används som kontexthanterare eller manuellt:

        lås = InstanceLock()
        if not lås.acquire():
            print(f"Kör redan (PID {lås.other_pid})")
        ...
        lås.release()

    Låsfilen tas bort vid avslut. Ligger den kvar efter en krasch upptäcks
    det genom att processen inte längre finns, och låset övertas.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else lock_path()
        self.acquired = False
        #: PID för den instans som redan håller låset, när acquire() nekar
        self.other_pid: int = 0
        self.other_started: str = ""

    def _read(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError,
                UnicodeDecodeError):
            return {}

    def acquire(self) -> bool:
        """Ta låset. False om en annan levande instans redan har det."""
        if self.acquired:
            return True
        gammal = self._read()
        pid = int(gammal.get("pid", 0) or 0)
        if pid and pid != os.getpid() and _process_lever(pid):
            self.other_pid = pid
            self.other_started = str(gammal.get("started", ""))
            return False

        # Ingen levande ägare - skriv vårt eget lås. Två processer kan
        # nå hit samtidigt (autostart + dubbelklick samma sekund); den som
        # skriver sist vinner filen. Därför bekräftas efteråt att det är
        # VÅRT pid som står i låset - annars vann den andra och vi ger oss.
        try:
            _write_json(self.path, {
                "pid": os.getpid(),
                "started": now_iso(),
                "host": _värdnamn(),
            })
        except OSError:
            # Går låset inte att skriva ska appen ändå starta - ett lås som
            # inte kan skapas är ett mindre problem än en app som vägrar gå.
            self.acquired = True
            return True
        vann = self._read()
        vinnar_pid = int(vann.get("pid", 0) or 0)
        if vinnar_pid and vinnar_pid != os.getpid():
            self.other_pid = vinnar_pid
            self.other_started = str(vann.get("started", ""))
            return False
        self.acquired = True
        return True

    def release(self) -> None:
        """Släpp låset, men bara om det fortfarande är vårt."""
        if not self.acquired:
            return
        self.acquired = False
        if self._read().get("pid") == os.getpid():
            try:
                self.path.unlink()
            except OSError:
                pass

    def __enter__(self) -> "InstanceLock":
        self.acquire()
        return self

    def __exit__(self, *_exc) -> None:
        self.release()


def show_request_path() -> Path:
    return json_dir() / "visa-fonstret"


def request_show() -> bool:
    """Be den körande instansen visa sitt fönster.

    Startar användaren appen en andra gång är avsikten nästan alltid att
    komma åt fönstret - inte att köra två kopior. Den nya processen lämnar
    en lapp och avslutar; den som redan kör ser lappen och dyker upp.
    """
    try:
        show_request_path().write_text(now_iso(), encoding="utf-8")
        return True
    except OSError:
        return False


def consume_show_request() -> bool:
    """Sant om någon bett oss visa fönstret. Lappen tas bort direkt."""
    p = show_request_path()
    try:
        if not p.exists():
            return False
        p.unlink()
        return True
    except OSError:
        return False


def _värdnamn() -> str:
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return ""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        def _do():
            with open(path, "r", encoding="utf-8") as fh:
                return _json_loads(fh.read())
        return _with_retry(_do)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        # Trasig fil: SJÄLVLÄKNING - försök först återställa från senaste
        # bra kopian (.bak) innan vi ger upp och börjar tomt. Den trasiga
        # filen sparas undan som .broken-<tid> så att den kan inspekteras.
        bak = path.with_name(path.name + ".bak")
        healed = None
        if bak.exists():
            try:
                with open(bak, "r", encoding="utf-8") as fh:
                    healed = json.load(fh)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                healed = None
        try:
            path.replace(path.with_suffix(path.suffix + f".broken-{int(time.time())}"))
        except OSError:
            pass
        if healed is not None:
            try:
                _write_json(path, healed)      # återställ huvudfilen
            except OSError:
                pass
            return healed
        return default


def _write_json(path: Path, data: Any) -> None:
    """Atomisk skrivning - en krasch mitt i kan aldrig korrupta filen."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(_json_dumps(data))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        tmp = None
        # Självläkning: varje lyckad skrivning speglas till .bak, så att en
        # senare korrupt huvudfil kan återställas i _read_json.
        try:
            shutil.copyfile(path, path.with_name(path.name + ".bak"))
        except OSError:
            pass
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


_BAD_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}


def safe_folder_name(name: str) -> str:
    """Giltigt mappnamn på Windows, macOS och Linux."""
    name = unicodedata.normalize("NFKC", (name or "").strip())
    name = _BAD_FS_CHARS.sub("-", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if name.lower() in _RESERVED:
        name = "_" + name
    return name[:120] or "Osorterat"


DEFAULT_SETTINGS: Dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "input_dir": "",            # kvar för bakåtkompatibilitet
    "input_dirs": [],           # flera bevakade mappar
    "exclude_dirs": [],         # mappar som hoppas över, även inuti inmappar
    "ignore_words": [],         # filer som innehåller ordet hoppas över
    "ignore_filename_globs": [],  # filnamnsmönster som hoppas över
    "output_dir": "",
    "recursive": True,        # ANVÄNDARORDER 2026-09-28: även undermappar
    "subfolders_enabled_v2": False,   # engångsmigrering: se load_settings
    "extensions_offer_hidden": False, # "visa inte igen" i tilläggsdialogen
    "tesseract_path": "",        # manuell sökväg till tesseract.exe
    "learned_matching": True,    # N14: lärande klassificerare (kan stängas av)
    "swish_number": "0721817177",  # Swish-nummer för donations-QR (N15)
    "check_updates": True,       # 2026-10-16: sök Git-uppdatering vid start
    # 2026-10-20: autouppdatering på som standard. Nya versioner hämtas
    # från GitHub Releases, verifieras mot release-postens SHA256SUMS.txt
    # och installeras med backup + rollback. Saknas kontrollsumman frågar
    # appen i stället för att installera tyst.
    "auto_update": True,
    "ui_language": "sv",           # 1.1.0: gränssnittsspråk sv | en
    "tag_pdf_metadata": True,      # 1.1.0: skriv kategori som PDF-metadata
    "orgnr_lookup": False,         # 1.1.0: slå upp okända avsändare via nätet
    "schedule_enabled": False,     # 1.1.0: schemalagd sortering
    "schedule_time": "07:00",      # 1.1.0: klockslag för schemalagd sortering
    "schedule_last_run": "",       # 1.1.0: datum senaste schemalagda körning
    "year_subfolder": True,      # N16: årsmapp från filens datum, automatiskt
    "action": "move",             # move | copy
    "on_conflict": "rename",      # rename | skip | overwrite
    "min_score": 1.0,
    "ambiguity_margin": 0.5,
    # -- strikthet --
    "strictness": "normal",      # los | normal | strikt | mycket_strikt | egen
    "min_keywords": 2,           # ANVÄNDARORDER 2026-08-26: minst 2 ord för auto
    "require_strong": False,     # kräv minst en stark identifierare
    "score_ratio": 1.0,          # bästa poängen delat med tvåans
    "min_text_chars": 0,         # för lite läst text -> fråga hellre
    "require_anchor": False,     # minst ett stödord i brevhuvud/filnamn
    "reject_recipient_only": True,   # neka när alla träffar är mottagarens
    "require_anchor_or_strong": True,  # 2026-10-16: bara löptext flyttar aldrig
    "unmatched_folder": "",       # tom = lämna kvar filen i inmappen
    "ask_when_unsure": True,
    "popup_immediately": False,   # under bevakning: samla i kö i stället
    "ocr_enabled": True,
    "ocr_max_pages": 6,          # 2026-10-15: fler sidor OCR = bättre avläsning
    "ocr_language": "swe+eng",
    "ocr_quality": "high",     # standard | high - se OCR_QUALITY_LEVELS
    "max_pages_text": 0,      # 0 = alla sidor
    "watch_interval": 5.0,
    "stable_seconds": 3.0,
    "keywords_per_file": 15,     # 2026-10-15: fler matchningsord att välja på
    "dry_run": False,
    # -- nytt --
    "theme": "ljus",             # ljus | mork - växlas live i Inställningar
    "autostart": False,          # starta med operativsystemet
    "start_minimized": False,    # göm fönstret direkt, ligg i systemfältet
    "tray_enabled": True,        # visa ikon i systemfältet
    "close_to_tray": True,       # krysset minimerar i stället för att avsluta
    "minimize_to_tray": False,   # minimering göms i systemfältet (annars kvar
                                 # i aktivitetsfältet - krysset styr sitt eget)
    "autowatch_on_start": False, # slå på bevakning direkt vid start
    "notify": True,              # popup-notis när filer sorterats
    "rescan_after_learn": True,  # skanna om allt när ett nytt stödord lärts in
    # -- datum och undermappar --
    "date_enabled": False,       # av tills användaren slår på den
    "date_default_template": "{år}",   # för kategorier utan egen mall
    "date_fallback": "none",     # none | unknown | filedate
    "date_prefer_label": True,   # låt "Fakturadatum:" styra
    # -- rapport --
    "report_days": 10,           # hur många dagar matchningsrapporten täcker
    # -- framskjutet --
    "preview_in_dialog": False,  # PDF-förhandsvisning i granskningsrutan
                                 # (REQ-N7, FRAMSKJUTEN tills beställaren säger till)
    "contrast": "normal",        # normal | high (högkontrast, tema rond 3)
}


def load_settings() -> Dict[str, Any]:
    with _io_lock():
        data = _read_json(settings_path(), {})
    s = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        for k, v in data.items():
            if k in s:
                s[k] = v
    # Engångsmigrering (ANVÄNDARORDER 2026-09-28: "ska även skanna
    # undermapparna i vald mapp"): gamla installationer har recursive=false
    # sparad som standardvärde. Slå på undermappar en gång, och logga-
    # säkert därefter - kryssrutan råder som vanligt efter migreringen.
    # Engångsuppgradering 2026-10-15: bättre avläsning + fler ord
    if not s.get("read_upgrade_2026_10", False):
        if int(s.get("ocr_max_pages", 6) or 0) <= 3:
            s["ocr_max_pages"] = 6
        if int(s.get("keywords_per_file", 10) or 0) <= 10:
            s["keywords_per_file"] = 15
        s["read_upgrade_2026_10"] = True
        try:
            save_settings(s)
        except Exception:
            pass
    if not s.get("subfolders_enabled_v2", False):
        s["recursive"] = True
        s["subfolders_enabled_v2"] = True
        try:
            save_settings(s)
        except Exception:
            pass
    # Äldre versioner hade bara en inmapp - flytta över den
    dirs = [d for d in (s.get("input_dirs") or []) if isinstance(d, str) and d.strip()]
    if not dirs and s.get("input_dir"):
        dirs = [s["input_dir"]]
    seen, unique = set(), []
    for d in dirs:
        key = os.path.normcase(os.path.abspath(d))
        if key not in seen:
            seen.add(key)
            unique.append(d)
    s["input_dirs"] = unique
    s["input_dir"] = unique[0] if unique else ""
    return s


def save_settings(settings: Dict[str, Any]) -> None:
    clean = dict(DEFAULT_SETTINGS)
    clean.update({k: v for k, v in settings.items() if k in DEFAULT_SETTINGS})
    clean["schema_version"] = SCHEMA_VERSION
    with _io_lock():
        _write_json(settings_path(), clean)


class Rules:
    """Alla matchningsregler. Speglar rules.json."""

    def __init__(self, data: Optional[Dict[str, Any]] = None, path: Optional[Path] = None):
        self.path = Path(path) if path else rules_path()
        data = data if isinstance(data, dict) else {}
        self.categories: List[Dict[str, Any]] = []
        #: Inverterat ordindex (ord -> kategorinamn) för O(1)-uppslag i
        # keyword_owners/all_keyword_texts (snabbhet, ANVÄNDARORDER).
        self._index: Optional[Dict[str, List[str]]] = None
        for cat in data.get("categories", []):
            if not isinstance(cat, dict) or not str(cat.get("name", "")).strip():
                continue
            keywords, seen = [], set()
            for kw in cat.get("keywords", []):
                if isinstance(kw, str):
                    kw = {"text": kw}
                if not isinstance(kw, dict):
                    continue
                text = normalize(kw.get("text", ""))
                if not text or text in seen:
                    continue
                seen.add(text)
                post = {
                    "text": text,
                    "weight": float(kw.get("weight", 1.0) or 1.0),
                    "whole_word": bool(kw.get("whole_word", True)),
                    "hits": int(kw.get("hits", 0) or 0),
                    "added": kw.get("added", now_iso()),
                    "source": kw.get("source", "user"),
                }
                # Negativ inlärning: ett stödord som lett fel sparas med
                # antal avvisanden och när det senast hände. Fälten skrivs
                # bara när de används, så gamla rules.json är oförändrade.
                if int(kw.get("rejected", 0) or 0):
                    post["rejected"] = int(kw.get("rejected", 0) or 0)
                    post["rejected_at"] = str(kw.get("rejected_at", "") or "")
                keywords.append(post)
            name = str(cat["name"]).strip()
            self.categories.append({
                "name": name,
                "folder": safe_folder_name(cat.get("folder") or name),
                "keywords": keywords,
                "enabled": bool(cat.get("enabled", True)),
                "subfolder": str(cat.get("subfolder", "") or ""),
                # 0 = använd strikthetsnivåns värde. Sätts den till t.ex. 3
                # krävs tre olika stödord just för den här kategorin.
                "min_keywords": max(0, int(cat.get("min_keywords", 0) or 0)),
                "created": cat.get("created", now_iso()),
                "files_sorted": int(cat.get("files_sorted", 0) or 0),
            })
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        idx: Dict[str, List[str]] = {}
        for cat in self.categories:
            for kw in cat["keywords"]:
                idx.setdefault(kw["text"], []).append(cat["name"])
        self._index = idx

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Rules":
        p = Path(path) if path else rules_path()
        with _io_lock():
            return cls(_read_json(p, {}), p)

    def save(self) -> None:
        self._rebuild_index()   # täcker även externa .categories-tilldelningar
        with _io_lock():
            _write_json(self.path, {
                "schema_version": SCHEMA_VERSION,
                "updated": now_iso(),
                "categories": self.categories,
            })

    # -- uppslag ----------------------------------------------------------
    def names(self) -> List[str]:
        return [c["name"] for c in self.categories]

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        target = normalize(name)
        for cat in self.categories:
            if normalize(cat["name"]) == target:
                return cat
        return None

    def keyword_owners(self, word: str) -> List[str]:
        """Vilka kategorier som redan använder ett visst stödord."""
        target = normalize(word)
        if self._index is not None:
            return list(self._index.get(target, []))
        return [c["name"] for c in self.categories
                if any(kw["text"] == target for kw in c["keywords"])]

    def all_keyword_texts(self) -> Counter:
        if self._index is not None:
            return Counter({w: len(n) for w, n in self._index.items()})
        c: Counter = Counter()
        for cat in self.categories:
            for kw in cat["keywords"]:
                c[kw["text"]] += 1
        return c

    # -- ändra ------------------------------------------------------------
    def ensure_category(self, name: str, folder: Optional[str] = None) -> Dict[str, Any]:
        cat = self.get(name)
        if cat:
            if folder:
                cat["folder"] = safe_folder_name(folder)
            return cat
        cat = {
            "name": name.strip(),
            "folder": safe_folder_name(folder or name),
            "keywords": [],
            "enabled": True,
            "subfolder": "",
            "min_keywords": 0,
            "created": now_iso(),
            "files_sorted": 0,
        }
        self.categories.append(cat)
        self.categories.sort(key=lambda c: normalize(c["name"]))
        self._rebuild_index()
        return cat

    def add_keywords(self, name: str, words: List[str], weight: float = 1.0,
                     whole_word: bool = True, source: str = "user") -> Dict[str, Any]:
        cat = self.ensure_category(name)
        existing = {kw["text"] for kw in cat["keywords"]}
        for word in words:
            text = normalize(word)
            if not text or text in existing:
                continue
            existing.add(text)
            cat["keywords"].append({
                "text": text,
                "weight": float(weight),
                "whole_word": bool(whole_word),
                "hits": 0,
                "added": now_iso(),
                "source": source,
            })
        self._rebuild_index()
        return cat

    def remove_keyword(self, name: str, word: str) -> bool:
        cat = self.get(name)
        if not cat:
            return False
        target = normalize(word)
        before = len(cat["keywords"])
        cat["keywords"] = [kw for kw in cat["keywords"] if kw["text"] != target]
        changed = len(cat["keywords"]) != before
        if changed:
            self._rebuild_index()
        return changed

    def rename_category(self, old: str, new: str) -> bool:
        cat = self.get(old)
        if not cat or not new.strip():
            return False
        nytt = new.strip()
        # Namnkrock: en annan kategori får inte redan heta så. Två
        # kategorier med samma namn skulle göra get() tvetydig och låta
        # båda skriva till samma mapp.
        if any(normalize(c["name"]) == normalize(nytt) and c is not cat
               for c in self.categories):
            return False
        cat["name"] = nytt
        self.categories.sort(key=lambda c: normalize(c["name"]))
        self._rebuild_index()
        return True

    def remove_category(self, name: str) -> bool:
        target = normalize(name)
        before = len(self.categories)
        self.categories = [c for c in self.categories if normalize(c["name"]) != target]
        changed = len(self.categories) != before
        if changed:
            self._rebuild_index()
        return changed

    def register_hit(self, name: str, matched: List[str]) -> None:
        cat = self.get(name)
        if not cat:
            return
        cat["files_sorted"] = int(cat.get("files_sorted", 0)) + 1
        hits = {normalize(w) for w in matched}
        for kw in cat["keywords"]:
            if kw["text"] in hits:
                kw["hits"] = int(kw.get("hits", 0)) + 1

    def register_reject(self, name: str, matched: List[str]) -> None:
        """Ett stödord ledde fel: filen hamnade hos `name` men rättades.

        Räknaren gör att ordet väger mindre nästa gång (se _reject_factor
        i pdfsorter.py). Ett ord som aldrig mer används rätt tystnar helt,
        men en enstaka felsortering sänker det bara mjukt.
        """
        cat = self.get(name)
        if not cat:
            return
        stamp = now_iso()
        hits = {normalize(w) for w in matched}
        for kw in cat["keywords"]:
            if kw["text"] in hits:
                kw["rejected"] = int(kw.get("rejected", 0)) + 1
                kw["rejected_at"] = stamp


MAX_HISTORY = 2000

# -- Append-only-journal (ANVÄNDARORDER: förhindra att det låser sig) ------
# Tidigare skrevs HELA history.json om (med fsync) vid varje flytt - vid
# batchsortering blev det en skrivning per fil och appen hackade. Nu är
# varje händelse en pytteliten journalrad; huvudfilen skrivs om först vid
# kompaktering (varje 25:e händelse eller vid flush). Kraschar appen mitt
# i spelas journalen upp vid nästa load - inget går förlorat.
_HIST_JOURNAL_MAX = 25
_journal_pending: List[Dict[str, Any]] = []   # rader som inte nådde disken
_journal_fh = None                            # buffrad handle (snabbhet)
_journal_lines = 0
_HIST_MEM: Dict[str, Any] = {"sig": None, "events": None}  # mtime-cache


_JOURNAL_FLYTTAD = False


def _journal_path() -> Path:
    """Historikjournalen bor i json/ som alla andra datafiler
    (2026-10-16: inget i appmappens rot). En journal som ligger kvar i
    roten från äldre versioner flyttas hit en gång."""
    global _JOURNAL_FLYTTAD
    ny = json_dir() / "history.journal"
    if not _JOURNAL_FLYTTAD:
        _JOURNAL_FLYTTAD = True
        gammal = config_dir() / "history.journal"
        try:
            if gammal.is_file() and not ny.exists():
                shutil.move(str(gammal), str(ny))
        except OSError:
            pass
    return ny


def _journal_write(line: str) -> None:
    """En öppen handle i stället för open-per-event (snabbhet).

    buffering=1 (radbuffrad): varje rad flushas direkt, så en hårt
    avbruten process (avsluta i Aktivitetshanteraren, strömavbrott)
    förlorar aldrig en redan skriven händelse. Kostnaden är försumbar -
    journalen skrivs högst en gång per sorterad fil.
    """
    global _journal_fh, _journal_lines
    if _journal_fh is None:
        _journal_fh = open(_journal_path(), "a", encoding="utf-8",
                           buffering=1)
    _journal_fh.write(line + "\n")   # line MÅSTE vara en kompakt rad
    _journal_lines += 1


def _journal_flush() -> None:
    global _journal_lines
    if _journal_fh is not None:
        try:
            _journal_fh.flush()
        except OSError:
            pass
    _journal_lines = 0


def _journal_close() -> None:
    global _journal_fh
    if _journal_fh is not None:
        try:
            _journal_fh.close()
        except OSError:
            pass
        _journal_fh = None


def _hist_sig():
    """Signatur för historikens filer: ändras något = cachen ogiltig."""
    def sig(p: Path):
        try:
            st = p.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None
    return (sig(history_path()), sig(_journal_path()))


def _read_journal() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    p = _journal_path()
    if not p.exists():
        return out
    try:
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(_json_loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue   # avhuggen rad (krasch mitt i) - hoppa över
    except OSError:
        pass
    return out


def _compact_history() -> None:
    """Slå ihop journal + huvudfil till en ny history.json (under lås)."""
    global _journal_pending
    _journal_flush()
    _journal_close()          # stäng innan unlink (fil låst på Windows)
    base = _read_json(history_path(), {})
    events = base.get("events", []) if isinstance(base, dict) else []
    events += _read_journal()
    events += _journal_pending
    _journal_pending = []
    try:
        _journal_path().unlink()
    except OSError:
        pass
    _write_json(history_path(), {
        "schema_version": SCHEMA_VERSION,
        "updated": now_iso(),
        "events": events[-MAX_HISTORY:],
    })
    _HIST_MEM["sig"] = None   # cache ogiltig efter omskrivning


def append_history(entry: Dict[str, Any]) -> None:
    """Lägg till en händelse: en buffrad journalrad, ingen helomskrivning."""
    with _io_lock():
        try:
            _journal_write(_json_dumps_line(entry))
        except OSError:
            _journal_pending.append(entry)   # minnet räddar raden
        if _journal_lines + len(_journal_pending) >= _HIST_JOURNAL_MAX:
            _compact_history()


def flush_history() -> None:
    """Skriv allt till history.json (anropas vid avslut/rapport/ångra)."""
    with _io_lock():
        _compact_history()


def load_history() -> List[Dict[str, Any]]:
    """Senaste händelserna; mtime-cachad så att upprepade GUI-refreshar
    inte reparsar filerna (minimal minnes- och CPU-kostnad)."""
    with _io_lock():
        _journal_flush()
        sig = _hist_sig()
        if sig == _HIST_MEM["sig"] and _HIST_MEM["events"] is not None:
            return list(_HIST_MEM["events"])
        data = _read_json(history_path(), {})
        events = list(data.get("events", [])) if isinstance(data, dict) else []
        events += _read_journal()
        events += list(_journal_pending)
        events = events[-MAX_HISTORY:]
        _HIST_MEM["sig"] = sig
        _HIST_MEM["events"] = events
        return list(events)


def compact_history_if_large(limit: int = 200) -> bool:
    """Kompaktera journalen vid start om den vuxit sig stor (snabbare
    start och mindre filer). Anropas en gång per körning."""
    try:
        p = _journal_path()
        if not p.is_file():
            return False
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            antal = sum(1 for _ in fh)
        if antal <= limit:
            return False
        _compact_history()
        return True
    except OSError:
        return False


def replace_history(events: List[Dict[str, Any]]) -> None:
    with _io_lock():
        global _journal_pending
        _journal_pending = []
        _journal_flush()
        _journal_close()
        try:
            _journal_path().unlink()
        except OSError:
            pass
        _write_json(history_path(), {
            "schema_version": SCHEMA_VERSION,
            "updated": now_iso(),
            "events": events[-MAX_HISTORY:],
        })
        _HIST_MEM["sig"] = None




# --------------------------------------------------------------------------
# IGNORERADE FILER - "känn igen just DENNA fil" (ANVÄNDARORDER 2026-09-24)
# --------------------------------------------------------------------------
# Ord- och mönsterreglerna (ignore_words/ignore_filename_globs) är breda.
# Här sparas i stället ENSKILDA filer som användaren markerat i
# granskningsrutan. Känns igen på INNEHÅLLET (sha256 + storlek), så att
# filen ignoreras även om den byter namn eller flyttas - och en annan fil
# med samma namn men annat innehåll påverkas inte.

#: Tak: listan får inte växa obundet. Äldst in markeras först ut.
_IGNORED_MAX = 5000

#: mtime-cache (samma mönster som historiken): ingen omparsning vid
#: varje filkontroll under en bevakningssvep.
_IGNORED_MEM: Dict[str, Any] = {"sig": None, "by_size": {},
                                "hashes": set(), "entries": []}


def ignored_files_path() -> Path:
    return json_dir() / "ignored_files.json"


def _ignored_sig():
    try:
        st = ignored_files_path().stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _ignored_index() -> Dict[str, Any]:
    """Index över markerade filer: storlek -> hashmängd (+ alla hashar)."""
    sig = _ignored_sig()
    if sig is None:
        # Ingen fil: tomt index (cachen nollställs om den funnits förut).
        if _IGNORED_MEM["sig"] is not None:
            _IGNORED_MEM.update(sig=None, by_size={}, hashes=set(), entries=[])
        return _IGNORED_MEM
    if sig == _IGNORED_MEM["sig"] and _IGNORED_MEM["entries"]:
        return _IGNORED_MEM
    data = _read_json(ignored_files_path(), {})
    entries = data.get("files", []) if isinstance(data, dict) else []
    by_size: Dict[int, set] = {}
    hashes = set()
    for e in entries:
        if not isinstance(e, dict):
            continue
        h = str(e.get("hash", "")).casefold()
        if not h:
            continue
        hashes.add(h)
        try:
            by_size.setdefault(int(e.get("size", -1)), set()).add(h)
        except (TypeError, ValueError):
            continue
    _IGNORED_MEM.update(sig=sig, by_size=by_size, hashes=hashes,
                        entries=[e for e in entries if isinstance(e, dict)])
    return _IGNORED_MEM


def is_ignored_file(path: Path) -> bool:
    """Känns den här filen igen som individuellt ignorerad?

    Snabb väg: filstorleken jämförs mot de markerade filernas storlekar
    (en dict-träff, ingen I/O utöver stat). Hashen beräknas BARA när
    storleken matchar - annars skulle varje bevakad fil hashas, vilket
    skulle kosta mer än hela matchningen.
    """
    try:
        idx = _ignored_index()
        if not idx["hashes"]:
            return False
        storlek = path.stat().st_size
        kandidater = idx["by_size"].get(storlek)
        if not kandidater:
            return False
        return sha256_file(path).casefold() in kandidater
    except OSError:
        return False


def mark_ignored_file(path: Path, reason: str = "user") -> Optional[Dict[str, Any]]:
    """Markera filen som ignorerad. Returnerar posten, eller None om
    filen inte kan läsas / redan är markerad."""
    try:
        st = path.stat()
        h = sha256_file(path).casefold()
    except OSError:
        return None
    post = {"hash": h, "name": path.name, "size": st.st_size,
            "added": now_iso(), "reason": reason}
    with _io_lock():
        data = _read_json(ignored_files_path(), {})
        filer = data.get("files", []) if isinstance(data, dict) else []
        if any(isinstance(f, dict) and f.get("hash") == h for f in filer):
            return None
        filer.append(post)
        if len(filer) > _IGNORED_MAX:
            filer = filer[-_IGNORED_MAX:]
        _write_json(ignored_files_path(),
                    {"schema_version": SCHEMA_VERSION, "updated": now_iso(),
                     "files": filer})
    _IGNORED_MEM["sig"] = None      # cachen förnyas vid nästa kontroll
    return post


def unignore_file(hash_value: str) -> bool:
    """Ta bort en markering så att filen sorteras igen."""
    h = (hash_value or "").casefold()
    if not h:
        return False
    with _io_lock():
        data = _read_json(ignored_files_path(), {})
        filer = [f for f in (data.get("files", []) if isinstance(data, dict) else [])
                 if isinstance(f, dict)]
        kvar = [f for f in filer if f.get("hash") != h]
        if len(kvar) == len(filer):
            return False
        _write_json(ignored_files_path(),
                    {"schema_version": SCHEMA_VERSION, "updated": now_iso(),
                     "files": kvar})
    _IGNORED_MEM["sig"] = None
    return True


def list_ignored_files() -> List[Dict[str, Any]]:
    """Alla markerade filer (nyaste sist), för GUI-listan."""
    return list(_ignored_index()["entries"])

# ==========================================================================
# MATCHNINGSRAPPORT - svara på "hur gick det?" med en Markdown-fil
# ==========================================================================
#
# Historiken är det enda bestående underlaget för att förstå hur bra (eller
# dåligt) sorteringen fungerat över tid. Den här funktionen läser historiken,
# slår ihop den med reglerna och skriver ut en lättläst rapport. Den är
# tänkt att exporteras med jämna mellanrum (t.ex. var tionde dag) och visas
# upp, så att svaga stödord, krångliga kategorier och tvetydiga fall går att
# fånga - i stället för att bara gissa sig till vad som är fel.


def _event_time(event: Dict[str, Any]) -> Optional[datetime]:
    """Parsa en händelses tidsstämpel. Returnerar None vid trasigt värde.

    Naiva tidsstämplar (utan tidszon) tolkas som lokal tid, så att de går
    att jämföra med cutoff som är zonmedveten - annars skulle rapporten
    kunna krascha på gammal historik (REQ-I2: transienta fel ska inte
    sänka appen).
    """
    raw = event.get("time") or ""
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()          # naiv -> anta lokal tid
    return dt


def report_path() -> Path:
    """Sökväg till rapporten - skapas med dagens datum som filnamn."""
    today = datetime.now().strftime("%Y-%m-%d")
    return json_dir() / f"arkivpiloten-rapport-{today}.md"


def build_matching_report(days: int = 10) -> str:
    """Bygg en Markdown-rapport över matchningen de senaste `days` dagarna.

    Rapporten sammanfattar det man behöver veta för att förbättra
    sorteringen: hur mycket som gick automatiskt, vad du fick svara på,
    vilka stödord som aldrig träffade, kategorier som krockar och fall där
    två kandidater låg nära varandra.
    """
    from datetime import timedelta
    from collections import Counter, defaultdict

    now = datetime.now().astimezone()
    cutoff = now - timedelta(days=days)
    events = load_history()
    recent = [e for e in events
              if isinstance(e, dict)
              and (t := _event_time(e)) is not None and t >= cutoff]

    total = len(recent)
    by = Counter(e.get("decided_by", "") for e in recent)
    ocr_count = sum(1 for e in recent if e.get("used_ocr"))
    with_date = sum(1 for e in recent if e.get("date"))
    no_source = sum(1 for e in recent if not e.get("date_source"))

    # -- per kategori: antal, auto/manuell, snittpoäng, närhet --
    cat_stat: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "auto": 0, "user": 0, "unmatched": 0,
                 "scores": [], "close": 0})
    runner_up_cat = Counter()
    for e in recent:
        c = e.get("category") or "(okänd)"
        st = cat_stat[c]
        st["n"] += 1
        try:
            sc = float(e.get("score", 0) or 0)
        except (TypeError, ValueError):
            sc = 0.0
        st["scores"].append(sc)
        d = e.get("decided_by")
        if d == "auto":
            st["auto"] += 1
        elif d == "user":
            st["user"] += 1
        elif d == "unmatched":
            st["unmatched"] += 1
        ru = e.get("runner_up")
        if isinstance(ru, dict) and ru.get("category"):
            runner_up_cat[ru["category"]] += 1
            try:
                margin = sc - float(ru.get("score", 0) or 0)
            except (TypeError, ValueError):
                margin = 0.0
            if margin < 1.0:
                st["close"] += 1

    # -- regler / stödord --
    rules = Rules.load()
    top_kw = []          # (träffar, stödord, kategori)
    unused_kw = []       # (kategori, stödord) som aldrig träffat
    seen_multi: Dict[str, List[str]] = {}
    cats_kw = []
    for cat in rules.categories:
        used = sum(1 for k in cat["keywords"] if k.get("hits", 0))
        cats_kw.append((cat["name"], len(cat["keywords"]), used,
                        cat.get("files_sorted", 0)))
        for k in cat["keywords"]:
            top_kw.append((int(k.get("hits", 0)), k["text"], cat["name"]))
            if not k.get("hits", 0):
                unused_kw.append((cat["name"], k["text"]))
            owners = rules.keyword_owners(k["text"])
            if len(owners) > 1:
                seen_multi[k["text"]] = owners
    top_kw.sort(reverse=True)
    multi_owner = sorted(seen_multi.items())

    # -- hjälpfunktioner för snygga procentsatser --
    def pct(n: int) -> str:
        return f"{n / total * 100:.0f}%" if total else "0%"

    # -- sidhuvud --
    lines = []
    lines.append("# ArkivPiloten — Matchningsrapport")
    lines.append("")
    lines.append(f"**Period:** {cutoff:%Y-%m-%d} – {now:%Y-%m-%d}  ({days} dagar)")
    lines.append(f"**Skapad:** {now:%Y-%m-%d %H:%M}")
    lines.append(f"**Strikthetsnivå:** {load_settings().get('strictness', 'normal')}")
    lines.append("")

    lines.append("## 1. Sammanfattning")
    lines.append("")
    lines.append(f"- **Filer sorterade:** {total}")
    if total:
        lines.append(f"- Automatiskt: {by.get('auto', 0)}  ({pct(by.get('auto', 0))})")
        lines.append(f"- Ditt val (ask → svara): {by.get('user', 0)}  ({pct(by.get('user', 0))})")
        lines.append(f"- Flyttade till _Osorterat: {by.get('unmatched', 0)}  ({pct(by.get('unmatched', 0))})")
        lines.append(f"- Omskanning (rescan): {by.get('rescan', 0)}  ({pct(by.get('rescan', 0))})")
        lines.append(f"- Med OCR: {ocr_count}  ({pct(ocr_count)})")
        lines.append(f"- Med dokumentdatum: {with_date}  ({pct(with_date)})")
    else:
        lines.append("  *Inga händelser i perioden.*")
    lines.append("")

    # -- per kategori --
    lines.append("## 2. Per kategori")
    lines.append("")
    lines.append("| Kategori | Filer | Auto | Ditt val | _Osorterat | Snitt poäng |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for c, st in sorted(cat_stat.items(), key=lambda kv: -kv[1]["n"]):
        avg = (sum(st["scores"]) / len(st["scores"])) if st["scores"] else 0.0
        lines.append(f"| {c} | {st['n']} | {st['auto']} | {st['user']} | "
                     f"{st['unmatched']} | {avg:.2f} |")
    lines.append("")

    # -- tvetydighet --
    close_total = sum(st["close"] for st in cat_stat.values())
    lines.append("## 3. Tvetydighet (fall där tvåan låg nära)")
    lines.append("")
    lines.append(f"- Antal filer där bästa och tvåa låg **inom 1,0 poäng**: "
                 f"{close_total}  ({pct(close_total)})")
    if runner_up_cat:
        lines.append("- Kategorier som ofta var **tvåa** (risk att de blandas ihop "
                     "med något annat):")
        for c, n in runner_up_cat.most_common(8):
            lines.append(f"  - {c}: {n} gånger")
    else:
        lines.append("- Inga fall där tvåan var nära.")
    lines.append("")

    # -- stödord --
    lines.append("## 4. Stödord — vad som funkar och vad som är dött")
    lines.append("")
    lines.append("### Stödord med flest träffar (starka)")
    lines.append("")
    lines.append("| Stödord | Träffar | Kategori |")
    lines.append("|---|---:|---|")
    for hits, kw, cat_name in top_kw[:10]:
        if hits:
            lines.append(f"| {kw} | {hits} | {cat_name} |")
    lines.append("")
    if unused_kw:
        lines.append(f"### Stödord som aldrig träffat ({len(unused_kw)})")
        lines.append("")
        lines.append("  Dessa kan rensas under Matchningar — de särskiljer inte.")
        lines.append("")
        lines.append("| Kategori | Stödord |")
        lines.append("|---|---|")
        for cat_name, kw in unused_kw:
            lines.append(f"| {cat_name} | {kw} |")
        lines.append("")
    else:
        lines.append("### Stödord som aldrig träffat")
        lines.append("")
        lines.append("  Inga - allt har använts minst en gång.")
        lines.append("")

    # -- namnkrock --
    lines.append("## 5. Namnkrockar (ett ord i flera kategorier)")
    lines.append("")
    if multi_owner:
        lines.append("| Stödord | Används i |")
        lines.append("|---|---|")
        for kw, owners in multi_owner:
            lines.append(f"| {kw} | {', '.join(owners)} |")
    else:
        lines.append("  Inga krockar - varje stödord tillhör bara en kategori.")
    lines.append("")

    # -- kategoriernas omfång --
    lines.append("## 6. Kategorier: antal stödord och använda")
    lines.append("")
    lines.append("| Kategori | Stödord | Använda | Filer |")
    lines.append("|---|---:|---:|---:|")
    for cat_name, n_kw, used, files in cats_kw:
        lines.append(f"| {cat_name} | {n_kw} | {used} | {files} |")
    lines.append("")

    # -- råd --
    lines.append("## 7. Vad jag (ArkivPiloten) vill att du tittar på")
    lines.append("")
    advise = []
    if by.get("user", 0):
        advise.append(f"- Du fick svara på {by.get('user', 0)} filer - det är "
                      "kandidater där appen var osäker. Stödord som varit med "
                      "i många av dem är värda att renodla.")
    if unused_kw:
        advise.append(f"- {len(unused_kw)} stödord har aldrig gett en träff. "
                      "Rensa dem - de kan krocka med andra kategorier.")
    if multi_owner:
        advise.append(f"- {len(multi_owner)} stödord används av flera kategorier, "
                      "vilket gör dem svåra att skilja åt.")
    if close_total:
        advise.append(f"- {close_total} filer hade två kandidater nära varandra. "
                      "Öka striktheten eller förstärk stödorden i de kategorierna.")
    if no_source:
        advise.append(f"- {no_source} filer saknade dokumentdatum - överväg "
                      "\"använd filens tid\" som fallback.")
    if not advise:
        advise.append("- Allt ser hälsosamt ut. Bra omdöme.")
    for a in advise:
        lines.append(a)
    lines.append("")

    return "\n".join(lines)




#: Mallar för undermapp under kategorin. Nyckeln sparas i rules.json.
SUBFOLDER_TEMPLATES: List[Tuple[str, str]] = [
    ("", "Ingen undermapp"),
    ("{år}", "År:  Pilkington/2025/"),
    ("{år}/{månad}", "År och månad:  Pilkington/2025/03/"),
    ("{år}-{månad}", "År-månad:  Pilkington/2025-03/"),
    ("{år}/{månadsnamn}", "År och månadsnamn:  Pilkington/2025/03 mars/"),
    ("{kvartal}", "Kvartal:  Pilkington/2025-K1/"),
]

_MONTH_NAMES_SV = ("", "januari", "februari", "mars", "april", "maj", "juni",
                   "juli", "augusti", "september", "oktober", "november",
                   "december")


def render_subfolder(template: str, when: Optional[date]) -> str:
    """Fyll i en undermappsmall med ett datum.

    Returnerar en relativ sökväg som "2025/03", eller tom sträng om
    mallen är tom eller datum saknas. Varje nivå saneras för sig, så en
    mall aldrig kan skapa "../" eller andra otillåtna tecken.
    """
    if not template or when is None:
        return ""
    # Månad tvåsiffrigt, annars sorteras 10 före 2 i filhanteraren.
    ersatt = (template
              .replace("{år}", f"{when.year:04d}")
              .replace("{ar}", f"{when.year:04d}")
              .replace("{månad}", f"{when.month:02d}")
              .replace("{manad}", f"{when.month:02d}")
              .replace("{månadsnamn}", f"{when.month:02d} {_MONTH_NAMES_SV[when.month]}")
              .replace("{manadsnamn}", f"{when.month:02d} {_MONTH_NAMES_SV[when.month]}")
              .replace("{kvartal}", f"{when.year:04d}-K{(when.month - 1) // 3 + 1}")
              .replace("{dag}", f"{when.day:02d}"))
    delar = [safe_folder_name(d) for d in ersatt.split("/") if d.strip()]
    return "/".join(d for d in delar if d)



def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """Innehållshash (REQ-N4) - läst i stora block så att även filer på
    flera MB hashas snabbt. Används för att upptäcka dubbletter som har
    olika namn men samma innehåll."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def unique_target(target: Path) -> Path:
    """faktura.pdf -> faktura (2).pdf om namnet är upptaget."""
    if not target.exists():
        return target
    stem, suffix, parent = target.stem, target.suffix, target.parent
    for i in range(2, 10000):
        cand = parent / f"{stem} ({i}){suffix}"
        if not cand.exists():
            return cand
    return parent / f"{stem} ({int(time.time())}){suffix}"


def place_file(src: Path, out_root: Path, folder: str, action: str = "move",
               on_conflict: str = "rename", dry_run: bool = False,
               subfolder: str = "") -> Tuple[bool, str, Optional[Path]]:
    """Flytta/kopiera filen till out_root/folder[/subfolder]/.

    Skapar mappen vid behov, hur många nivåer den än har.
    Returnerar (lyckades, meddelande, målsökväg).
    """
    src = Path(src)
    dest_dir = Path(out_root) / safe_folder_name(folder)
    if subfolder:
        for nivå in subfolder.split("/"):
            if nivå.strip():
                dest_dir = dest_dir / safe_folder_name(nivå)
    target = dest_dir / src.name

    if target.exists():
        if on_conflict == "skip":
            return False, "Finns redan i målmappen - hoppade över", None
        if on_conflict == "rename":
            target = unique_target(target)

    if dry_run:
        return True, f"[TEST] skulle {action} -> {target}", target

    # Platskontroll (2026-10-15): full disk ska ge ett tydligt fel i
    # stället för en halvskriven fil mitt i flytten.
    try:
        fri = shutil.disk_usage(str(dest_dir.parent if not dest_dir.exists()
                                  else dest_dir)).free
        storlek = src.stat().st_size if action == "copy" else 0
        if storlek and fri < storlek + 50 * 1024 * 1024:
            return False, (f" För lite plats på måldisken "
                           f"({fri // (1024 * 1024)} MB fri, filen är "
                           f"{storlek // (1024 * 1024)} MB)"), None
    except OSError:
        pass

    def _gor():
        dest_dir.mkdir(parents=True, exist_ok=True)
        if action == "copy":
            shutil.copy2(str(src), str(target))
        else:
            # shutil.move klarar flytt mellan diskar (kopiera+radera)
            shutil.move(str(src), str(target))

    try:
        _gor()
        return True, str(target), target
    except PermissionError:
        # Ett enstaka retry: antivirus/låst fil släpper ofta inom en sekund
        time.sleep(1.0)
        try:
            _gor()
            return True, str(target), target
        except PermissionError:
            return False, "Filen är låst av ett annat program", None
        except OSError as exc:
            return False, f"Kunde inte flytta: {exc}", None
    except OSError as exc:
        return False, f"Kunde inte flytta: {exc}", None



# ==========================================================================
# SJÄLVTEST
# ==========================================================================

def _check() -> int:
    """Kontrollerar modulen mot en tillfällig katalog. Rör inga riktiga data."""
    fel = 0

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PDFSORTER_HOME"] = tmp
        rot = Path(tmp)

        # -- inga dubbla definitioner --
        # Modulen växte fram genom att kod flyttades hit från huvudfilen,
        # och då är det lätt att samma konstant följer med två gånger. En
        # dubblett är harmlös tills någon ändrar den ena kopian.
        import ast
        träd = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        namn: Dict[str, int] = {}
        for nod in träd.body:
            if isinstance(nod, (ast.FunctionDef, ast.ClassDef)):
                namn[nod.name] = namn.get(nod.name, 0) + 1
            elif isinstance(nod, ast.AnnAssign) and isinstance(nod.target, ast.Name):
                namn[nod.target.id] = namn.get(nod.target.id, 0) + 1
            elif isinstance(nod, ast.Assign):
                for m in nod.targets:
                    if isinstance(m, ast.Name):
                        namn[m.id] = namn.get(m.id, 0) + 1
        for n, antal in sorted(namn.items()):
            if antal > 1:
                print(f"  FEL {n} definieras {antal} ganger")
                fel += 1

        # -- mappnamn --
        prov = [("Pilkington", "Pilkington"), ("A/B:C", "A-B-C"),
                ("CON", "_CON"), ("  x  ", "x"), ("", "Osorterat"),
                # inledande punkter strippas - "../" kan aldrig bli kvar
                ("../etc", "-etc")]
        for indata, vantat in prov:
            fick = safe_folder_name(indata)
            if fick != vantat:
                print(f"  FEL safe_folder_name({indata!r}) -> {fick!r}, "
                      f"vantat {vantat!r}")
                fel += 1

        # -- regler tur och retur --
        r = Rules(path=rot / "r.json")
        r.add_keywords("Pilkington", ["pilkington", "556033-9086"], weight=2.0)
        r.save()
        igen = Rules.load(rot / "r.json")
        if igen.names() != ["Pilkington"]:
            print(f"  FEL kategorier efter omlasning: {igen.names()}")
            fel += 1
        if len(igen.get("Pilkington")["keywords"]) != 2:
            print("  FEL stodorden overlevde inte sparningen")
            fel += 1

        # -- namnbyte far inte krocka med en annan kategori --
        r.add_keywords("Nordfrakt", ["nordfrakt"])
        if r.rename_category("Nordfrakt", "Pilkington"):
            print("  FEL namnbyte till befintligt kategorinamn tillats")
            fel += 1
        if not r.rename_category("Nordfrakt", "Nordfrakt AB"):
            print("  FEL vanligt namnbyte misslyckades")
            fel += 1

        # -- atomisk skrivning tal trasig fil --
        (rot / "trasig.json").write_text("{ inte json", encoding="utf-8")
        tom = _read_json(rot / "trasig.json", {"ok": True})
        if tom != {"ok": True}:
            print("  FEL trasig JSON gav inte reservvardet")
            fel += 1

        # -- undermappsmallar --
        d = date(2025, 3, 14)
        mallar = [("{år}", "2025"), ("{år}/{månad}", "2025/03"),
                  ("{kvartal}", "2025-K1"), ("", "")]
        for mall, vantat in mallar:
            fick = render_subfolder(mall, d)
            if fick != vantat:
                print(f"  FEL render_subfolder({mall!r}) -> {fick!r}")
                fel += 1
        if render_subfolder("{år}", None) != "":
            print("  FEL utan datum ska ge tom strang")
            fel += 1

        # -- filflytt med undermapp --
        (rot / "in").mkdir()
        (rot / "in" / "a.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
        ok, msg, mal = place_file(rot / "in" / "a.pdf", rot / "ut",
                                  "Pilkington", subfolder="2025")
        if not ok or not (rot / "ut" / "Pilkington" / "2025" / "a.pdf").exists():
            print(f"  FEL place_file med undermapp: {msg}")
            fel += 1

        # -- namnkrock --
        (rot / "in" / "a.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
        ok, msg, mal2 = place_file(rot / "in" / "a.pdf", rot / "ut",
                                   "Pilkington", subfolder="2025")
        if not ok or mal2 is None or mal2.name != "a (2).pdf":
            print(f"  FEL namnkrock gav {mal2.name if mal2 else msg}")
            fel += 1

        # -- torrkorning flyttar ingenting men ger malsokvag (REQ-D2) --
        (rot / "in" / "b.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
        ok, msg, mal_torr = place_file(rot / "in" / "b.pdf", rot / "ut",
                                       "Nordfrakt", dry_run=True)
        if not ok or mal_torr is None or mal_torr.exists():
            print(f"  FEL torrkorning: {msg}")
            fel += 1

        # -- enkelinstanslås --
        lås1 = InstanceLock(rot / "test.lock")
        if not lås1.acquire():
            print("  FEL forsta acquire nekades")
            fel += 1
        if not lås1.acquire():
            print("  FEL samma process ska fa laset igen")
            fel += 1

        # en levande process ska blockera
        import subprocess
        p_annan = subprocess.Popen([sys.executable, "-c",
                                    "import time; time.sleep(20)"])
        try:
            _write_json(rot / "test.lock", {"pid": p_annan.pid,
                                            "started": "", "host": ""})
            lås2 = InstanceLock(rot / "test.lock")
            if lås2.acquire():
                print("  FEL laset togs trots levande agare")
                fel += 1
            if lås2.other_pid != p_annan.pid:
                print(f"  FEL other_pid {lås2.other_pid}")
                fel += 1
        finally:
            p_annan.terminate()
            p_annan.wait()

        # död process = övergivet lås, ska kunna övertas
        _write_json(rot / "test.lock", {"pid": p_annan.pid,
                                        "started": "", "host": ""})
        lås3 = InstanceLock(rot / "test.lock")
        if not lås3.acquire():
            print("  FEL overgivet las overtogs inte")
            fel += 1
        lås3.release()
        if (rot / "test.lock").exists():
            print("  FEL lasfilen togs inte bort vid release")
            fel += 1

        # trasig låsfil ska inte hindra start
        (rot / "test.lock").write_text("{ trasig", encoding="utf-8")
        lås4 = InstanceLock(rot / "test.lock")
        if not lås4.acquire():
            print("  FEL trasig lasfil blockerade start")
            fel += 1
        lås4.release()

        # -- signalen "visa fönstret" --
        if consume_show_request():
            print("  FEL lapp fanns utan att nagon lamnat den")
            fel += 1
        request_show()
        if not consume_show_request():
            print("  FEL lappen hittades inte")
            fel += 1
        if consume_show_request():
            print("  FEL lappen konsumerades inte")
            fel += 1

        # -- kategorifält överlever spara/läsa --
        r2 = Rules(path=rot / "r2.json")
        cat = r2.ensure_category("Nordfrakt")
        cat["subfolder"] = "{år}"
        cat["min_keywords"] = 3
        r2.save()
        igen2 = Rules.load(rot / "r2.json").get("Nordfrakt")
        if igen2.get("subfolder") != "{år}":
            print(f"  FEL subfolder forsvann: {igen2.get('subfolder')!r}")
            fel += 1
        if igen2.get("min_keywords") != 3:
            print(f"  FEL min_keywords forsvann: {igen2.get('min_keywords')!r}")
            fel += 1

        # -- matchningsrapport (REQ-F6b) --
        # tom historik ska ge giltig Markdown utan krasch (AC-6b.6)
        if not str(report_path()).endswith(".md"):
            print(f"  FEL report_path gav inte .md: {report_path()}")
            fel += 1
        md = build_matching_report(10)
        if not md.startswith("# ArkivPiloten"):
            print("  FEL rapport med tom historik saknar rubrik")
            fel += 1
        # med en handelse ska kategorin raknas in i rapporten
        append_history({
            "time": now_iso(), "action": "move", "source": "in/a.pdf",
            "target": "ut/Pilkington/2025/a.pdf", "category": "Pilkington",
            "score": 3.2, "runner_up": {"category": "Nordfrakt", "score": 1.0},
            "matched": ["pilkington"], "used_ocr": False,
            "decided_by": "auto", "learned": False,
            "date": "2025-03-14", "date_source": "label", "subfolder": "2025",
        })
        md2 = build_matching_report(10)
        if "| Pilkington | 1 |" not in md2:
            print("  FEL rapporten tog inte med den sorterade filen")
            fel += 1
        # naiv tidsstämpel (utan zon) i historiken ska inte krascha
        append_history({"time": "2026-08-26T09:00:00",
                        "category": "Pilkington", "decided_by": "user",
                        "score": 1.0, "runner_up": "trasig-icke-dict"})
        md3 = build_matching_report(10)
        if not md3.startswith("# ArkivPiloten"):
            print("  FEL rapport kraschade pa naiv/trasig historik")
            fel += 1

        # -- installningar tur och retur --
        s = load_settings()
        s["input_dirs"] = [str(rot / "in"), str(rot / "in")]  # dubblett
        s["strictness"] = "strikt"
        save_settings(s)
        s2 = load_settings()
        if len(s2["input_dirs"]) != 1:
            print(f"  FEL dubbletter av inmappar togs inte bort: {s2['input_dirs']}")
            fel += 1
        if s2.get("strictness") != "strikt":
            print("  FEL strictness overlevde inte sparningen")
            fel += 1
        if "report_days" not in s2:
            print("  FEL report_days saknas i installningarna")
            fel += 1

    print("pdfsorter_data.py: allt ok" if not fel
          else f"pdfsorter_data.py: {fel} fel")
    return 1 if fel else 0


def main() -> int:
    if "--var" in sys.argv:
        print(f"Instaellningar: {config_dir()}")
        for namn, sokvag in (("regler", rules_path()),
                             ("installningar", settings_path()),
                             ("historik", history_path())):
            finns = "finns" if sokvag.exists() else "saknas"
            print(f"  {namn:<15}{sokvag}  ({finns})")
        return 0
    return _check()


if __name__ == "__main__":
    raise SystemExit(main())
