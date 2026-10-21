#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdfsorter_read.py — läsa och tolka PDF-filer.
=============================================

Hjälpmodul till pdfsorter.py. Här ligger allt som handlar om att få ut
meningsfull information ur en PDF:

    * Textextraktion via PyMuPDF, pypdf eller pdfminer
    * OCR för inskannade sidor, och för logotyper i annars textbaserade filer
    * Sidhuvud, sidfot, anteckningar och formulärfält
    * Kandidatord — de tio förslagen i granskningsrutan
    * Rankning som skiljer avsändare från mottagare
    * Luhn-kontroll av organisationsnummer

Modulen känner inte till kategorier, mappar eller sortering. Den tar en
fil och returnerar text och ordförslag. Därför kan den provas för sig:

    python pdfsorter_read.py --check
    python pdfsorter_read.py faktura.pdf
    python pdfsorter_read.py faktura.pdf --text
    python pdfsorter_read.py *.pdf --json

Saknas filen kan pdfsorter.py inte läsa PDF alls, och säger till om det.

ÄNDRINGAR rond 7 (2026-09-17, avläsningsrunda):
    * Buggfix: _run_ocr kunde returnera "" i stället för (text, conf),
      vilket kraschade uppackningen i extract().
    * Buggfix: pdfminer-vägen påstod max_pages lästa sidor och total 0;
      nu räknas sidorna riktigt och samma skyddstak gäller som för de
      andra motorerna (även pypdf-vägen fick taket).
    * Buggfix/minne: ocr_header_logo och ocr_embedded_images läckte
      PIL-bilder (originalet resp. den förbehandlade kopian stängdes
      aldrig). Båda stängs nu.
    * Hängningsskydd: ocr_header_logo gick utan timeout - nu via
      _tess_call (60 s) som alla andra OCR-anrop.
    * Snabbhet: embedded_images öppnade dokumentet två gånger - nu ett.
      Skevhetsrättning slopad för logotyper/stämplar (de ligger raka).
    * Minne: skyddstak _OCR_MAX_WIDTH för extremt breda sidor.
    * Kod: språkvalet samlat i _resolve_langs (tre kopior -> en).
"""

from __future__ import annotations

import concurrent.futures
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: Programmets version. Höjs vid varje leverans.
VERSION = "1.4.10"

__all__ = [
    # extraktion
    "Extraction", "extract", "backend_status", "status_text", "ocr_available",
    "reading_health",
    "header_images", "ocr_header_logo", "embedded_images",
    "ocr_embedded_images",
    "MIN_TEXT_CHARS", "HARD_PAGE_CAP",
    # stödord
    "Candidate", "suggest_keywords", "guess_category_name",
    "KIND_INFO", "STOPWORDS",
    # OCR-kvalitet
    "OCR_QUALITY_LEVELS", "denoise_numbers",
    # datum - för sortering i årsmappar
    "find_document_date",
    # delar som matchningsmotorn behöver
    "normalize", "_luhn_ok", "_recipient_zone", "_head_of",
    "_DOC_TYPE_WORDS", "_ID_HINT", "_RECIPIENT_MARKERS", "_looks_like_code",
]


def normalize(text: str) -> str:
    """Gemener + Unicode NFKC + hopslagna blanksteg.

    Definieras här och inte i huvudfilen, eftersom hela den här modulen
    bygger på den. pdfsorter.py importerar samma funktion härifrån, så det
    finns bara en variant.
    """
    text = unicodedata.normalize("NFKC", text or "").casefold()
    return re.sub(r"[\s\u00a0]+", " ", text).strip()


MIN_TEXT_CHARS = 120   # under detta antas PDF:en vara en skannad bild


def _have(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


def has_pymupdf() -> bool:
    return _have("pymupdf") or _have("fitz")


def _open_pymupdf():
    try:
        import pymupdf
        return pymupdf
    except Exception:
        import fitz
        return fitz


def has_pypdf() -> bool:
    return _have("pypdf")


def has_pdfminer() -> bool:
    try:
        from pdfminer.high_level import extract_text  # noqa: F401
        return True
    except Exception:
        return False


def has_pytesseract() -> bool:
    return _have("pytesseract") and _have("PIL")


#: Användarvald sökväg (Inställningar / tilläggsdialogen) - kontrolleras
#: FÖRST, så att en manuell installation på udda ställe alltid hittas.
_TESSERACT_OVERRIDE: Optional[str] = None


def set_tesseract_path(path: str) -> None:
    """Peka ut tesseract.exe manuellt. Tom sträng eller obefintlig fil
    rensar valet - appen faller tillbaka på standardsökningen."""
    global _TESSERACT_OVERRIDE
    p = str(path or "").strip()
    if p and Path(p).is_file():
        _TESSERACT_OVERRIDE = p
    else:
        _TESSERACT_OVERRIDE = None


def tesseract_binary() -> Optional[str]:
    if _TESSERACT_OVERRIDE and Path(_TESSERACT_OVERRIDE).is_file():
        return _TESSERACT_OVERRIDE
    exe = shutil.which("tesseract")
    if exe:
        return exe
    if sys.platform.startswith("win"):
        # Även användarnivå-installation (LOCALAPPDATA) - dit hamnar den
        # när installationen körs utan admin.
        import os as _os
        cand_extra = []
        local = _os.environ.get("LOCALAPPDATA")
        if local:
            cand_extra.append(
                Path(local) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
        for cand in [r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                     r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
                     ] + cand_extra:
            if Path(cand).exists():
                return str(cand)
    elif sys.platform == "darwin":
        for cand in ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"):
            if Path(cand).exists():
                return cand
    return None


def ocr_available() -> bool:
    if not has_pytesseract() or tesseract_binary() is None:
        return False
    return has_pymupdf() or shutil.which("pdftoppm") is not None


def backend_status() -> Dict[str, bool]:
    return {
        "pymupdf": has_pymupdf(),
        "pypdf": has_pypdf(),
        "pdfminer": has_pdfminer(),
        "pytesseract": has_pytesseract(),
        "tesseract": tesseract_binary() is not None,
        "pdftoppm": shutil.which("pdftoppm") is not None,
        "ocr_ready": ocr_available(),
    }


def status_text() -> str:
    st = backend_status()
    if st["pymupdf"]:
        engine = "PyMuPDF"
    elif st["pypdf"]:
        engine = "pypdf"
    elif st["pdfminer"]:
        engine = "pdfminer"
    else:
        engine = "SAKNAS - kör: pip install pymupdf pypdf"
    if st["ocr_ready"]:
        ocr = "klar"
    elif not st["tesseract"]:
        ocr = "ej tillgänglig (Tesseract saknas)"
    elif not st["pytesseract"]:
        ocr = "ej tillgänglig (pip install pytesseract pillow)"
    else:
        ocr = "ej tillgänglig"
    return f"PDF-motor: {engine}  |  OCR: {ocr}"


@dataclass
class Extraction:
    path: Path
    text: str = ""
    filename_text: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)
    page_count: int = 0
    pages_read: int = 0
    used_ocr: bool = False
    ocr_logo: bool = False      # OCR kördes på en logotypbild i brevhuvudet
    #: Medelkonfidens (0-100) från senaste OCR-körningen; -1 = ingen OCR.
    #: Underlag för dialogens procentskala och för --status/--diag.
    ocr_conf: float = -1.0
    #: Flersidig matchning: token -> antal sidor den förekommer på, bara
    #: tokens som upprepas på minst två sidor (brevhuvud/sidfot som åter-
    #:kommer = starkt avsändarbevis). Tom vid t.ex. pdfminer (inga sidor).
    token_pages: Dict[str, int] = field(default_factory=dict)
    error: str = ""
    #: Dokumentets datum, valt enligt reglerna i find_document_date().
    doc_date: Optional[date] = None
    #: Varför just det datumet valdes: "fakturadatum", "brevhuvud",
    #: "text", "filens tid" eller "" när inget hittades.
    date_source: str = ""
    #: Alla datum som hittades, med etikett. Används i förklaringsrutan
    #: och vid felsökning - man ska kunna se vad som fanns att välja på.
    date_candidates: List[Tuple[date, str]] = field(default_factory=list)

    @property
    def combined(self) -> str:
        """Sidtext + metadata + filnamn. Det är detta som analyseras.

        Sidtexten ligger FÖRST så att brevhuvudsanalysen ser dokumentets
        riktiga första rader. Låg man filnamnet först tolkades det som
        brevhuvud, och en fil som hette "offert_101.pdf" fick analysen att
        tro att dokumentet började med ordet "offert".
        """
        # Radbrytning mellan fälten, inte mellanslag. Med mellanslag flyter
        # titelns sista ord ihop med författarens första, och regexen för
        # firmanamn hittar "Pilkington Pilkington Sverige AB" - ett namn
        # som inte finns i dokumentet.
        # Metadata som redan ingår i brödtexten hoppas över - annars
        # dubbelräknas t.ex. titeln i matchningen (korrekthet/design).
        norm = normalize(self.text)
        meta = "\n".join(str(v) for k, v in self.metadata.items()
                         if v and not k.startswith("_")
                         and normalize(str(v)) not in norm)
        return "\n".join(p for p in (self.text, meta, self.filename_text) if p)

    @property
    def page_header(self) -> str:
        """Text i sidornas överkant - logotyp och firmanamn."""
        return self.metadata.get("_page_header", "")

    @property
    def page_footer(self) -> str:
        """Text i sidornas underkant - ofta org.nr, bankgiro och adress."""
        return self.metadata.get("_page_footer", "")

    # -- serialisering (design): modulen äger själv formatet för
    # diskcachen, så att huvudfilen inte behöver känna till internen.
    def to_cache_dict(self) -> Dict[str, Any]:
        """Fullständigt serialiserat tillstånd för bestående textcache."""
        return {
            "text": self.text,
            "filename_text": self.filename_text,
            "metadata": {k: v for k, v in self.metadata.items()
                         if isinstance(v, str)},
            "page_count": self.page_count,
            "pages_read": self.pages_read,
            "used_ocr": self.used_ocr,
            "ocr_logo": self.ocr_logo,
            "ocr_conf": self.ocr_conf,
            "doc_date": self.doc_date.isoformat() if self.doc_date else None,
            "date_source": self.date_source,
            "token_pages": {t: int(c) for t, c in (self.token_pages or {}).items()},
        }

    @classmethod
    def from_cache_dict(cls, path: Path, d: Dict[str, Any]) -> "Extraction":
        ext = cls(path=path)
        ext.text = d.get("text", "")
        ext.filename_text = d.get("filename_text", "")
        ext.metadata = d.get("metadata", {}) or {}
        ext.page_count = int(d.get("page_count", 0) or 0)
        ext.pages_read = int(d.get("pages_read", 0) or 0)
        ext.used_ocr = bool(d.get("used_ocr"))
        ext.ocr_logo = bool(d.get("ocr_logo"))
        try:
            ext.ocr_conf = float(d.get("ocr_conf", -1.0))
        except (TypeError, ValueError):
            ext.ocr_conf = -1.0
        try:
            ext.doc_date = (date.fromisoformat(d["doc_date"])
                            if d.get("doc_date") else None)
        except (ValueError, TypeError):
            ext.doc_date = None
        ext.date_source = d.get("date_source", "") or ""
        try:
            ext.token_pages = {str(t): int(c) for t, c
                               in (d.get("token_pages") or {}).items()}
        except (TypeError, ValueError):
            ext.token_pages = {}
        return ext

    def __repr__(self) -> str:
        return (f"<Extraction {self.path.name}: {len(self.text)} tkn, "
                f"ocr={self.used_ocr}, conf={self.ocr_conf:.0f}, "
                f"datum={self.doc_date}>")


GENERIC_META = {
    "anonymous", "unspecified", "untitled", "unknown", "none", "null", "n/a",
    "document", "dokument", "microsoft word", "microsoft excel", "word",
    "acrobat", "distiller", "ghostscript", "reportlab", "opensource",
    "reportlab pdf library", "pdfcreator", "pdf", "scan", "scanned", "image",
    "print", "utskrift", "canon", "epson", "xerox", "hp", "kyocera", "ricoh",
}


def _useful_meta(value: str) -> bool:
    """Sant om ett metadatafält är värt att analysera."""
    v = normalize(value)
    if len(v) < 3 or v in GENERIC_META:
        return False
    return not any(g in v for g in ("reportlab", "acrobat", "ghostscript",
                                    "pdfcreator", "microsoft", "libreoffice",
                                    "openoffice", "anonymous", "unspecified"))


def _clean(text: str) -> str:
    text = (text or "").replace("\u00ad", "").replace("\x00", " ")
    # Avstavning över radbrytning läks ihop: "Pilkington-\nSverige AB" blir
    # "Pilkington Sverige AB" - annars tappar matchningen firmanamnet.
    text = re.sub(r"([^\W_])-\s*\n\s*", r"\1 ", text)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


#: Hur stor andel av sidan som räknas som sidhuvud respektive sidfot.
#: Sidfoten är värdefull: på svenska fakturor står avsändarens org.nr,
#: bankgiro och adress nästan alltid där.
PAGE_HEADER_BAND = 0.14
PAGE_FOOTER_BAND = 0.86

#: Skyddstak vid max_pages = 0 (alla sidor). Hindrar att en enstaka
#: tusensidig bilaga låser bevakningen.
HARD_PAGE_CAP = 300


def _page_bands(page) -> Tuple[str, str]:
    """Returnerar (sidhuvud, sidfot) för en sida, utifrån var texten sitter.

    Text som ligger i sidans övre eller nedre kant är återkommande
    ram-information: logotyp och firmanamn högst upp, organisationsnummer
    och bankgiro längst ned. Båda hör till avsändaren.
    """
    top, bottom = [], []
    try:
        height = page.rect.height or 1.0
        bredd = page.rect.width or 1.0
        for block in page.get_text("blocks") or []:
            if len(block) < 5:
                continue
            x0, y0, y1 = block[0], block[1], block[3]
            text = str(block[4] or "").strip()
            if not text:
                continue
            if y1 <= height * PAGE_HEADER_BAND:
                top.append((y0, x0, text))
            elif y0 >= height * PAGE_FOOTER_BAND:
                bottom.append((y0, x0, text))
    except Exception:
        return "", ""

    def ordna(block_lista):
        """Läs vänster spalt före höger, rad för rad.

        Avsändaren står till vänster i brevhuvudet; dokumenttypen och
        fakturanumret till höger. Sorteras de bara på y-led blandas de
        ihop och `_header_zone()` tror att brevhuvudet slutar vid ordet
        FAKTURA - mitt i avsändarens adress.
        """
        vänster = [b for b in block_lista if b[1] < bredd * 0.5]
        höger = [b for b in block_lista if b[1] >= bredd * 0.5]
        vänster.sort(key=lambda b: (b[0], b[1]))
        höger.sort(key=lambda b: (b[0], b[1]))
        return [b[2] for b in vänster] + [b[2] for b in höger]

    return "\n".join(ordna(top)), "\n".join(ordna(bottom))


def _page_extras(page) -> str:
    """Text som inte kommer med i vanlig sidtext.

    Anteckningar, stämplar och ifyllda formulärfält innehåller ibland just
    det som identifierar avsändaren, men hoppas över av get_text().
    """
    out = []
    try:
        for annot in page.annots() or []:
            info = annot.info or {}
            for key in ("content", "title", "subject"):
                val = str(info.get(key) or "").strip()
                if val:
                    out.append(val)
    except Exception:
        pass
    try:
        for widget in page.widgets() or []:
            val = str(getattr(widget, "field_value", "") or "").strip()
            name = str(getattr(widget, "field_name", "") or "").strip()
            if val:
                out.append(f"{name} {val}".strip())
    except Exception:
        pass
    return "\n".join(out)


#: Tak för antalet spårade flersidiga tokens per fil (minnesbroms).
TOKEN_PAGES_MAX = 3000


def token_page_counts(page_texts) -> Dict[str, int]:
    """Räkna på hur många sidor varje ord förekommer (flersidig matchning).

    ANVÄNDARORDER 2026-09-07. Returnerar token -> antal sidor, men BARA
    för tokens som finns på minst två sidor: det är de som upprepas i
    brevhuvud/sidfot sida efter sida och därmed är starka avsändarbevis.
    Ensidiga tokens (den absoluta majoriteten) utelämnas - de ger inget
    bonusbidrag och skulle bara äta minne.
    """
    räknare: Dict[str, int] = {}
    for sida in page_texts:
        if not sida:
            continue
        # Mängd per sida: samma ord tio gånger på en sida är fortfarande
        # bara EN sida.
        for t in set(_TOKEN_RE.findall(normalize(sida))):
            räknare[t] = räknare.get(t, 0) + 1
    flersidiga = {t: c for t, c in räknare.items() if c >= 2}
    if len(flersidiga) > TOKEN_PAGES_MAX:
        # Behåll de vanligaste; överflödet ger marginellt bonusbidrag.
        flersidiga = dict(sorted(flersidiga.items(),
                                 key=lambda p: -p[1])[:TOKEN_PAGES_MAX])
    return flersidiga


def _x_pymupdf(path: Path, max_pages: int) -> Tuple[str, Dict[str, str], int, int]:
    """Läs hela dokumentet: brödtext, sidhuvud, sidfot, anteckningar och
    formulärfält. max_pages = 0 betyder alla sidor."""
    pymupdf = _open_pymupdf()
    header_txt: List[str] = []
    footer_txt: List[str] = []
    with pymupdf.open(str(path)) as doc:
        if doc.needs_pass:
            doc.authenticate("")
        meta = {k: str(v) for k, v in (doc.metadata or {}).items()
                if k in ("title", "author", "subject", "keywords")
                and v and _useful_meta(str(v))}
        total = len(doc)
        n = min(total, max_pages) if max_pages > 0 else min(total, HARD_PAGE_CAP)
        chunks = []
        sidtexter: List[str] = []          # en post per sida (flersidig)
        for i in range(n):
            page = doc[i]
            # sort=True läser i geometrisk ordning - uppifrån och ned,
            # vänster till höger. Utan den följer texten PDF:ens interna
            # ordning, och i tvåspaltiga fakturor hamnar högerspaltens
            # "FAKTURA nr 4471" mitt i avsändarens adress.
            try:
                sidtext = page.get_text("text", sort=True) or ""
            except TypeError:                     # äldre PyMuPDF
                sidtext = page.get_text("text") or ""
            chunks.append(sidtext)
            extras = _page_extras(page)
            if extras:
                chunks.append(extras)
                sidtext = sidtext + "\n" + extras
            sidtexter.append(sidtext)
            top, bottom = _page_bands(page)
            if top:
                header_txt.append(top)
            if bottom:
                footer_txt.append(bottom)

    text = _clean("\n".join(chunks))

    # Sidhuvud/sidfot från ALLA sidor (ANVÄNDARORDER: matcha på alla blad):
    # avsändarens org.nr upprepas i sidfoten på varje sida, så deduplicerade
    # band från hela dokumentet ger säkrare avsändarbevis än bara sida 1-3.
    def _unika(lista):
        out = []
        for x in lista:
            if x not in out:
                out.append(x)
        return out
    if header_txt:
        meta["_page_header"] = _clean("\n".join(_unika(header_txt)[:10]))
    if footer_txt:
        meta["_page_footer"] = _clean("\n".join(_unika(footer_txt)[:10]))
    tp = token_page_counts(sidtexter)
    if tp:
        meta["_token_pages"] = json.dumps(tp, ensure_ascii=False)
    return text, meta, n, total


def _x_pypdf(path: Path, max_pages: int) -> Tuple[str, Dict[str, str], int, int]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception:
            pass
    info = reader.metadata or {}
    meta = {}
    for key in ("/Title", "/Author", "/Subject", "/Keywords"):
        try:
            val = info.get(key)
        except Exception:
            val = None
        if val and _useful_meta(str(val)):
            meta[key.strip("/").lower()] = str(val)
    total = len(reader.pages)
    # Skyddstak även här (pymupdf-vägen har det): en patologisk bilaga
    # får aldrig äta all tid/minne.
    n = min(total, max_pages) if max_pages > 0 else min(total, HARD_PAGE_CAP)
    chunks = []
    for i in range(n):
        try:
            chunks.append(reader.pages[i].extract_text() or "")
        except Exception:
            chunks.append("")
    tp = token_page_counts(chunks)
    if tp:
        meta["_token_pages"] = json.dumps(tp, ensure_ascii=False)
    return _clean("\n".join(chunks)), meta, n, total


def _x_pdfminer(path: Path, max_pages: int) -> Tuple[str, Dict[str, str], int, int]:
    from pdfminer.high_level import extract_text
    # max_pages = 0 betyder "alla sidor" - sätt samma skyddstak som de
    # andra motorerna i stället för att låta pdfminer läsa oändligt.
    tak = max_pages if max_pages > 0 else HARD_PAGE_CAP
    text = extract_text(str(path), maxpages=tak) or ""
    # Ärlig sidräkning (tidigare påstods max_pages lästa även när filen
    # var kortare - och total var alltid 0). Snabb bläddring utan
    # textextraktion; misslyckas den blir det 0 = "okänt".
    total = 0
    try:
        from pdfminer.pdfpage import PDFPage
        with open(path, "rb") as fh:
            total = sum(1 for _ in PDFPage.get_pages(fh))
    except Exception:
        total = 0
    lästa = min(tak, total) if total > 0 else 0
    return _clean(text), {}, lästa, total


def _win_dold() -> Dict[str, Any]:
    """Windows: starta underprocesser utan konsolfönster (pythonw ska
    aldrig blinka). Tom dict på andra plattformar."""
    if not sys.platform.startswith("win"):
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {"startupinfo": si, "creationflags": 0x08000000}


def _render_pages(path: Path, max_pages: int, dpi: int = 200) -> List[Any]:
    """Rendera de första sidorna till PIL-bilder (för OCR)."""
    from PIL import Image
    images: List[Any] = []
    if has_pymupdf():
        pymupdf = _open_pymupdf()
        zoom = dpi / 72.0
        with pymupdf.open(str(path)) as doc:
            if doc.needs_pass:
                doc.authenticate("")
            for i in range(min(len(doc), max_pages)):
                pix = doc[i].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
                images.append(Image.open(io.BytesIO(pix.tobytes("png"))))
        return images
    exe = shutil.which("pdftoppm")
    if exe:
        with tempfile.TemporaryDirectory() as tmp:
            # Hängningsskydd: 60 s tak (ANVÄNDARORDER: får ej låsa sig).
            try:
                subprocess.run([exe, "-r", str(dpi), "-f", "1", "-l", str(max_pages),
                                "-png", str(path), str(Path(tmp) / "page")],
                               check=False, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=60,
                               **_win_dold())
            except subprocess.TimeoutExpired:
                pass
            for png in sorted(Path(tmp).glob("page*.png")):
                with Image.open(png) as im:
                    images.append(im.copy())
    return images


#: Kvalitetsnivåer för OCR. "high" ger klart bättre resultat än "standard",
#: priset är längre körtid. Väljs i Inställningar (nyckeln "ocr_quality").
OCR_QUALITY_LEVELS: Dict[str, str] = {
    "standard": "snabb, lägre upplösning",
    "high":     "hög kvalitet - bäst avläsning",
}

#: Mål-bredd (i pixlar) per kvalitetsnivå när en sida är för liten.
_OCR_TARGET_WIDTH = {"standard": 2000, "high": 2600}

#: Skyddstak: bredare sidor än så här krymps före OCR. Jättebredder
#: (t.ex. A0-ritningar i 300 dpi) skulle annars sluka minne och få
#: tesseract att sega ner sig utan att läsbarheten blir bättre.
_OCR_MAX_WIDTH = 5200

#: Statistik från senaste OCR-körningen, för reading_health()/--status.
_OCR_LAST = {"sekunder": 0.0, "konfidens": -1.0}


def reading_health() -> Dict[str, Any]:
    """Läsningens hälsa för --status/--diag (felsökningsdesign).

    Ger motor/OCR-status plus tid och konfidens för senaste OCR-körningen,
    så att man utan att öppna appen ser om avläsningen mår bra.
    """
    st = backend_status()
    return {
        "status": status_text(),
        "ocr_ready": st["ocr_ready"],
        "senaste_ocr_sekunder": _OCR_LAST["sekunder"],
        "senaste_ocr_konfidens": _OCR_LAST["konfidens"],
    }


#: Vanliga OCR-förväxlingar mellan bokstäver och siffror. Ersättningen sker
#: BARA i teckenrunor som redan domineras av siffror - vanliga ord som
#: "Oslo" eller "Ill" röras inte, men "556O33-9O86" läks till ett org.nr.
_OCR_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1"})


def denoise_numbers(text: str) -> str:
    """Byt ut vanliga OCR-förväxlingar (O/0, I/l/1) i sifferdominerade runor.

    '556O33-9O86' -> '556033-9086'. Det här är grunden för den
    brus-toleranta matchningen (REQ-N6): zonerna söker både på original-
    texten och på den avbrusade kopian, så en enda felskannad bokstav
    förstör inte längre ett starkt bevis.
    """
    def fix(m: "re.Match[str]") -> str:
        s = m.group(0)
        digits = sum(c.isdigit() for c in s)
        return s.translate(_OCR_DIGIT_FIX) if digits >= 3 else s
    return re.sub(r"[0-9A-Za-z]{4,}", fix, text)


def _binarize(img):
    """Tröskla en gråbild med Otsu-metoden - bleka skanningar får skarpa kanter.

    Histogrammet är 256 spann, så tröskeln kostar försumbart även för stora
    sidor. LSTM-OCR:n läser tydligt svart/vitt bättre än halvgrått.
    """
    try:
        g = img.convert("L")
        hist = g.histogram()
        total = sum(hist)
        if not total:
            return g
        sum_all = sum(i * n for i, n in enumerate(hist))
        sum_b, w_b = 0.0, 0
        best_t, best_var = 127, -1.0
        for t in range(256):
            w_b += hist[t]
            if not w_b:
                continue
            w_f = total - w_b
            if not w_f:
                break
            sum_b += t * hist[t]
            diff = sum_b / w_b - (sum_all - sum_b) / w_f
            var = w_b * w_f * diff * diff
            if var > best_var:
                best_var, best_t = var, t
        return g.point(lambda p, t=best_t: 255 if p > t else 0)
    except Exception:
        return img


def _deskew_angle(img, max_angle: float = 5.0, steps: int = 11) -> float:
    """Uppskatta sidans skevhet i grader.

    Enkel metod utan OpenCV: rotera en nedskalad kopia i några vinklar och
    välj den vars horisontella projektionsprofil har högst varians (jämna
    textrader ger höga, tydliga toppar). Returnerar 0.0 när inget kan mätas.
    """
    try:
        from PIL import Image
        # Fort: mät på en liten kopia, inte på hela sidan.
        test = img
        if test.width > 700:
            test = test.resize((700, int(test.height * 700 / test.width)),
                               Image.BILINEAR)
        gray = test.convert("L")
        h = gray.size[1]
        half = steps // 2
        best_angle, best_var = 0.0, -1.0
        for i in range(steps):
            a = max_angle * (i - half) / half
            rot = gray.rotate(a, resample=Image.BILINEAR, expand=False,
                              fillcolor=255)
            # Radprofilen i C-fart: en BOX-nedskalning till 1 pixel bredd är
            # exakt radmedlen - variansen över dem är projektionsvariansen.
            # (Den gamla pixelslingan i Python tog sekunder per sida.)
            vals = [255 - b for b in rot.resize((1, h), Image.BOX).tobytes()]
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            if var > best_var:
                best_var, best_angle = var, a
        return best_angle
    except Exception:
        return 0.0


def _preprocess(img, quality: str = "high", do_deskew: bool = True):
    """Förbehandla en sida före OCR.

    Grånivå → kontrast (autolevel) → ev. skevhetsrättning → uppskalning till
    en resolutionsnivå som ger läsbar text. Allt görs med PIL, så inget nytt
    paket krävs (OpenCV skulle ge ännu bättre resultat om det finns).
    """
    from PIL import Image
    # Normalisera till gråskala
    if img.mode == "RGBA":
        img = img.convert("RGB")
    if img.mode == "RGB":
        img = img.convert("L")
    elif img.mode != "L":
        img = img.convert("L")

    # Kontrast: blekta skanningar får "liv" - men BARA då kontrasten
    # faktiskt är låg. autocontrast med cutoff klipper annars bort
    # textpixlarna när de är <1 % av ytan (högkontrastskanningar fick
    # osynlig text och OCR:n såg ingenting; fångat 2026-10-05).
    lo, hi = img.getextrema()
    if hi - lo < 120:
        span = max(1, hi - lo)
        img = img.point(lambda p, lo=lo, span=span:
                        max(0, min(255, int((p - lo) * 255 / span))))

    # Skevhet
    if do_deskew:
        angle = _deskew_angle(img)
        if abs(angle) >= 0.1:
            img = img.rotate(angle, resample=Image.BICUBIC, expand=False,
                             fillcolor=255)

    # Uppskala så att små tecken blir läsbara
    target = _OCR_TARGET_WIDTH.get(quality, 2600)
    if img.width and img.width < target:
        scale = target / img.width
        img = img.resize((int(img.width * scale),
                          int(img.height * scale)), Image.LANCZOS)
    # ...men aldrig bredare än taket (minnes- och tidsskydd).
    if img.width and img.width > _OCR_MAX_WIDTH:
        scale = _OCR_MAX_WIDTH / img.width
        img = img.resize((int(img.width * scale),
                          int(img.height * scale)), Image.LANCZOS)
    return img


def _resolve_langs(pytesseract, language: str) -> str:
    """Välj installerade språk; fallback till eng. Kastar aldrig.

    Tidigare fanns den här logiken i tre kopior (_run_ocr,
    ocr_header_logo, ocr_embedded_images) - nu på ett ställe.
    """
    try:
        available = set(pytesseract.get_languages(config=""))
        wanted = [l for l in (language or "eng").split("+") if l in available]
        if not wanted:
            wanted = ["eng"] if "eng" in available else sorted(available)[:1]
        return "+".join(wanted)
    except Exception:
        return language or "eng"


def _tess_call(fn, img, langs: str, cfg: str, **extra):
    """Tesseract-anrop med 60 s timeout där versionen stöder det -
    en hängande tesseract-process får aldrig låsa appen."""
    try:
        return fn(img, lang=langs, config=cfg, timeout=60, **extra)
    except TypeError:                      # äldre pytesseract utan timeout
        return fn(img, lang=langs, config=cfg, **extra)


def _ocr_pass(img, langs: str, cfg: str, pytesseract) -> Tuple[float, str]:
    """OCR:a en bild och returnerar (medelkonfidens, text).

    `image_to_data` ger konfidens per ord, vilket låter flera
    konfigurationer jämföras objektivt - grunden för "Bättre OCR" i REQ-N5.
    Missar datan fallbackas till ren text med konfidens 0.
    """
    try:
        d = _tess_call(pytesseract.image_to_data, img, langs, cfg,
                       output_type=pytesseract.Output.DICT)
        confs = [int(c) for c in d.get("conf", [])
                 if str(c).lstrip("-").isdigit() and int(c) > 0]
        text = " ".join(w for w in d.get("text", []) if w and w.strip())
        score = sum(confs) / len(confs) if confs else 0.0
        return score, text
    except Exception:
        try:
            return 0.0, _tess_call(pytesseract.image_to_string, img, langs, cfg)
        except Exception:
            return 0.0, ""


def _run_ocr(path: Path, max_pages: int, language: str, quality: str = "high",
             dpi: int = 300) -> str:
    try:
        import pytesseract
    except Exception:
        return "", -1.0   # OCR inte installerat - tyst reserv, ingen krasch
    exe = tesseract_binary()
    if exe:
        pytesseract.pytesseract.tesseract_cmd = exe
    langs = _resolve_langs(pytesseract, language)
    images = _render_pages(path, max_pages, dpi=dpi)
    if not images:
        return "", -1.0

    def ocr_one(img):
        """En sida, flera konfigurationer, bästa konfidens vinner (REQ-N5):
        psm 3 på den förbehandlade gråbilden, och på "high" dessutom psm 6
        på en Otsu-binariserad kopia - bleka skanningar får skarpare kanter
        för LSTM:n."""
        skapade = [img]
        try:
            # deskew endast i "high" (snabbhet): standardläget hoppar över
            # skevhetsanalysen, som är den dyraste förbehandlingsdelen.
            pre = _preprocess(img, quality, do_deskew=(quality == "high"))
            skapade.append(pre)
            passes = [(pre, "--oem 1 --psm 3")]
            if quality == "high":
                bin_ = _binarize(pre)
                skapade.append(bin_)
                passes.append((bin_, "--oem 1 --psm 6"))
                # Extra pass 2026-10-15 (bättre avläsning): psm 4 antar
                # en enda textkolumn med varierande innehåll - fångar
                # skanningar som psm 3/6 delar upp fel.
                passes.append((pre, "--oem 1 --psm 4"))
                # Extra avläsningspass på 1,5× uppskalad bild: liten och
                # blek text som annars försvinner (bättre avläsning).
                try:
                    from PIL import Image as _PIL
                    big = pre.resize((int(pre.width * 1.5),
                                      int(pre.height * 1.5)), _PIL.LANCZOS)
                    skapade.append(big)
                    passes.append((big, "--oem 1 --psm 3"))
                except Exception:
                    pass
            best_text, best_score = "", -1.0
            for pim, pcfg in passes:
                score, text = _ocr_pass(pim, langs, pcfg, pytesseract)
                # Längden bryter lika: mer text är bättre än ingen, men
                # konfidens går alltid först.
                komb = score + min(len(text), 2000) * 0.01
                if komb > best_score:
                    best_score, best_text = komb, text
            return best_text, best_score
        except Exception:
            return "", -1.0
        finally:
            for im in skapade:
                try:
                    im.close()
                except Exception:
                    pass

    # Parallell OCR: varje sida i egen tråd. Tesseract arbetar i
    # subprocesser, så GIL hindrar inte - en tresidig skanning blir nära
    # tre gånger snabbare (ANVÄNDARORDER: mycket snabbare).
    workers = max(1, min(4, len(images)))
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="pdfsorter-ocr") as pool:
        futs = [pool.submit(ocr_one, im) for im in images]
        texts: List[str] = []
        confs: List[float] = []
        for f in futs:
            # 90 s per sida: en patologisk skanning får aldrig hänga appen.
            try:
                txt, sc = f.result(timeout=90)
            except Exception:
                txt, sc = "", -1.0
                f.cancel()
            if txt:
                texts.append(txt)
                if sc > 0:
                    confs.append(sc)
    conf = sum(confs) / len(confs) if confs else -1.0
    _OCR_LAST["sekunder"] = round(time.time() - t0, 2)
    _OCR_LAST["konfidens"] = round(conf, 1)
    # \f mellan sidorna markerar sidgränsen: extract() räknar flersidiga
    # tokens på dem. _clean och senare normalisering påverkas inte -
    # tecknet överlever städningen och blir blanksteg vid normalisering.
    return _clean("\n\f\n".join(texts)), conf


#: Andel av sidhöjden som räknas som "brevhuvud" - där avsändaren står.
HEADER_FRACTION = 0.33

#: En bild måste vara minst så här stor för att vara värd att OCR:a.
MIN_LOGO_AREA_PT = 2500      # ca 50x50 punkter
MIN_LOGO_WIDTH_PT = 60


def header_images(path: Path) -> List[Any]:
    """Hitta bilder i sidans övre del på sida 1 - typiskt logotypen.

    Många affärs-PDF:er är hybrider: brödtexten är riktig text medan
    avsändarens namn bara finns i en logotypbild. Textlagret ser då
    komplett ut, men själva firmanamnet saknas helt.
    """
    if not has_pymupdf():
        return []
    from PIL import Image
    pymupdf = _open_pymupdf()
    crops: List[Any] = []
    try:
        with pymupdf.open(str(path)) as doc:
            if doc.needs_pass:
                doc.authenticate("")
            if not len(doc):
                return []
            page = doc[0]
            cutoff = page.rect.y0 + page.rect.height * HEADER_FRACTION
            boxes = []
            for info in page.get_images(full=True):
                try:
                    for rect in page.get_image_rects(info[0]):
                        if (rect.y0 <= cutoff
                                and rect.width >= MIN_LOGO_WIDTH_PT
                                and rect.width * rect.height >= MIN_LOGO_AREA_PT):
                            boxes.append(rect)
                except Exception:
                    continue
            if not boxes:
                return []
            # Rendera i hög upplösning - logotyptext är ofta liten
            for rect in boxes[:4]:
                pad = 4
                clip = pymupdf.Rect(rect.x0 - pad, rect.y0 - pad,
                                    rect.x1 + pad, rect.y1 + pad) & page.rect
                pix = page.get_pixmap(matrix=pymupdf.Matrix(4.0, 4.0), clip=clip)
                crops.append(Image.open(io.BytesIO(pix.tobytes("png"))))
    except Exception:
        return []
    return crops


def embedded_images(path: Path, max_images: int = 6,
                    max_pages: int = 3) -> List[Any]:
    """Bilder över hela sidorna, inte bara brevhuvudet.

    Avsändaren kan gömma sig i en stämpel, annons eller bild längre ned
    (ANVÄNDARORDER: appen ska kunna tolka bilderna i PDF:en). Största
    bilderna först, med tak så att det aldrig spårar.
    """
    if not has_pymupdf():
        return []
    from PIL import Image
    pymupdf = _open_pymupdf()
    crops: List[Any] = []
    try:
        # Ett enda dokumentöppnande (tidigare två: hitta + rendera) -
        # halva I/O-kostnaden för stora filer.
        with pymupdf.open(str(path)) as doc:
            if doc.needs_pass:
                doc.authenticate("")
            found: List[Tuple[float, int, Any]] = []
            for pno in range(min(len(doc), max_pages)):
                page = doc[pno]
                for info in page.get_images(full=True):
                    try:
                        for rect in page.get_image_rects(info[0]):
                            area = rect.width * rect.height
                            if (rect.width >= MIN_LOGO_WIDTH_PT
                                    and area >= MIN_LOGO_AREA_PT):
                                found.append((area, pno, rect))
                    except Exception:
                        continue
            found.sort(key=lambda t: -t[0])
            for _, pno, rect in found[:max_images]:
                page = doc[pno]
                pad = 4
                clip = pymupdf.Rect(rect.x0 - pad, rect.y0 - pad,
                                    rect.x1 + pad, rect.y1 + pad) & page.rect
                pix = page.get_pixmap(matrix=pymupdf.Matrix(3.0, 3.0), clip=clip)
                crops.append(Image.open(io.BytesIO(pix.tobytes("png"))))
        return crops
    except Exception:
        return crops


def ocr_embedded_images(path: Path, language: str = "swe+eng") -> str:
    """Tolka bilderna i PDF:en: OCR:a de största inbäddade bilderna.

    Texten läggs till som brödtext (inte brevhuvud), så den stärker
    matchningen utan att låtsas vara avsändarrad.
    """
    if not ocr_available():
        return ""
    try:
        import pytesseract
    except Exception:
        return ""
    exe = tesseract_binary()
    if exe:
        pytesseract.pytesseract.tesseract_cmd = exe
    langs = _resolve_langs(pytesseract, language)
    out = []
    for img in embedded_images(path):
        pre = None
        try:
            # Ingen skevhetsrättning för stämplar/logotyper: de ligger
            # redan raka, och deskew är förbehandlingens dyraste steg.
            pre = _preprocess(img, "high", do_deskew=False)
            out.append(_tess_call(pytesseract.image_to_string, pre, langs,
                                  "--oem 1 --psm 6"))
        except Exception:
            continue
        finally:
            # BÅDA bilderna stängs - originalet läckte tidigare när
            # förbehandlingen skapade en ny bild.
            for im in (img, pre):
                try:
                    im.close()
                except Exception:
                    pass
    return _clean("\n".join(t for t in out if t))


def ocr_header_logo(path: Path, language: str = "swe+eng") -> str:
    if not ocr_available():
        return ""
    try:
        import pytesseract
    except Exception:
        return ""
    exe = tesseract_binary()
    if exe:
        pytesseract.pytesseract.tesseract_cmd = exe
    langs = _resolve_langs(pytesseract, language)
    out = []
    for img in header_images(path):
        pre = None
        try:
            pre = _preprocess(img, "high", do_deskew=False)
            # psm 6: en sammanhållen textblock - passar logotyper bra.
            # oem 1 (LSTM) ger bättre teckenigenkänning på små bilder.
            # _tess_call ger 60 s timeout - direktanropet tidigare kunde
            # hänga appen om tesseract kärvar.
            out.append(_tess_call(pytesseract.image_to_string, pre, langs,
                                  "--oem 1 --psm 6"))
        except Exception:
            continue
        finally:
            # Båda bilderna stängs: originalet läckte tidigare, eftersom
            # variabeln skrevs över av den förbehandlade kopian.
            for im in (img, pre):
                try:
                    im.close()
                except Exception:
                    pass
    return _clean("\n".join(out))


def extract(path: Path, max_pages: int = 0, ocr_enabled: bool = True,
            ocr_max_pages: int = 3, ocr_language: str = "swe+eng",
            ocr_quality: str = "high", ocr_dpi: int = 300) -> Extraction:
    """Läs text ur en PDF. Kastar aldrig undantag - fel hamnar i .error."""
    res = Extraction(path=Path(str(path)))
    try:
        path = Path(path)
        res.filename_text = re.sub(r"[_\-.]+", " ", path.stem)

        if not path.is_file():
            # Tydligare än att vänta på att varje motor rapporterar felet.
            res.error = f"Filen finns inte: {path}"
            return res

        for fn, ok in ((_x_pymupdf, has_pymupdf()),
                       (_x_pypdf, has_pypdf()),
                       (_x_pdfminer, has_pdfminer())):
            if not ok:
                continue
            try:
                text, meta, pages, total = fn(path, max_pages)
                if len(text) > len(res.text):
                    res.text, res.metadata, res.pages_read = text, meta, pages
                    res.page_count = total or res.page_count
                if len(res.text) >= MIN_TEXT_CHARS:
                    res.error = ""
                    break
            except Exception as exc:
                res.error = f"{type(exc).__name__}: {exc}"

        if len(res.text) < MIN_TEXT_CHARS and ocr_enabled and ocr_available():
            # Helt skannad sida - OCR:a allt
            try:
                ocr_text, conf = _run_ocr(path, max(1, ocr_max_pages),
                                          ocr_language,
                                          quality=ocr_quality, dpi=ocr_dpi)
                if len(ocr_text) > len(res.text):
                    res.text, res.used_ocr, res.error = ocr_text, True, ""
                    res.ocr_conf = conf
            except Exception as exc:
                res.error = res.error or f"OCR misslyckades: {exc}"
        elif ocr_enabled and ocr_available():
            # Hybrid-PDF: textlagret ser komplett ut, men avsändaren kan ändå
            # sitta i en logotypbild. OCR:a bara brevhuvudet - det är billigt
            # och det är där firmanamnet står.
            try:
                logo_text = ocr_header_logo(path, ocr_language)
                if logo_text:
                    new_lines = [ln for ln in logo_text.splitlines()
                                 if normalize(ln) and normalize(ln) not in normalize(res.text)]
                    if new_lines:
                        # Först i texten - brevhuvudet ska väga tyngst
                        res.text = "\n".join(new_lines) + "\n" + res.text
                        res.ocr_logo = True
            except Exception:
                pass
            # TOLKA BILDERNA (ANVÄNDARORDER 2026-08-26): största inbäddade
            # bilderna OCR:as och läggs sist som brödtext.
            try:
                img_text = ocr_embedded_images(path, ocr_language)
                if img_text:
                    norm = normalize(res.text)
                    body_lines = [ln for ln in img_text.splitlines()
                                  if normalize(ln) and normalize(ln) not in norm]
                    if body_lines:
                        res.text = res.text + "\n" + "\n".join(body_lines)
                        res.ocr_logo = True
            except Exception:
                pass

        if not res.text and not res.error:
            res.error = "Ingen text kunde läsas (skannad PDF utan OCR?)"

        # Flersidig matchning (ANVÄNDARORDER 2026-09-07): vilka ord som
        # upprepas över flera sidor. PDF-motorerna levererar räkningen som
        # metadata; OCR-vägen får den från \f-märkta sidgränser.
        try:
            tp_raw = res.metadata.pop("_token_pages", "")
            if tp_raw:
                res.token_pages = {str(t): int(c) for t, c
                                   in json.loads(tp_raw).items()}
            elif res.used_ocr and "\f" in res.text:
                res.token_pages = token_page_counts(res.text.split("\f"))
        except Exception:
            res.token_pages = {}

        # Datumet plockas ut här, en gång, så att det följer med i TextCache
        # tillsammans med texten. Matchningen påverkas inte - datumet styr
        # bara vilken undermapp filen hamnar i.
        if res.text:
            try:
                res.doc_date, res.date_source, res.date_candidates = \
                    find_document_date(res.text, res.page_header, res.filename_text)
            except Exception:
                pass
    except Exception as exc:
        # REQ-B1 AC-1.2: extract() kastar aldrig - allt hamnar i .error.
        res.error = res.error or f"{type(exc).__name__}: {exc}"
    return res



# Ord som finns i nästan alla affärsdokument och därför är värdelösa som
# stödord. Svenska + engelska.
STOPWORDS = set("""
och eller men att som det den de dem denna detta dessa vi ni jag du han hon
är var vara varit blev blir bli har hade haft ha ska skall skulle kan kunde
måste bör får fick få vid till från med för utan under över efter före mot
per samt enligt genom om av på i en ett den där här när hur vad vem vilken
inte icke ingen inget inga alla allt all andra annan annat samma egen egna
faktura fakturan fakturor fakturanr fakturadatum fakturanummer kvitto
order ordernummer ordernr orderbekräftelse offert offertnummer följesedel
leverans leveransadress leveransdatum leveransvillkor fraktsedel packsedel
kund kundnummer kundnr kundadress kontakt kontaktperson referens ert vårt
er vår våra ers dnr diarienummer ärende ärendenummer
belopp summa totalt total delsumma nettosumma bruttosumma netto brutto
moms momsbelopp momssats momsreg momsregistreringsnummer vat exkl inkl
öresavrundning avrundning rabatt rabattsats
betalning betalningsvillkor betalningsdatum betalas dröjsmålsränta ränta
förfallodatum förfallodag förfaller kredit debet saldo
bankgiro plusgiro postgiro iban bic swift bank konto kontonummer
organisationsnummer orgnr org sätesort säte styrelsens godkänd innehar
f-skatt fskatt skattsedel registrerad registreringsnummer
datum dag månad år vecka tid klockan sida sidan sidor antal styck st
enhet pris enhetspris apris summa artikel artikelnummer artikelnr benämning
beskrivning specifikation kvantitet mängd vikt volym
adress postadress besöksadress postnummer postort ort land telefon tel
telefax fax mobil epost email mail webb web www hemsida internet
aktiebolag handelsbolag firma företag bolag avdelning enhet
hej hejsan tack vänligen med vänliga hälsningar hälsningar mvh bifogas
bifogad bilaga bilagor se nedan ovan enligt gäller avser
the and for with from this that these those you your our their its
invoice receipt order delivery customer number date page total amount
sum net gross tax vat payment terms due bank account address phone email
company ltd inc please thank thanks regards attached attachment note
description quantity unit price item items reference
anonymous unspecified untitled unknown document dokument reportlab opensource
acrobat distiller ghostscript pdfcreator producer creator library layer
ritning ritningar skiss underlag handling handlingar rapport protokoll
avtal kontrakt anbud upphandling faktureringsadress fakturaadress
foljesedel folisedel packlista plocklista returer reklamation
orderbekraftelse ordererkannande bekraftelse erkannande
projekt projektnummer etapp skala revidering rev version utgava
kvartal period lopnummer serie batch parti
drawing sketch contract agreement quote quotation tender proposal report
project phase scale revision issue sheet total page confidential copy
""".split())

# OCR-/kopi-brus som aldrig är ett stödord (bättre matchning, rond 4).
STOPWORDS.update({"kopia", "copy", "scanned", "ocr", "http", "www",
                  "page", "sid", "skanning", "kopia av"})

_ORGNR = re.compile(r"\b(\d{6})[-\u2013 ]?(\d{4})\b")


def _luhn_ok(digits: str) -> bool:
    """Kontrollsiffra enligt Luhn - svenska org.nr och personnr följer den.

    Utan den här kontrollen tolkas vilket 10-siffrigt nummer som helst som
    organisationsnummer, t.ex. referensnumret 7250438182 på en offert.
    """
    d = [int(c) for c in digits if c.isdigit()]
    if len(d) != 10:
        return False
    total = 0
    for i, x in enumerate(d[:9]):
        v = x * (2 if i % 2 == 0 else 1)
        total += v - 9 if v > 9 else v
    return (10 - total % 10) % 10 == d[9]
_VATNR = re.compile(r"\b[A-Z]{2}\d{9,12}\b")
_GIRO = re.compile(r"\b\d{3,4}-\d{4}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@([\w-]+\.[\w.-]+)\b", re.I)
_URL = re.compile(r"\b(?:https?://)?(?:www\.)([\w-]+\.[\w.-]{2,})\b", re.I)
#: Firmanamn med bolagsändelse. Mellanrummen är [ \t]+ och inte \s+ -
#: annars sträcker sig träffen över radbrytningar och slår ihop två
#: fristående namn till ett: "Anna Lindqvist\n\nPilkington Sverige AB".
_COMPANY = re.compile(
    r"\b([A-ZÅÄÖØÆ][\wÅÄÖåäöØæé&.\-]{1,24}(?:[ \t]+[A-ZÅÄÖØÆ0-9][\wÅÄÖåäöØæé&.\-]{0,24}){0,3})"
    r"[ \t]+(AB|Ab|ab|AS|A/S|ASA|Oy|Oyj|ApS|GmbH|AG|Ltd|Limited|LLC|Inc|BV|B\.V\.|NV|SA|SAS|SpA|KB|HB|Corp)\b")
# Fångar även flerordiga versalnamn: "SAINT-GOBAIN GLASS", "NSG GROUP"
_ALLCAPS = re.compile(
    r"\b([A-ZÅÄÖØÆ][A-ZÅÄÖØÆ0-9&\-]{2,24}(?:[ \t\-][A-ZÅÄÖØÆ][A-ZÅÄÖØÆ0-9&\-]{1,24}){0,2})\b")
_WORD = re.compile(r"[^\W\d_][\w\-åäöÅÄÖéèüÜøæ]{2,}", re.UNICODE)

#: Ord som börjar med versal mitt i en rad. Produktnamn och varumärken
#: ("Optifloat", "Suncool", "Planar") skrivs så, och de är ofta det enda
#: som skiljer en leverantör från en annan. Ett ord först på raden räknas
#: inte - då är versalen bara meningens början.
_PROPER = re.compile(
    r"(?<=[a-zåäö,;:]\s)([A-ZÅÄÖ][a-zåäöéèü]{2,}(?:[ \t][A-ZÅÄÖ][a-zåäöéèü]{2,}){0,2})")
_DATEISH = re.compile(r"^\d[\d\s./:-]*$")

#: Delar text i ord (bokstäver/siffror hör ihop) - för tokenräknaren i
#: suggest_keywords (snabbhet, rond 4).
_TOKEN_RE = re.compile(r"[^\W_]+")

# typ -> (vikt, etikett)
KIND_INFO = {
    "orgnr":   (3.0, "organisationsnummer"),
    "vat":     (3.0, "VAT-nummer"),
    "giro":    (2.2, "bankgiro/plusgiro"),
    "refnr":   (0.9, "referensnummer"),
    "domain":  (2.6, "domän"),
    "sender":  (2.8, "avsändare i brevhuvudet"),
    "company": (2.5, "företagsnamn"),
    "caps":    (2.0, "versaler"),
    "proper":  (1.7, "produkt- eller egennamn"),
    "phrase":  (1.4, "fras"),
    "word":    (1.0, "ord"),
}


@dataclass
class Candidate:
    text: str          # normaliserad form - det som sparas som regel
    display: str       # så som det såg ut i dokumentet
    kind: str
    count: int
    score: float

    @property
    def label(self) -> str:
        return KIND_INFO.get(self.kind, (1.0, "ord"))[1]

    def __repr__(self) -> str:
        return f"<Candidate {self.text!r}: {self.kind}, {self.score:.2f}>"


def _looks_like_code(text: str) -> bool:
    """Sant för dokumentkoder som A2-114, SK-2026-441, REV3.

    Sådana är utmärkta stödord men usla mappnamn.
    """
    if any(ch.isdigit() for ch in text) and len(text) <= 14:
        letters = sum(ch.isalpha() for ch in text)
        return letters <= 4 or bool(re.fullmatch(r"[a-zåäö]{1,4}[\s\-_]?[\d\-_/]+", text))
    return False


#: Etiketter som ofta står precis före ett företagsnamn i en faktura.
#: "Leveransadress HDK80T Haga Limo AB" -> "Haga Limo AB"
_LABEL_WORDS = {
    "leveransadress", "fakturaadress", "faktureringsadress", "postadress",
    "besoksadress", "besöksadress", "adress", "kund", "kundadress",
    "leverantor", "leverantör", "mottagare", "avsandare", "avsändare",
    "saljare", "säljare", "kopare", "köpare", "bestallare", "beställare",
    "referens", "kontakt", "kontaktperson", "attention", "att", "c/o",
    "faktura", "offert", "order", "till", "fran", "från", "levereras",
    "deliver", "invoice", "bill", "sold", "ship", "buyer", "seller",
    "customer", "supplier", "vendor", "recipient", "sender",
}


def _strip_labels(name: str) -> str:
    """Ta bort ledande etikettord ur ett upphittat företagsnamn."""
    parts = name.split()
    while parts and normalize(parts[0]) in _LABEL_WORDS:
        parts.pop(0)
    # Enstaka kod före namnet, t.ex. kundnumret "HDK80T"
    while len(parts) > 1 and _looks_like_code(normalize(parts[0])):
        parts.pop(0)
    return " ".join(parts)


#: Rader som aldrig är ett avsändarnamn.
_NOT_A_NAME = re.compile(
    r"^(?:[\d\W_]+|.*(?:@|www\.|https?://).*|.{0,2}|.{60,})$", re.I)


#: Ord som avslutar brevhuvudet - efter dem kommer aldrig firmanamnet.
_DOC_TYPE_WORDS = {
    "offert", "faktura", "fakturan", "order", "orderbekraftelse", "kvitto",
    "avtal", "kontrakt", "ritning", "rapport", "protokoll", "foljesedel",
    "packsedel", "entreprenadavtal", "avtalsnummer", "offertnr", "fakturanr",
    "invoice", "quote", "quotation", "receipt", "contract", "agreement",
    "delivery", "statement", "credit", "reminder", "kreditfaktura",
    "betalningspaminnelse", "sida", "page",
    # fler dokumenttyper som avslutar brevhuvudet
    "arbetsorder", "arbetsordning", "servicerapport", "besiktning",
    "besiktningsprotokoll", "egenkontroll", "tidrapport", "dagbok",
    "specifikation", "sammanstallning", "underlag", "bilaga", "intyg",
    "garantibevis", "reklamation", "returer", "kravbrev", "inkasso",
    "kontoutdrag", "arsredovisning", "attest", "rekvisition",
    "work", "service", "report", "inspection", "protocol", "timesheet",
    "packing", "shipment", "waybill", "remittance",
}

#: Rader som är adresser eller identifierare, inte namn.
_ADDRESS_HINT = re.compile(
    r"\b(?:box\s*\d|\d{3}\s?\d{2}\s+\w|gatan?\s|vagen?\s|väg(?:en)?\s|"
    r"street|road|avenue)\b|\d{5}", re.I)
_ID_HINT = re.compile(
    r"\b(?:org\.?\s?nr|orgnr|momsreg|vat|bankgiro|plusgiro|iban|bic|"
    r"tel|telefon|fax|mobil)\b", re.I)

#: Skiljetecken som används i slogans: "Bilglas • Stenskott • Solfilm"
_SLOGAN_SEP = re.compile(r"[•·|/]|\s[»«+]\s|\s-\s")


# ==========================================================================
# DATUM - för sortering i årsmappar
# ==========================================================================
#
# Ett affärsdokument innehåller nästan alltid flera datum: fakturadatum,
# förfallodatum, leveransdatum, utskriftsdatum. Väljer man fel hamnar
# fakturan i fel år, och då är hela årsindelningen värdelös. Reglerna
# nedan är därför byggda kring att UTESLUTA fel datum snarare än att
# hitta det första bästa.

#: Månadsnamn på svenska och engelska, i den form de får efter lower().
#: Både fullständiga namn och de trebokstavsförkortningar som är vanliga i
#: fakturasystem. Diakritiska varianter ("märz") skrivs sällan i svenska
#: fakturor och hanteras i så fall som okända månader - hellre det än ett
#: felaktigt datum.
_MONTHS: Dict[str, int] = {}
for _i, _names in enumerate((
        ("januari", "january", "jan"),
        ("februari", "february", "feb"),
        ("mars", "march", "mar", "marts"),
        ("april", "apr"),
        ("maj", "may"),
        ("juni", "june", "jun"),
        ("juli", "july", "jul"),
        ("augusti", "august", "aug"),
        ("september", "sept", "sep"),
        ("oktober", "october", "okt", "oct"),
        ("november", "nov"),
        ("december", "dec")), start=1):
    for _n in _names:
        _MONTHS[_n] = _i
del _i, _names, _n

#: Etiketter som pekar ut dokumentets EGET datum. Står någon av dem på
#: samma rad som ett datum vinner det datumet över alla andra.
_DATE_LABELS = re.compile(
    r"\b(?:faktura(?:ns)?datum|fakt\.?\s?datum|dokumentdatum|"
    r"ordersdatum|orderdatum|utskriftsdatum|utfärdad|utfardad|"
    r"leveransdatum|datum|date|invoice\s+date)\b", re.I)

#: Etiketter som pekar ut ett datum i FRAMTIDEN. De måste uteslutas -
#: ett förfallodatum ligger 30 dagar fram och kan lätt hamna i nästa år.
_DATE_EXCLUDE = re.compile(
    r"\b(?:förfallo(?:datum)?|forfallo(?:datum)?|förfaller|forfaller|"
    r"betalas\s+senast|sista\s+betalningsdag|betalningsvillkor|"
    r"giltig\s+(?:till|t\.o\.m)|due\s+date|expiry)\b", re.I)

#: Nedre gräns för ett rimligt dokumentdatum. Äldre än så är nästan
#: alltid ett feltolkat nummer.
_DATE_MIN_YEAR = 1990


def _mk_date(year: int, month: int, day: int) -> Optional[date]:
    """Skapa ett datum om kombinationen är rimlig, annars None.

    Fångar både orimliga år och omöjliga datum som 2025-02-30, vilket
    ett rent regex inte klarar.
    """
    if year < 100:                       # tvåsiffrigt år: 24 -> 2024
        year += 2000 if year < 70 else 1900
    if not (_DATE_MIN_YEAR <= year <= date.today().year + 1):
        return None
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        return date(year, month, day)
    except ValueError:                   # t.ex. 30 februari
        return None


def _dates_in_line(line: str) -> List[date]:
    """Alla giltiga datum på en rad, i den ordning de står.

    Raden gemenas först - månadsnamn skrivs med versal i engelska
    dokument ("March 14, 2025") och mitt i svenska meningar.
    """
    line = line.lower()
    out: List[date] = []

    def add(d: Optional[date]) -> None:
        if d is not None and d not in out:
            out.append(d)

    # 2025-03-14 · 2025.03.14 · 2025/03/14
    for m in re.finditer(r"\b(20\d{2})[-–./](\d{1,2})[-–./](\d{1,2})\b", line):
        add(_mk_date(int(m.group(1)), int(m.group(2)), int(m.group(3))))

    # 14/3 2025 · 14/3-25 · 14.3.2025
    for m in re.finditer(r"\b(\d{1,2})[/.](\d{1,2})[\s\-/.](\d{2,4})\b", line):
        add(_mk_date(int(m.group(3)), int(m.group(2)), int(m.group(1))))

    # 14 mars 2025 · 14 mar 2025
    for m in re.finditer(r"\b(\d{1,2})\s+([a-zåäö]{3,9})\.?\s+(\d{4})\b", line):
        mon = _MONTHS.get(m.group(2))
        if mon:
            add(_mk_date(int(m.group(3)), mon, int(m.group(1))))

    # mars 14, 2025 (engelsk ordning)
    for m in re.finditer(r"\b([a-zåäö]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b", line):
        mon = _MONTHS.get(m.group(1))
        if mon:
            add(_mk_date(int(m.group(3)), mon, int(m.group(2))))

    # 20250314 · 250314. Prövas sist och bara när inget annat hittades
    # på raden, annars plockar den sönder t.ex. fakturanummer.
    if not out:
        for m in re.finditer(r"\b(\d{6}|\d{8})\b", line):
            s = m.group(1)
            if len(s) == 8:
                add(_mk_date(int(s[:4]), int(s[4:6]), int(s[6:])))
            else:
                # Undvik att tolka organisationsnummer som datum
                add(_mk_date(int(s[:2]), int(s[2:4]), int(s[4:])))
    return out


def find_document_date(
        text: str, header: str = "", filename: str = "",
        prefer_label: bool = True) -> Tuple[Optional[date], str, List[Tuple[date, str]]]:
    """Hitta dokumentets datum.

    Returnerar (datum, källa, alla_kandidater). Källan är en kort svensk
    text som visas för användaren, så att ett felplacerat dokument går
    att förstå utan att öppna filen.

    Prioritering:
      1. Rad med en datumetikett ("Fakturadatum: 2025-03-14")
      2. Datum i brevhuvudet eller sidhuvudet
      3. Äldsta rimliga datumet i hela texten

    Rader med förfallodatum hoppas alltid över, oavsett steg.
    """
    kandidater: List[Tuple[date, str]] = []
    etikett: Optional[date] = None

    for rad in text.splitlines():
        rad = rad.strip()
        if not rad:
            continue
        # Ett förfallodatum ligger i framtiden och får aldrig styra.
        if _DATE_EXCLUDE.search(rad):
            for d in _dates_in_line(rad):
                kandidater.append((d, "förfallodatum (ej vald)"))
            continue
        träffar = _dates_in_line(rad)
        if not träffar:
            continue
        if prefer_label and etikett is None and _DATE_LABELS.search(rad):
            etikett = träffar[0]
            kandidater.append((träffar[0], "fakturadatum"))
            for d in träffar[1:]:
                kandidater.append((d, "text"))
            continue
        for d in träffar:
            kandidater.append((d, "text"))

    if etikett is not None:
        return etikett, "fakturadatum", kandidater

    # Brevhuvudet: datumet står ofta uppe till höger utan etikett.
    for rad in header.splitlines():
        if _DATE_EXCLUDE.search(rad):
            continue
        träffar = _dates_in_line(rad)
        if träffar:
            return träffar[0], "brevhuvud", kandidater

    # Filnamnet, t.ex. "2025-03-14 faktura.pdf"
    if filename:
        träffar = _dates_in_line(filename)
        if träffar:
            kandidater.append((träffar[0], "filnamn"))
            return träffar[0], "filnamn", kandidater

    # Sista utväg: äldsta rimliga datumet. Ett dokument skrivs en gång,
    # men kan nämna senare datum i löptexten.
    riktiga = [d for d, k in kandidater if k != "förfallodatum (ej vald)"]
    if riktiga:
        return min(riktiga), "text", kandidater
    return None, "", kandidater


def _sender_lines(text: str, max_lines: int = 6) -> List[str]:
    """De första raderna som ser ut som ett avsändarnamn.

    Tar bara rader innan dokumenttypen ("Offert", "Faktura") dyker upp -
    det som står ovanför är brevhuvudet.
    """
    out: List[str] = []
    for raw in text.splitlines()[:8]:
        line = raw.strip(" .,:;|-•·")
        low = normalize(line)
        if not low:
            continue
        # Dokumenttyp, adress eller identifierare nådd - brevhuvudet är slut
        first = low.split()[0]
        if (low in STOPWORDS or first in _DOC_TYPE_WORDS
                or _ADDRESS_HINT.search(low) or _ID_HINT.search(low)):
            break
        if _NOT_A_NAME.match(line):
            continue
        # Avdelarrader och OCR-brus ("Le] = =")
        letters = sum(ch.isalpha() for ch in line)
        if letters < 4 or letters / max(1, len(line)) < 0.55:
            continue
        if all(w in STOPWORDS for w in low.split()):
            continue
        # Slogan/tjänsteuppräkning, inte ett firmanamn
        if len(_SLOGAN_SEP.findall(line)) >= 2:
            continue
        if len(line.split()) > 6:
            continue
        # På tvåspaltiga sidor hamnar högerspaltens "FAKTURA 4471" på
        # samma rad som firmanamnet. Klipp där dokumenttypen börjar, så
        # att stödordet blir "Pilkington Sverige AB" och inte
        # "Pilkington Sverige AB FAKTURA 4471".
        ord_ = line.split()
        for i, w in enumerate(ord_):
            if i and normalize(w).strip(":.,") in _DOC_TYPE_WORDS:
                line = " ".join(ord_[:i]).rstrip(" ,:;-")
                break
        if not line or len(line) < 3:
            continue
        out.append(line)
        if len(out) >= max_lines:
            break
    return out


def _head_of(text: str, lines: int = 15) -> str:
    """Brevhuvudet - där avsändaren nästan alltid står."""
    return "\n".join(text.splitlines()[:lines])


#: Rader som inleder mottagarblocket. Allt därefter handlar om KUNDEN,
#: inte om avsändaren, och ska därför inte styra vilken mapp filen hamnar i.
_RECIPIENT_MARKERS = (
    "leveransadress", "fakturaadress", "faktureringsadress", "leveransadr",
    "kundadress", "mottagare", "till:", "levereras till", "faktureras till",
    "deliver to", "bill to", "ship to", "sold to", "invoice to",
    "kundnr", "kundnummer", "er referens", "ert referensnr", "ert ordernr",
    # "Kund: Byggforvaltningen" är ett mottagarblock lika mycket som
    # "Kundadress". Utan de här hamnar kundens namn bland förslagen och
    # kan rankas över avsändarens.
    "kund:", "bestallare", "beställare", "bestallare:", "kopare", "köpare",
    "customer:", "buyer:", "client:",
)


#: Markörer som ensamma inleder ett mottagarblock. Övriga i
#: _RECIPIENT_MARKERS ("ert ordernr", "er referens") kan stå mitt i
#: avsändarens egen rad - "Tel 035-15 30 00  Ert ordernr: BEST-2025-0891" -
#: och får bara inleda zonen när de står först på raden.
_STRONG_RECIPIENT = (
    "leveransadress", "fakturaadress", "faktureringsadress", "leveransadr",
    "kundadress", "mottagare", "levereras till", "faktureras till",
    "deliver to", "bill to", "ship to", "sold to", "invoice to",
    "kund:", "bestallare", "beställare", "kopare", "köpare",
)


def _recipient_zone(text: str) -> str:
    """Texten från mottagarblockets början och 8 rader framåt.

    Blocket börjar vid den första *starka* markören, eller vid en svagare
    markör som står först på sin rad. Utan den skillnaden räknas
    avsändarens kontaktrad som mottagarblock, och då nedvärderas
    leverantörens egna uppgifter till en tredjedel.
    """
    lines = text.splitlines()
    reserv = -1
    for i, line in enumerate(lines):
        low = normalize(line)
        if not low:
            continue
        if any(low.startswith(m) or f" {m}" in low for m in _STRONG_RECIPIENT):
            return normalize("\n".join(lines[i:i + 8]))
        if reserv < 0 and any(low.startswith(m) for m in _RECIPIENT_MARKERS):
            reserv = i
    if reserv >= 0:
        return normalize("\n".join(lines[reserv:reserv + 8]))
    return ""


def suggest_keywords(text: str, filename: str = "", limit: int = 10,
                     existing: Optional[Counter] = None) -> List[Candidate]:
    """Ta fram de N mest karakteristiska stödorden ur en fil.

    Deterministiskt och helt lokalt - ingen AI, inget nätverk.
    `existing` = Counter över stödord som redan används av kategorier;
    ord som redan används av flera kategorier rankas ner (de särskiljer inte).
    """
    existing = existing or Counter()
    text = text or ""
    head = _head_of(text)
    name_part = re.sub(r"[_\-.]+", " ", filename or "")
    hay = f"{name_part}\n{text}"
    # Normalisera EN gång och räkna tokens en gång (snabbhet/minne,
    # rond 4): tidigare normaliserades hela hay för varje kandidat.
    norm_hay = normalize(hay)
    norm_tokens = Counter(_TOKEN_RE.findall(norm_hay))

    found: Dict[str, Candidate] = {}

    def add(raw: str, kind: str) -> None:
        raw = re.sub(r"\s+", " ", (raw or "").strip(" .,:;()[]{}\"'-"))
        if len(raw) < 3:
            return
        key = normalize(raw)
        if not key or len(key) < 3:
            return
        if kind in ("word", "phrase", "caps", "company", "sender"):
            parts = key.split()
            if all(p in STOPWORDS for p in parts):
                return
            if kind in ("word", "caps") and key in STOPWORDS:
                return
        prev = found.get(key)
        if prev is None:
            if " " in key:
                cnt = len(re.findall(re.escape(key), norm_hay)) or 1
            else:
                cnt = max(1, norm_tokens.get(key, 0))
            found[key] = Candidate(key, raw, kind, cnt, 0.0)
        else:
            # behåll den starkaste typen
            if KIND_INFO.get(kind, (0,))[0] > KIND_INFO.get(prev.kind, (0,))[0]:
                prev.kind, prev.display = kind, raw

    # -- starka identifierare ------------------------------------------
    for m in _ORGNR.finditer(hay):
        raw = m.group(0)
        if _luhn_ok(m.group(1) + m.group(2)):
            add(raw, "orgnr")
        else:
            # Fel kontrollsiffra - troligen ett referens- eller kundnummer.
            # Fortfarande unikt nog att duga som stödord, men får inte
            # rankas som ett organisationsnummer.
            add(raw, "refnr")
    for m in _VATNR.finditer(hay):
        add(m.group(0), "vat")
    for m in _GIRO.finditer(hay):
        add(m.group(0), "giro")
    for m in _EMAIL.finditer(hay):
        dom = m.group(1).lower()
        if not any(dom.startswith(p) for p in ("gmail.", "hotmail.", "outlook.", "yahoo.", "icloud.")):
            add(dom, "domain")
    for m in _URL.finditer(hay):
        add(m.group(1).lower(), "domain")

    # -- företagsnamn ----------------------------------------------------
    for m in _COMPANY.finditer(hay):
        name = _strip_labels(m.group(1))
        if not name:
            continue
        add(f"{name} {m.group(2)}", "company")
        add(name, "caps")   # även utan bolagsändelse

    # -- företagsnamn utan bolagsändelse vid identitetsrad (rond 4) ------
    # "Pilkington Sverige" raden över "Org.nr 556033-9086" är nästan säkert
    # avsändaren, även utan AB. Tidigare fångades bara namn med bolagsändelse.
    lines = text.splitlines()
    for i, line in enumerate(lines[:60]):
        if not _ID_HINT.search(normalize(line)):
            continue
        for j in (i, i - 1, i - 2):
            if not (0 <= j < len(lines)):
                continue
            cand_line = lines[j].strip()
            m = _COMPANY.search(cand_line) or _ALLCAPS.search(cand_line)
            if m:
                name = _strip_labels(m.group(1))
                if name and len(name) >= 4 and normalize(name) not in STOPWORDS:
                    add(name, "company")
                break
            # Titelfallsrad utan bolagsändelse: 1-4 ord, versalstart, inga
            # siffror, ingen adress - t.ex. "Pilkington Sverige".
            words = cand_line.split()
            if (1 <= len(words) <= 4 and not re.search(r"\d", cand_line)
                    and not _ADDRESS_HINT.search(cand_line)
                    and normalize(cand_line) not in STOPWORDS
                    and sum(1 for w in words if w[:1].isupper())
                    >= max(1, len(words) - 1)):
                add(cand_line, "company")
                break

    # -- versalord (logotyper, brevhuvud) --------------------------------
    for m in _ALLCAPS.finditer(hay):
        namn = m.group(1)
        # Ett versalord som redan ingår i ett hittat företagsnamn tillför
        # inget eget - "PILKINGTON" när "Pilkington Sverige AB" finns.
        add(namn, "caps")

    # -- produkt- och egennamn i löptexten -------------------------------
    # "Leverans av Optifloat Clear 4mm samt Suncool 70/40" - de här orden
    # nämns ofta bara en gång, men de är starkt knutna till en viss
    # leverantör. Utan dem föreslås bara generiska ord som "planglas".
    for m in _PROPER.finditer(text):
        namn = m.group(1).strip()
        if normalize(namn) not in STOPWORDS:
            add(namn, "proper")

    # -- avsändarens namn högst upp --------------------------------------
    # Många firmor saknar bolagsändelse i logotypen ("Laxå Glasmästeri").
    # De första raderna i brevhuvudet är nästan alltid avsändaren, så de
    # plockas upp även om ingen annan regel matchar dem.
    # Enbart sidtexten - filnamnet ligger sist i `text` och ska inte
    # kunna förväxlas med en rad i brevhuvudet.
    sender = _sender_lines(text)
    for i, line in enumerate(sender):
        # Rad 1 är firmanamnet. Raderna under är nästan alltid adress eller
        # slogan - de duger som stödord men ska inte tävla om mappnamnet.
        add(line, "sender" if i == 0 else "phrase")

    # -- vanliga ord och fraser ------------------------------------------
    # Bara sidtexten. Filnamnet ligger sist i `text` via combined, och ett
    # filnamn som "riktig.pdf" eller "scan0001" ger annars ett stödord som
    # bara matchar den enda fil det kom ifrån.
    words = [w.group(0) for w in _WORD.finditer(text)]
    norm_words = [normalize(w) for w in words]
    filnamnsdelar = {normalize(w) for w in _WORD.findall(name_part)}
    freq = Counter(w for w in norm_words
                   if w not in STOPWORDS and len(w) >= 4
                   and w not in filnamnsdelar)
    for word, cnt in freq.most_common(60):
        # Ett ord som bara nämns en gång måste vara ovanligt för att duga.
        # Gränsen låg på 8 tecken, vilket missade "suncool" och "planar" -
        # korta varumärken är just den sorts ord som särskiljer bäst.
        if cnt >= 2 or len(word) >= 6:
            add(word, "word")

    for i in range(len(norm_words) - 1):
        a, b = norm_words[i], norm_words[i + 1]
        if a in STOPWORDS or b in STOPWORDS or len(a) < 3 or len(b) < 3:
            continue
        add(f"{words[i]} {words[i+1]}", "phrase")

    # -- poängsättning ----------------------------------------------------
    norm_head = normalize(head)
    norm_recipient = _recipient_zone(text)
    # Rad 1 i brevhuvudet är nästan alltid själva firmanamnet
    first_sender = normalize(sender[0]) if sender else ""
    norm_name = normalize(name_part)
    for cand in found.values():
        base, _ = KIND_INFO.get(cand.kind, (1.0, ""))
        score = base * (1.0 + min(cand.count, 8) * 0.28)
        if cand.text in norm_head:
            score *= 1.6                     # står i brevhuvudet
        if first_sender and cand.text == first_sender:
            score *= 1.4                     # allra översta raden
        if norm_recipient and cand.text in norm_recipient and cand.text not in norm_head:
            # Står bara i mottagarblocket - det är kunden, inte avsändaren.
            # Utan detta sorteras alla fakturor efter mottagaren i stället
            # för efter leverantören.
            score *= 0.35
        if cand.text in norm_name:
            score *= 1.8                     # står i filnamnet
        if _DATEISH.match(cand.text) and cand.kind not in ("orgnr", "vat", "giro"):
            score *= 0.25                    # rena datum/belopp
        owners = existing.get(cand.text, 0)
        if owners == 1:
            score *= 0.7
        elif owners >= 2:
            score *= 0.25                    # särskiljer inte längre
        if cand.kind == "phrase" and cand.count < 2:
            score *= 0.6
        cand.score = score

    # -- rensa bort delsträngar av starkare kandidater --------------------
    ranked = sorted(found.values(), key=lambda c: (-c.score, c.text))
    kept: List[Candidate] = []
    for cand in ranked:
        if any(cand.text != k.text and cand.text in k.text and cand.score < k.score * 1.3
               for k in kept):
            continue
        kept.append(cand)
        if len(kept) >= limit:
            break
    return kept


def guess_category_name(candidates: List[Candidate]) -> str:
    """Gissa ett mappnamn ur de starkaste kandidaterna.

    Företagsnamn går före versalord, som går före domäner. Dokumenttyper
    ("Ritning"), rena koder ("A2-114") och stoppord hoppas över - en mapp
    ska heta "Pilkington", inte "Ritning".
    """
    def pretty(raw: str) -> str:
        words = []
        for w in raw.strip().split():
            up = w.upper()
            if up in ("AB", "AS", "ASA", "LTD", "LLC", "INC", "BV", "NV",
                      "SA", "KB", "HB", "OY", "AG", "APS", "A/S"):
                words.append(up)
            elif up == "GMBH":
                words.append("GmbH")
            elif w.isupper() and len(w) > 1:
                # "SAINT-GOBAIN" -> "Saint-Gobain", inte "Saint-gobain"
                words.append("-".join(part.capitalize() for part in w.split("-")))
            else:
                words.append(w)
        return " ".join(words)

    def usable(cand: Candidate) -> bool:
        parts = cand.text.split()
        if len(cand.text) < 3 or not parts:
            return False
        # Alla orden generiska, eller inleds med en dokumenttyp
        # ("Ritning A2-114") - då är det inget bra mappnamn.
        if all(part in STOPWORDS for part in parts) or parts[0] in STOPWORDS:
            return False
        # Namn som bara är en dokumentkod plus generiska ord
        if all(p in STOPWORDS or _looks_like_code(p) for p in parts):
            return False
        return not _looks_like_code(cand.text)

    # 1. Starka typer i prioritetsordning
    for kind in ("sender", "company", "caps", "domain"):
        same = [c for c in candidates if c.kind == kind and usable(c)]
        if not same:
            continue
        if kind == "sender":
            # Avsändarrader är redan rankade efter position i brevhuvudet -
            # rad 1 är firmanamnet. Låt poängen avgöra.
            best = max(same, key=lambda c: c.score)
        else:
            # Inom övriga typer vinner det längsta namnet - "SAINT-GOBAIN
            # GLASS" är mer beskrivande än bara "GLASS".
            best = max(same, key=lambda c: (len(c.text.split()), c.score))
        if kind == "domain":
            return best.display.split(".")[0].capitalize()
        return pretty(best.display)

    # 2. Annars högst rankade dugliga kandidaten
    for cand in candidates:
        if usable(cand) and cand.kind != "phrase":
            return pretty(cand.display).capitalize()
    return ""

# ==========================================================================
# FRISTÅENDE KÖRNING
# ==========================================================================

def _describe(path: Path, show_text: bool = False,
              limit: int = 10) -> Dict[str, Any]:
    """Läs en fil och returnera det viktigaste, för utskrift eller JSON."""
    ext = extract(path)
    cands = suggest_keywords(ext.combined, path.name, limit=limit)
    return {
        "file": str(path),
        "pages": ext.page_count,
        "pages_read": ext.pages_read,
        "chars": len(ext.text),
        "used_ocr": ext.used_ocr,
        "ocr_logo": ext.ocr_logo,
        "error": ext.error,
        "page_header": ext.page_header[:200],
        "page_footer": ext.page_footer[:200],
        "guess": guess_category_name(cands),
        "keywords": [
            {"text": c.text, "display": c.display, "kind": c.kind,
             "label": c.label, "count": c.count, "score": round(c.score, 2)}
            for c in cands
        ],
        "text": ext.text if show_text else "",
    }


def _print_report(info: Dict[str, Any], show_text: bool) -> None:
    print(f"\n{'=' * 68}\n{Path(info['file']).name}\n{'-' * 68}")
    läst = "OCR" if info["used_ocr"] else "textlager"
    if info["ocr_logo"]:
        läst += " + OCR av logotypen"
    print(f"  Sidor:      {info['pages_read']} av {info['pages']}")
    print(f"  Tecken:     {info['chars']}  ({läst})")
    if info["error"]:
        print(f"  Fel:        {info['error']}")
    if info["page_header"]:
        print(f"  Sidhuvud:   {info['page_header'][:60]}")
    if info["page_footer"]:
        print(f"  Sidfot:     {info['page_footer'][:60]}")
    print(f"  Gissad mapp: {info['guess'] or '-'}")
    if info["keywords"]:
        print("\n  Föreslagna stödord:")
        for k in info["keywords"]:
            print(f"    {k['display'][:34]:36s} {k['label']:24s} {k['score']:6.2f}")
    if show_text:
        print(f"\n  Text:\n{'-' * 68}")
        print(info["text"])


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="pdfsorter_read",
        description="Läs PDF-filer och visa vad ArkivPiloten ser i dem.")
    p.add_argument("files", nargs="*", help="PDF-filer att undersöka")
    p.add_argument("--text", action="store_true", help="Skriv ut hela texten")
    p.add_argument("--json", action="store_true", help="Skriv resultatet som JSON")
    p.add_argument("--limit", type=int, default=10, help="Antal stödord (10)")
    p.add_argument("--check", action="store_true",
                   help="Visa vilka PDF-motorer som hittats")
    args = p.parse_args(argv)

    if args.check or not args.files:
        print("ArkivPiloten - läsmodul")
        print(f"  {status_text()}")
        for k, v in backend_status().items():
            print(f"    {k:16s} {'ja' if v else 'nej'}")
        if not args.files:
            print("\nAnvändning:  python pdfsorter_read.py FIL.pdf [--text] [--json]")
        return 0

    results = []
    for name in args.files:
        path = Path(name)
        if not path.is_file():
            print(f"Hittar inte: {path}", file=sys.stderr)
            continue
        try:
            info = _describe(path, args.text, args.limit)
        except Exception as exc:                    # noqa: BLE001
            print(f"{path.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        results.append(info)
        if not args.json:
            _print_report(info, args.text)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
