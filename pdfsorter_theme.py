#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utseendet i ArkivPiloten - färger, typsnitt och ttk-stilar.

Den här modulen bestämmer hur appen ser ut. Den vet ingenting om
PDF-filer, matchning eller inställningar: den tar emot ett Tk-fönster och
returnerar färdiga stilar. Därför går den att ändra i helt fritt utan
risk för att sorteringen påverkas.

Vill du byta färgtema räcker det att ändra i `COLORS` här.

Fristående körning visar en provkarta med alla stilar:

    python pdfsorter_theme.py

Saknas filen startar appen ändå, med Tkinters gråa standardutseende.
"""

from __future__ import annotations

from collections import OrderedDict
import sys

from typing import Any, Dict, Tuple

#: Programmets version. Höjs vid varje leverans.
VERSION = "1.4.15"


#: Färgpalett. Ljus, sval grundton med en tydlig blå accent. Alla färger
#: ligger här så att utseendet kan ändras på ett ställe i stället för att
#: vara utspritt i hundratals widgetanrop.
COLORS: Dict[str, str] = {
    # ytor
    "bg":            "#eef1f6",   # fönsterbakgrund, något blåtonad
    "surface":       "#ffffff",   # kort, listor, fält
    "surface_alt":   "#f7f9fc",   # varannan rad i tabeller
    "surface_sunk":  "#e7ebf2",   # nedsänkt yta, t.ex. loggens ram
    # linjer
    "border":        "#dde3ec",
    "border_strong": "#c3ccdb",
    # text
    "text":          "#16202e",
    "text_muted":    "#5d6b7f",
    "text_faint":    "#94a1b4",
    "text_invert":   "#ffffff",
    # accent
    "accent":        "#2563c7",
    "accent_dark":   "#1b4a9c",
    "accent_light":  "#e4edfc",
    "accent_hair":   "#c9dcf8",
    # status
    "ok":            "#12703a",
    "ok_light":      "#e3f5ea",
    "warn":          "#8a5a00",
    "warn_light":    "#fdf3e0",
    "err":           "#a91d13",
    "err_light":     "#fdeceb",
    # kromdetaljer
    "header_bg":     "#eaeff7",   # tabellhuvuden
    "shadow":        "#d6dce7",   # falsk skugga under kort
}


#: Mörk palett med exakt samma nycklar som COLORS, så att varje stil och
#: varje widget som fungerar i ljust läge också fungerar i mörkt. Accenter
#: och statusfärger är ljusare varianter som bär mot mörk botten, och de
#: "_light"-nycklar som i ljust läge är bleka pill-ytor blir här mörkt
#: tonade ytor med ljus text.
COLORS_DARK: Dict[str, str] = {
    # ytor
    "bg":            "#171b21",
    "surface":       "#20262e",
    "surface_alt":   "#252c35",
    "surface_sunk":  "#12161b",
    # linjer
    "border":        "#323b47",
    "border_strong": "#48525f",
    # text
    "text":          "#e8ecf1",
    "text_muted":    "#9aa7b6",
    "text_faint":    "#68737f",
    "text_invert":   "#ffffff",
    # accent
    "accent":        "#4d8fe8",
    "accent_dark":   "#82b3f2",   # ljusare - används som text på mörk botten
    "accent_light":  "#24344d",   # tonad yta för hover/piller
    "accent_hair":   "#2c3f5e",
    # status
    "ok":            "#4cc38a",
    "ok_light":      "#1d332a",
    "warn":          "#e0a63f",
    "warn_light":    "#3a2f1a",
    "err":           "#e5726a",
    "err_light":     "#3b2220",
    # kromdetaljer
    "header_bg":     "#1b2128",
    "shadow":        "#0d1014",
}

#: Högkontrastpalett (rond 3): svart/vitt med gul accent - WCAG 7:1 för
#: brödtext. Väljs via Theme(..., contrast="high"); tänkt för synsvaga och
#: starkt solljus. Alla nycklar samma som COLORS så att varje stil fungerar.
COLORS_HC: Dict[str, str] = {
    "bg":            "#000000",
    "surface":       "#0a0a0a",
    "surface_alt":   "#161616",
    "surface_sunk":  "#000000",
    "border":        "#ffffff",
    "border_strong": "#ffffff",
    "text":          "#ffffff",
    "text_muted":    "#e6e6e6",
    "text_faint":    "#c0c0c0",
    "text_invert":   "#000000",
    "accent":        "#ffd400",
    "accent_dark":   "#ffe95c",
    "accent_light":  "#332b00",
    "accent_hair":   "#665800",
    "ok":            "#00e676",
    "ok_light":      "#00331a",
    "warn":          "#ffab00",
    "warn_light":    "#332200",
    "err":           "#ff5252",
    "err_light":     "#330000",
    "header_bg":     "#1a1a1a",
    "shadow":        "#000000",
}


# ==========================================================================
# KONTRAST-KONTROLL (WCAG) - design-QA och färgblindssäkerhet
# ==========================================================================

def _lum(hexv: str) -> float:
    """Relativ luminans enligt WCAG."""
    def c8(v: int) -> float:
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * c8(r) + 0.7152 * c8(g) + 0.0722 * c8(b)


def contrast_ratio(a: str, b: str) -> float:
    """Kontrastförhållande 1–21 mellan två #rrggbb-färger."""
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


#: Par som ska klara 4,5:1 (normal text) respektive 3:1 (större/fet text
#: som knappar och piller).
_AUDIT_NORMAL = (("text", "bg"), ("text", "surface"),
                 ("text_muted", "bg"), ("text_muted", "surface"),
                 ("ok", "surface"), ("warn", "surface"), ("err", "surface"))
_AUDIT_LARGE = (("text_invert", "accent"),)

#: Memo: paletterna är modulkonstanter, revisionen behöver räknas en gång.
_AUDIT_CACHE: Dict[int, list] = {}


def dark_titlebar(win, dark: bool) -> None:
    """Mörk titellist på Windows 10+ när mörkt tema är valt - samma
    moderna känsla som appens egna ytor (ANVÄNDARORDER 2026-10-06).
    Ofarlig no-op på andra plattformar/fel."""
    try:
        if not sys.platform.startswith("win"):
            return
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        if not hwnd:
            return
        v = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        pass


def audit_palette(p: Dict[str, str]) -> list:
    """Returnerar par som inte når WCAG-kravet - tom lista = godkänd
    palett. Körs i tester och i provkartan; båda paletterna ska alltid
    klara sina trösklar (design: läsbarhet även för färgblinda)."""
    hit = _AUDIT_CACHE.get(id(p))
    if hit is not None:
        return hit
    bad = []
    for fg, bg in _AUDIT_NORMAL:
        if contrast_ratio(p[fg], p[bg]) < 4.5:
            bad.append((fg, bg, round(contrast_ratio(p[fg], p[bg]), 2)))
    for fg, bg in _AUDIT_LARGE:
        if contrast_ratio(p[fg], p[bg]) < 3.0:
            bad.append((fg, bg, round(contrast_ratio(p[fg], p[bg]), 2)))
    _AUDIT_CACHE[id(p)] = bad
    return bad


#: Cache över typsnittsfamiljer per fönster (snabbhet, rond 3).
_FAMILIES_CACHE: Dict[int, set] = {}


def _pick_font(root, candidates: Tuple[str, ...], size: int,
               weight: str = "normal") -> Tuple[str, int, str]:
    """Välj det första teckensnittet som faktiskt finns på datorn.

    Familjelistan cachas per fönster (snabbhet): tkfont.families() är en
    systemfråga som inte behöver upprepas för varje typsnittsstorlek.
    """
    try:
        from tkinter import font as tkfont
        fams = _FAMILIES_CACHE.get(id(root))
        if fams is None:
            fams = {f.lower() for f in tkfont.families(root)}
            _FAMILIES_CACHE[id(root)] = fams
            while len(_FAMILIES_CACHE) > 4:
                _FAMILIES_CACHE.pop(next(iter(_FAMILIES_CACHE)))
        for name in candidates:
            if name.lower() in fams:
                return (name, size, weight)
    except Exception:
        pass
    return ("TkDefaultFont", size, weight)


#: Cache över skalade vektorikoner så att temabyten och uppdateringar
#: aldrig behöver rita om identiska PNG-lager i onödan.
_NAV_ICON_CACHE: "OrderedDict[Tuple[str, str, str, str, int], Any]" = OrderedDict()
_ACTION_ICON_CACHE: "OrderedDict[Tuple[str, str, str, int], Any]" = OrderedDict()


def display_dpi(root: Any) -> float:
    """Läs skärmens verkliga pixeltäthet (DPI), även när X11 fastnar på 96."""
    try:
        dpi = float(root.winfo_fpixels("1i"))
    except Exception:
        dpi = 96.0
    if dpi <= 0.0:
        dpi = 96.0
    if dpi <= 96.5:
        try:
            screen_w = int(root.winfo_screenwidth())
            mm_w = int(root.winfo_screenmmwidth())
            if 100 <= mm_w <= 2000 and screen_w >= 1920:
                phys = screen_w / (mm_w / 25.4)
                if 110.0 <= phys <= 288.0:
                    dpi = round(phys, 1)
        except Exception:
            pass
    return max(72.0, min(288.0, dpi))


def window_dpi(widget: Any) -> float:
    """Läs aktuell skärm-DPI för just detta fönster (Per-Monitor v2 på Windows)."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            hwnd = int(widget.winfo_id())
            if hwnd:
                dpi_val = int(ctypes.windll.user32.GetDpiForWindow(hwnd))
                if 72 <= dpi_val <= 384:
                    return float(dpi_val)
        except Exception:
            pass
    return display_dpi(widget)


def calibrate_tk_scaling(root: Any, dpi: float | None = None,
                         *, allow_down: bool = False) -> float:
    """Synka Tk:s inbyggda punkt-till-pixel-skala med skärmens DPI."""
    if dpi is None:
        dpi = display_dpi(root)
    target = max(1.0, float(dpi) / 72.0)
    try:
        tk_obj = getattr(root, "tk", None)
        if tk_obj is not None:
            current = float(tk_obj.call("tk", "scaling"))
            if abs(current - target) > 0.08 and (allow_down or target > current):
                tk_obj.call("tk", "scaling", target)
                return target
            return current
    except Exception:
        pass
    return target


def navigation_icon_image(kind: str, palette: Dict[str, str], size: int = 20):
    """Rita en liten, skalbar ikon till huvudflikarna.

    Ikonerna använder samma accent- och ytfärger som temat och ritas i hög
    upplösning (4× översampling + skärpa) för att hålla sig skarpa även på
    4K/HiDPI-skärmar. Pillow är valfritt här: utan det returneras ``None``
    och flikarna visar vanlig text.
    """
    try:
        from PIL import Image, ImageDraw, ImageEnhance

        size = max(16, min(64, int(size)))
        accent = palette["accent"]
        bg = palette["accent_light"]
        outline = palette["accent_hair"]
        cache_key = (str(kind), accent, bg, outline, size)
        cached = _NAV_ICON_CACHE.get(cache_key)
        if cached is not None:
            _NAV_ICON_CACHE.move_to_end(cache_key)
            return cached.copy()

        scale = 4
        side = size * scale
        unit = side / 24.0
        image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        def xy(x, y):
            return (round(x * unit), round(y * unit))

        width = max(1, round(1.8 * unit))
        draw.rounded_rectangle(
            (xy(1.2, 1.2), xy(22.8, 22.8)), radius=round(5 * unit),
            fill=bg, outline=outline, width=max(1, round(0.8 * unit)))

        def line(points, fill=accent, stroke=width):
            draw.line([xy(x, y) for x, y in points], fill=fill,
                      width=stroke, joint="curve")

        def rect(box, radius=1.0, fill=None, stroke=width):
            draw.rounded_rectangle(
                (xy(box[0], box[1]), xy(box[2], box[3])),
                radius=round(radius * unit), fill=fill,
                outline=accent if fill is None else None,
                width=stroke if fill is None else 1)

        if kind == "start":
            draw.polygon(
                [xy(12, 4.4), xy(19.6, 10.8), xy(17.5, 10.8),
                 xy(17.5, 19.2), xy(6.5, 19.2), xy(6.5, 10.8), xy(4.4, 10.8)],
                fill=accent,
            )
            rect((10.2, 13.4, 13.8, 19.3), radius=0.8, fill=bg)
        elif kind == "review":
            rect((5.2, 4.2, 16.4, 19.2), radius=1.8, fill=accent)
            line(((8.0, 8.4), (13.6, 8.4)), fill=bg, stroke=max(1, round(1.5 * unit)))
            line(((8.0, 11.6), (12.2, 11.6)), fill=bg, stroke=max(1, round(1.5 * unit)))
            cx, cy = xy(16.6, 16.6)
            r = 4.2 * unit
            draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                         fill=bg, outline=accent, width=max(1, round(1.6 * unit)))
            line(((14.8, 16.7), (16.1, 18.0), (18.7, 15.0)),
                 stroke=max(1, round(1.9 * unit)))
        elif kind == "categories":
            draw.polygon(
                [xy(4.5, 6.2), xy(10.2, 6.2), xy(11.8, 8.2), xy(19.5, 8.2),
                 xy(19.5, 10.5), xy(4.5, 10.5)],
                fill=accent,
            )
            rect((4.5, 9.2, 19.5, 18.8), radius=1.8, fill=accent)
            line(((6.8, 11.2), (17.2, 11.2)), fill=bg, stroke=max(1, round(1.2 * unit)))
        elif kind == "settings":
            for y, x in ((7, 8.5), (12, 15.5), (17, 9.5)):
                line(((4.8, y), (19.2, y)), stroke=max(1, round(1.7 * unit)))
                r = 2.0 * unit
                cx, cy = xy(x, y)
                draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                             fill=accent, outline=bg, width=max(1, round(0.9 * unit)))
        elif kind == "history":
            draw.ellipse((xy(4.6, 4.6), xy(19.4, 19.4)),
                         outline=accent, width=max(1, round(2.0 * unit)))
            line(((12, 7.2), (12, 12.2), (15.8, 14.4)),
                 stroke=max(1, round(2.0 * unit)))
            draw.polygon([xy(4.5, 8.8), xy(7.4, 6.2), xy(7.6, 9.8)], fill=accent)
        elif kind == "help":
            draw.ellipse((xy(4.4, 4.4), xy(19.6, 19.6)), fill=accent)
            line(((9.6, 9.4), (10.8, 7.6), (13.4, 7.6), (14.6, 9.3),
                  (13.8, 11.0), (12.0, 12.2), (12.0, 14.0)),
                 fill=bg, stroke=max(1, round(1.9 * unit)))
            cx, cy = xy(12, 16.9)
            r = 1.05 * unit
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=bg)
        elif kind == "advanced":
            line(((9.2, 6.6), (6.8, 6.6), (6.8, 10.8), (5.2, 12.0),
                  (6.8, 13.2), (6.8, 17.4), (9.2, 17.4)),
                 stroke=max(1, round(1.9 * unit)))
            line(((14.8, 6.6), (17.2, 6.6), (17.2, 10.8), (18.8, 12.0),
                  (17.2, 13.2), (17.2, 17.4), (14.8, 17.4)),
                 stroke=max(1, round(1.9 * unit)))
            line(((10.8, 16.6), (13.2, 7.4)), stroke=max(1, round(1.7 * unit)))
        else:
            return None

        resampling = getattr(Image, "Resampling", Image)
        out = image.resize((size, size), resampling.LANCZOS)
        out = ImageEnhance.Sharpness(out).enhance(1.15)
        _NAV_ICON_CACHE[cache_key] = out
        while len(_NAV_ICON_CACHE) > 48:
            _NAV_ICON_CACHE.popitem(last=False)
        return out.copy()
    except Exception:
        return None


MICRO_ICON_SVGS: Dict[str, str] = {
    "sort": '<polygon points="6.5,4.8 18.5,12 6.5,19.2" fill="currentColor"/>',
    "watch": '<path d="M2.8,12 C5.6,6.8 18.4,6.8 21.2,12 C18.4,17.2 5.6,17.2 2.8,12 Z"/><circle cx="12" cy="12" r="2.8" fill="currentColor"/>',
    "folder": '<path d="M3.5,6.5 H9.8 L11.5,8.8 H20.5 V18.5 H3.5 Z" rx="1.5"/>',
    "folder_clean": '<path d="M3.5,6.5 H9.8 L11.5,8.8 H20.5 V18.5 H3.5 Z"/><polyline points="8.8,13.6 11.2,16.0 15.6,11.6"/>',
    "search": '<circle cx="10.2" cy="10.2" r="5.8"/><line x1="14.5" y1="14.5" x2="20" y2="20"/>',
    "audit": '<path d="M12,3.2 L19.4,6.4 V12.4 C19.4,16.5 16.2,19.6 12,21 C7.8,19.6 4.6,16.5 4.6,12.4 V6.4 Z"/><polyline points="8.6,12.0 11.0,14.5 15.8,9.4"/>',
    "add": '<line x1="12" y1="4.8" x2="12" y2="19.2"/><line x1="4.8" y1="12" x2="19.2" y2="12"/>',
    "refresh": '<path d="M19.2,8.8 A7.5,7.5 0 1 0 19.3,14.5"/><polygon points="20.4,3.8 20.4,10.2 14.2,9.2" fill="currentColor" stroke="none"/>',
    "help": '<circle cx="12" cy="12" r="8.4"/><path d="M9.6,9.4 C9.9,7.9 11.0,7.2 12.2,7.2 C13.6,7.2 14.6,8.1 14.6,9.4 C14.6,10.7 13.4,11.4 12.0,12.3 V14.2"/><circle cx="12" cy="17.2" r="1.0" fill="currentColor" stroke="none"/>',
    "review": '<rect x="4.5" y="3.8" width="11.5" height="16.4" rx="1.8"/><line x1="7.8" y1="8.5" x2="13.0" y2="8.5"/><line x1="7.8" y1="11.8" x2="11.6" y2="11.8"/><polyline points="12.5,16.2 14.4,18.2 19.6,12.6"/>',
    "ocr": '<polyline points="4,8.5 4,4.2 8.5,4.2"/><polyline points="15.5,4.2 20,4.2 20,8.5"/><polyline points="4,15.5 4,19.8 8.5,19.8"/><polyline points="15.5,19.8 20,19.8 20,15.5"/><line x1="7" y1="10" x2="17" y2="10"/><line x1="7" y1="14" x2="14.5" y2="14"/>',
    "pdf_text": '<path d="M6,3.5 H14.5 L18.5,7.5 V20.5 H6 Z"/><polyline points="14.2,3.5 14.2,7.8 18.5,7.8"/><line x1="8.8" y1="11.5" x2="15.4" y2="11.5"/><line x1="8.8" y1="15.0" x2="13.6" y2="15.0"/>',
    "status_ok": '<circle cx="12" cy="12" r="8.4"/><polyline points="8.4,12.2 11.0,14.8 16.0,9.4"/>',
    "status_warn": '<polygon points="12,3.6 20.8,19.4 3.2,19.4"/><line x1="12" y1="9.2" x2="12" y2="14.2"/><circle cx="12" cy="16.9" r="0.9" fill="currentColor" stroke="none"/>',
    "status_err": '<circle cx="12" cy="12" r="8.4"/><line x1="8.8" y1="8.8" x2="15.2" y2="15.2"/><line x1="15.2" y1="8.8" x2="8.8" y2="15.2"/>',
    "status_idle": '<circle cx="12" cy="12" r="5.2" fill="currentColor"/>',
    "status_active": '<circle cx="12" cy="12" r="8.0"/><circle cx="12" cy="12" r="3.8" fill="currentColor" stroke="none"/>',
    "jump": '<line x1="5.8" y1="18.2" x2="18.2" y2="5.8"/><polyline points="10.2,5.8 18.2,5.8 18.2,13.8"/>',
    "undo": '<polygon points="4.2,11.2 9.4,6.4 9.4,16.0" fill="currentColor" stroke="none"/><path d="M8.8,11.2 H15.0 C17.8,11.2 19.6,13.1 19.6,15.8 V18.2"/>',
    "export": '<path d="M4.8,14.2 V19.4 H19.2 V14.2"/><line x1="12" y1="4.2" x2="12" y2="14.2"/><polyline points="8.4,10.6 12,14.4 15.6,10.6"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>',
    "trash": '<line x1="4.4" y1="6.8" x2="19.6" y2="6.8"/><path d="M9.0,6.8 V4.2 H15.0 V6.8"/><path d="M6.4,6.8 L7.4,19.6 H16.6 L17.6,6.8"/><line x1="10.2" y1="10.2" x2="10.6" y2="16.4"/><line x1="13.8" y1="10.2" x2="13.4" y2="16.4"/>',
}


def micro_icon_svg(kind: str, color: str, *, size: int = 16,
                   bg: str = "") -> str:
    """Returnera skalbar SVG-definition för en vektor-mikroikon (24×24 viewBox)."""
    body = MICRO_ICON_SVGS.get(str(kind))
    if not body:
        return ""
    size = max(12, min(64, int(size)))
    bg_rect = (
        f'<rect x="0" y="0" width="24" height="24" rx="5" fill="{bg}"/>'
        if bg else ""
    )
    rendered = body.replace('fill="currentColor"', f'fill="{color}"')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" '
        f'height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'{bg_rect}{rendered}</svg>'
    )


def _tone_colors(palette: Dict[str, str], tone: str,
                 inverted: bool) -> Tuple[str, str]:
    if inverted:
        return palette["text_invert"], palette["accent"]
    tone_map = {
        "on_accent": (palette["text_invert"], palette["accent"]),
        "ok": (palette["ok"], palette["ok_light"]),
        "warn": (palette["warn"], palette["warn_light"]),
        "err": (palette["err"], palette["err_light"]),
        "muted": (palette["text_muted"], palette["surface_alt"]),
        "text": (palette["text"], palette["surface_alt"]),
    }
    return tone_map.get(tone, (palette["accent"], palette["accent_light"]))


def micro_icon_image(kind: str, palette: Dict[str, str], size: int = 16,
                     *, tone: str = "accent", inverted: bool = False):
    """Rendera en skarp SVG-baserad mikroikon skalad till aktuell bildstorlek."""
    if kind not in MICRO_ICON_SVGS:
        return None
    try:
        from PIL import Image, ImageDraw, ImageEnhance

        size = max(12, min(48, int(size)))
        fg, bg = _tone_colors(palette, tone, inverted)
        cache_key = (str(kind), fg, bg, size)
        cached = _ACTION_ICON_CACHE.get(cache_key)
        if cached is not None:
            _ACTION_ICON_CACHE.move_to_end(cache_key)
            return cached.copy()

        scale = 4
        side = size * scale
        unit = side / 24.0
        image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        width = max(1, round(2.0 * unit))

        def xy(x, y):
            return (round(x * unit), round(y * unit))

        def line(points, stroke=width):
            draw.line([xy(x, y) for x, y in points], fill=fg,
                      width=stroke, joint="curve")

        def dot(cx_u, cy_u, r_u, fill=fg, outline=None):
            cx, cy = xy(cx_u, cy_u)
            r = r_u * unit
            draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                         fill=fill, outline=outline, width=width)

        if kind == "sort":
            draw.polygon([xy(6.5, 4.8), xy(18.5, 12), xy(6.5, 19.2)], fill=fg)
        elif kind == "watch":
            draw.ellipse((xy(3.2, 6.8), xy(20.8, 17.2)), outline=fg, width=width)
            dot(12, 12, 2.8)
        elif kind == "folder":
            line(((3.5, 6.5), (9.8, 6.5), (11.5, 8.8), (20.5, 8.8),
                  (20.5, 18.5), (3.5, 18.5), (3.5, 6.5)))
            line(((5.5, 10.6), (18.5, 10.6)), stroke=max(1, round(1.3 * unit)))
        elif kind == "folder_clean":
            line(((3.5, 6.5), (9.8, 6.5), (11.5, 8.8), (20.5, 8.8),
                  (20.5, 18.5), (3.5, 18.5), (3.5, 6.5)))
            line(((8.8, 13.6), (11.2, 16.0), (15.6, 11.6)))
        elif kind == "search":
            draw.ellipse((xy(4.4, 4.4), xy(16.0, 16.0)), outline=fg, width=width)
            line(((14.5, 14.5), (20.0, 20.0)), stroke=max(1, round(2.5 * unit)))
        elif kind == "audit":
            line(((12, 3.2), (19.4, 6.4), (19.4, 12.6), (12, 20.8),
                  (4.6, 12.6), (4.6, 6.4), (12, 3.2)))
            line(((8.6, 12.0), (11.0, 14.5), (15.8, 9.4)))
        elif kind == "add":
            line(((12, 4.8), (12, 19.2)))
            line(((4.8, 12), (19.2, 12)))
        elif kind == "refresh":
            draw.arc((xy(4.5, 4.5), xy(19.5, 19.5)), 38, 322, fill=fg, width=width)
            draw.polygon([xy(20.4, 3.8), xy(20.4, 10.2), xy(14.2, 9.2)], fill=fg)
        elif kind == "help":
            draw.ellipse((xy(3.6, 3.6), xy(20.4, 20.4)), outline=fg, width=width)
            line(((9.6, 9.4), (10.8, 7.5), (13.4, 7.5), (14.6, 9.3),
                  (12.0, 12.3), (12.0, 14.2)))
            dot(12, 17.2, 0.95)
        elif kind == "review":
            draw.rounded_rectangle(
                (xy(4.5, 3.8), xy(16.0, 20.2)), radius=round(1.8 * unit),
                outline=fg, width=width)
            line(((7.8, 8.5), (13.0, 8.5)), stroke=max(1, round(1.6 * unit)))
            line(((7.8, 11.8), (11.6, 11.8)), stroke=max(1, round(1.6 * unit)))
            line(((12.5, 16.2), (14.4, 18.2), (19.6, 12.6)),
                 stroke=max(1, round(2.3 * unit)))
        elif kind == "ocr":
            line(((4, 8.5), (4, 4.2), (8.5, 4.2)))
            line(((15.5, 4.2), (20, 4.2), (20, 8.5)))
            line(((4, 15.5), (4, 19.8), (8.5, 19.8)))
            line(((15.5, 19.8), (20, 19.8), (20, 15.5)))
            line(((7, 10), (17, 10)), stroke=max(1, round(1.7 * unit)))
            line(((7, 14), (14.5, 14)), stroke=max(1, round(1.7 * unit)))
        elif kind == "pdf_text":
            line(((6, 3.5), (14.5, 3.5), (18.5, 7.5), (18.5, 20.5), (6, 20.5), (6, 3.5)))
            line(((14.2, 3.5), (14.2, 7.8), (18.5, 7.8)), stroke=max(1, round(1.5 * unit)))
            line(((8.8, 11.5), (15.4, 11.5)), stroke=max(1, round(1.7 * unit)))
            line(((8.8, 15.0), (13.6, 15.0)), stroke=max(1, round(1.7 * unit)))
        elif kind == "status_ok":
            draw.ellipse((xy(3.6, 3.6), xy(20.4, 20.4)), outline=fg, width=width)
            line(((8.4, 12.2), (11.0, 14.8), (16.0, 9.4)))
        elif kind == "status_warn":
            line(((12, 3.6), (20.8, 19.4), (3.2, 19.4), (12, 3.6)))
            line(((12, 9.2), (12, 14.2)))
            dot(12, 16.9, 0.9)
        elif kind == "status_err":
            draw.ellipse((xy(3.6, 3.6), xy(20.4, 20.4)), outline=fg, width=width)
            line(((8.8, 8.8), (15.2, 15.2)))
            line(((15.2, 8.8), (8.8, 15.2)))
        elif kind == "status_idle":
            dot(12, 12, 5.0, fill=fg)
        elif kind == "status_active":
            draw.ellipse((xy(4.0, 4.0), xy(20.0, 20.0)), outline=fg, width=width)
            dot(12, 12, 3.8, fill=fg)
        elif kind == "jump":
            line(((5.8, 18.2), (18.2, 5.8)))
            line(((10.2, 5.8), (18.2, 5.8), (18.2, 13.8)))
        elif kind == "undo":
            draw.polygon([xy(4.2, 11.2), xy(9.4, 6.4), xy(9.4, 16.0)], fill=fg)
            line(((8.8, 11.2), (16.2, 11.2), (19.2, 14.2), (19.2, 18.2)))
        elif kind == "export":
            line(((4.8, 14.2), (4.8, 19.4), (19.2, 19.4), (19.2, 14.2)))
            line(((12, 4.2), (12, 14.2)))
            line(((8.4, 10.6), (12, 14.4), (15.6, 10.6)))
        elif kind == "stop":
            draw.rounded_rectangle(
                (xy(6, 6), xy(18, 18)), radius=round(2.0 * unit),
                fill=fg)
        elif kind == "trash":
            line(((4.4, 6.8), (19.6, 6.8)))
            line(((9.0, 6.8), (9.0, 4.2), (15.0, 4.2), (15.0, 6.8)))
            line(((6.4, 6.8), (7.4, 19.6), (16.6, 19.6), (17.6, 6.8)))
            line(((10.2, 10.2), (10.6, 16.4)), stroke=max(1, round(1.4 * unit)))
            line(((13.8, 10.2), (13.4, 16.4)), stroke=max(1, round(1.4 * unit)))
        else:
            return None

        resampling = getattr(Image, "Resampling", Image)
        out = image.resize((size, size), resampling.LANCZOS)
        out = ImageEnhance.Sharpness(out).enhance(1.15)
        _ACTION_ICON_CACHE[cache_key] = out
        while len(_ACTION_ICON_CACHE) > 64:
            _ACTION_ICON_CACHE.popitem(last=False)
        return out.copy()
    except Exception:
        return None


def action_icon_image(kind: str, palette: Dict[str, str], size: int = 18,
                      inverted: bool = False):
    """Rita skarpa små vektorikoner för knappar och verktygsrader."""
    return micro_icon_image(
        kind, palette, size=max(14, min(48, int(size))),
        tone="accent", inverted=inverted)


class Theme:
    """Samlar färger, typsnitt och ttk-stilar på ett ställe.

    Tkinter ser förvalt ganska tråkigt ut, särskilt på Linux. Här byggs ett
    genomgående utseende: vita kort mot en svalt grå bakgrund, tydlig
    typografisk hierarki och en blå accentfärg reserverad för det som är
    viktigast på varje flik.
    """

    #: Standardavstånd i bildpunkter. Att gå via namn i stället för siffror
    #: gör att luften blir densamma på alla flikar.
    PAD = 12        # ytterkant mot fönstret
    GAP = 8         # mellan två kort
    INNER = 10      # inuti ett kort

    def __init__(self, root, ttk, dark: bool = False,
                 contrast: str = "normal", text_scale: float = 1.0,
                 dpi_override: float | None = None):
        self.root = root
        self.ttk = ttk
        self.dark = dark
        self.contrast = contrast
        self._micro_icon_refs: list = []
        try:
            self.text_scale = max(1.0, min(1.5, float(text_scale)))
        except (TypeError, ValueError):
            self.text_scale = 1.0
        if contrast == "high":
            self.c = COLORS_HC
        else:
            self.c = COLORS_DARK if dark else COLORS
        self.style = ttk.Style(root)

        # clam går att färgsätta fritt, till skillnad från de inbyggda
        # Windows- och macOS-temana. Priset är att vi ritar allt själva.
        for theme in ("clam", "alt", "default"):
            try:
                self.style.theme_use(theme)
                break
            except Exception:
                continue

        # HiDPI: känn av riktig pixeltäthet, synka Tk-skalning och skala både
        # typsnitt, ikoner och pixelavstånd mjukt även på 4K/5K-skärmar.
        if dpi_override is not None:
            dpi = max(72.0, min(288.0, float(dpi_override)))
            tk_scale = calibrate_tk_scaling(root, dpi, allow_down=True)
        else:
            dpi = window_dpi(root)
            tk_scale = calibrate_tk_scaling(root, dpi)
        if dpi >= 144:
            dpi_scale = min(1.85, round(1.25 + (dpi - 144.0) / 192.0, 2))
        elif dpi >= 120:
            dpi_scale = 1.1
        else:
            dpi_scale = 1.0
        self.dpi = dpi
        self.ui_scale = dpi_scale * self.text_scale
        self.pixel_scale = max(1.0, min(2.75, dpi / 96.0)) * self.text_scale
        self.PAD = self.px(12)
        self.GAP = self.px(8)
        self.INNER = self.px(10)

        # När OS/Tk redan skalar punktstorleken med DPI (t.ex. Per-Monitor v2
        # på Windows eller kalibrerad X11) undviker vi dubbel förstoring av
        # punktstorlekar och skalar bara efter användarens textval.
        tk_handles_dpi = (dpi > 105.0 and tk_scale >= (dpi / 72.0) * 0.92)
        font_scale = (self.text_scale if tk_handles_dpi else self.ui_scale)

        def _sz(n: int) -> int:
            return max(8, int(round(n * font_scale)))

        ui = ("Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text",
              "Helvetica Neue", "Cantarell", "Ubuntu", "DejaVu Sans", "Arial")
        mono = ("Cascadia Mono", "Consolas", "SF Mono", "JetBrains Mono",
                "DejaVu Sans Mono", "Menlo", "Courier New")
        self.f_base = _pick_font(root, ui, _sz(11))
        self.f_small = _pick_font(root, ui, _sz(10))
        self.f_tiny = _pick_font(root, ui, _sz(9))
        self.f_bold = _pick_font(root, ui, _sz(11), "bold")
        self.f_head = _pick_font(root, ui, _sz(13), "bold")
        self.f_title = _pick_font(root, ui, _sz(17), "bold")
        self.f_huge = _pick_font(root, ui, _sz(24), "bold")
        self.f_mono = _pick_font(root, mono, _sz(10))
        self.f_mono_bold = _pick_font(root, mono, _sz(10), "bold")

        self._apply()
        try:
            # Appens Notebook byggs direkt efter Theme-instansen. Vänta till
            # idle så att alla sju huvudflikar finns på plats.
            self.root.after_idle(self._apply_navigation_icons)
        except Exception:
            pass

    def px(self, value: float) -> int:
        """Skala ett basmått (96 DPI) till aktuell skärmtäthet och textstorlek."""
        return max(1, int(round(float(value) * getattr(self, "pixel_scale", 1.0))))

    def micro_icon_photo(self, kind: str, size: int = 16,
                         *, tone: str = "accent", inverted: bool = False):
        """Skapa och håll kvar en Tk-bild av en SVG-mikroikon skalad med pixel_scale."""
        try:
            from PIL import ImageTk
        except Exception:
            return None
        image = micro_icon_image(
            kind, self.c, size=self.px(size), tone=tone, inverted=inverted)
        if image is None:
            return None
        try:
            photo = ImageTk.PhotoImage(image, master=self.root)
            self._micro_icon_refs.append(photo)
            return photo
        except Exception:
            return None

    def _apply_navigation_icons(self) -> None:
        """Sätt temafärgade, skalbara ikoner på huvudfönstrets flikar."""
        try:
            from PIL import ImageTk
        except Exception:
            return

        kinds = ("start", "review", "categories", "settings",
                 "history", "help", "advanced")
        refs = []
        # Följ typsnittsskalan så att ikonerna inte blir pyttesmå i
        # förhållande till texten på HiDPI-skärmar.
        icon_size = max(16, min(64, int(round(20 * self.ui_scale))))

        def visit(widget):
            try:
                if widget.winfo_class() == "TNotebook":
                    tabs = widget.tabs()
                    if len(tabs) == len(kinds):
                        for tab, kind in zip(tabs, kinds):
                            image = navigation_icon_image(
                                kind, self.c, size=icon_size)
                            if image is not None:
                                photo = ImageTk.PhotoImage(image, master=self.root)
                                widget.tab(tab, image=photo, compound="left")
                                refs.append(photo)
                for child in widget.winfo_children():
                    visit(child)
            except Exception:
                return

        visit(self.root)
        # Keep current images alive; replacing this reference after tab updates
        # also releases the previous palette's raster icons on a theme change.
        try:
            self.root._arkivpiloten_tab_icon_refs = refs
        except Exception:
            pass

    # -- hängningsskydd: en okänd ttk-option på en exotisk tk-build får
    # ALDRIG krascha eller låsa starten - stilen hoppas bara över.
    def _cfg(self, name, **kw):
        try:
            self.style.configure(name, **kw)
        except Exception:
            pass

    def _map(self, name, **kw):
        try:
            self.style.map(name, **kw)
        except Exception:
            pass

    def _layout(self, name, spec):
        try:
            self.style.layout(name, spec)
        except Exception:
            pass

    # -- stilar -----------------------------------------------------------
    def _apply(self) -> None:
        c = self.c
        try:
            self.root.configure(background=c["bg"])
        except Exception:
            pass

        self._cfg(".", background=c["bg"], foreground=c["text"],
                     font=self.f_base, borderwidth=0, focuscolor=c["accent"])
        self._cfg("TFrame", background=c["bg"])
        self._cfg("TLabel", background=c["bg"], foreground=c["text"])
        self._cfg("TSeparator", background=c["border"])

        # -- brand header and start-page hero -----------------------------
        self._cfg("Topbar.TFrame", background=c["surface"],
                     relief="solid", borderwidth=1, bordercolor=c["border"])
        self._cfg("BrandTitle.TLabel", background=c["surface"],
                     foreground=c["text"], font=self.f_head)
        self._cfg("BrandSub.TLabel", background=c["surface"],
                     foreground=c["text_muted"], font=self.f_small)
        self._cfg("Hero.TFrame", background=c["accent_light"],
                     relief="solid", borderwidth=1,
                     bordercolor=c["accent_hair"])
        self._cfg("HeroTitle.TLabel", background=c["accent_light"],
                     foreground=c["accent_dark"], font=self.f_title)
        self._cfg("HeroText.TLabel", background=c["accent_light"],
                     foreground=c["text_muted"], font=self.f_small)
        self._cfg("Step.TFrame", background=c["surface"], relief="solid",
                     borderwidth=1, bordercolor=c["accent_hair"])

        # -- kort ---------------------------------------------------------
        # Ett kort är en vit yta med tunn ram. Rubriken ligger UTANFÖR
        # kortet, som en egen etikett ovanför - det ger en tydligare
        # gruppering än LabelFrame, vars inbyggda rubrik skär genom ramen.
        self._cfg("Card.TFrame", background=c["surface"],
                     relief="solid", borderwidth=1, bordercolor=c["border"])
        # Inre ytor på ett kort: samma vita färg men utan egen ram, annars
        # ritas en linje runt varje grupp inuti kortet.
        self._cfg("CardInner.TFrame", background=c["surface"],
                     relief="flat", borderwidth=0)
        self._cfg("Shadow.TFrame", background=c["shadow"])
        self._cfg("Sunk.TFrame", background=c["surface_sunk"],
                     relief="solid", borderwidth=1, bordercolor=c["border"])

        # Text som ligger på ett kort måste ha kortets bakgrund, annars
        # syns en grå fyrkant runt varje etikett.
        self._cfg("Card.TLabel", background=c["surface"], foreground=c["text"])
        self._cfg("CardMuted.TLabel", background=c["surface"],
                     foreground=c["text_muted"], font=self.f_small)
        self._cfg("CardHead.TLabel", background=c["surface"],
                     foreground=c["text"], font=self.f_head)
        self._cfg("CardTitle.TLabel", background=c["surface"],
                     foreground=c["text"], font=self.f_title)
        self._cfg("CardHuge.TLabel", background=c["surface"],
                     foreground=c["text"], font=self.f_huge)
        self._cfg("CardKey.TLabel", background=c["surface"],
                     foreground=c["text"], font=self.f_bold)

        # -- typografi ----------------------------------------------------
        self._cfg("Muted.TLabel", foreground=c["text_muted"], font=self.f_small)
        self._cfg("Faint.TLabel", foreground=c["text_faint"], font=self.f_small)
        self._cfg("Title.TLabel", font=self.f_title, foreground=c["text"])
        self._cfg("Head.TLabel", font=self.f_head, foreground=c["text"])
        self._cfg("Huge.TLabel", font=self.f_huge, foreground=c["text"])
        # Sektionsrubrik: liten, versal, dämpad - den ska leda ögat, inte
        # konkurrera med innehållet.
        self._cfg("Section.TLabel", font=self.f_small,
                     foreground=c["text_muted"], background=c["bg"])
        self._cfg("Ok.TLabel", foreground=c["ok"], font=self.f_small)
        self._cfg("Warn.TLabel", foreground=c["warn"], font=self.f_small)
        self._cfg("Err.TLabel", foreground=c["err"], font=self.f_small)
        px = self.px
        try:
            from tkinter import font as tkfont
            _line_h = int(tkfont.Font(root=self.root, font=self.f_base).metrics("linespace"))
        except Exception:
            _line_h = px(20)
        row_h = max(px(30), _line_h + px(12))

        for tone in ("ok", "warn", "err", "accent"):
            self._cfg(f"Pill{tone.title()}.TLabel",
                         background=c[f"{tone}_light"], foreground=c[tone],
                         font=self.f_small, padding=(px(9), px(3)))
        # Neutral statuspille (t.ex. "Bevakning: AV") - samma form som
        # statuspillerna men utan att ropa.
        self._cfg("PillMuted.TLabel", background=c["surface_alt"],
                     foreground=c["text_muted"], font=self.f_small,
                     padding=(px(9), px(3)))

        self._cfg("TLabelframe", background=c["bg"], borderwidth=1,
                     relief="solid", bordercolor=c["border"])
        self._cfg("TLabelframe.Label", background=c["bg"],
                     foreground=c["text_muted"], font=self.f_small)

        # -- knappar ------------------------------------------------------
        self._cfg("TButton", background=c["surface"], foreground=c["text"],
                     bordercolor=c["border_strong"], relief="solid",
                     borderwidth=1, padding=(px(12), px(7)), font=self.f_base,
                     anchor="center")
        self._map("TButton",
               background=[("pressed", c["accent_light"]),
                           ("active", c["accent_light"]),
                           ("disabled", c["bg"])],
               bordercolor=[("active", c["accent"]), ("disabled", c["border"])],
               foreground=[("disabled", c["text_faint"]),
                           ("active", c["accent_dark"])])

        self._cfg("Accent.TButton", background=c["accent"],
                     foreground=c["text_invert"], bordercolor=c["accent_dark"],
                     padding=(px(14), px(8)), font=self.f_bold)
        self._map("Accent.TButton",
               background=[("pressed", c["accent_dark"]),
                           ("active", c["accent_dark"]),
                           ("disabled", c["border_strong"])],
               bordercolor=[("disabled", c["border_strong"])],
               foreground=[("disabled", c["text_invert"]),
                           ("active", c["text_invert"])])

        self._cfg("Danger.TButton", foreground=c["err"],
                     bordercolor=c["border_strong"])
        self._map("Danger.TButton",
               background=[("active", c["err_light"]), ("pressed", c["err_light"])],
               bordercolor=[("active", c["err"])],
               foreground=[("active", c["err"])])

        self._cfg("Link.TButton", background=c["bg"], foreground=c["accent"],
                     borderwidth=0, relief="flat", padding=(px(8), px(5)),
                     font=self.f_base)
        self._map("Link.TButton",
               background=[("active", c["accent_light"]), ("pressed", c["accent_light"])],
               foreground=[("active", c["accent_dark"])])

        self._cfg("CardLink.TButton", background=c["surface"],
                     foreground=c["accent"], borderwidth=0, relief="flat",
                     padding=(px(8), px(5)))
        self._map("CardLink.TButton",
               background=[("active", c["accent_light"])],
               foreground=[("active", c["accent_dark"])])

        # -- flikar -------------------------------------------------------
        # Vald flik får vit botten och en kraftig accentkant upptill, så
        # den läses ihop med kortytan under.
        self._cfg("TNotebook", background=c["bg"], borderwidth=0,
                     tabmargins=(px(2), px(4), px(2), 0))
        self._cfg("TNotebook.Tab", background=c["bg"],
                     foreground=c["text_muted"], padding=(px(12), px(8)),
                     font=self.f_base, borderwidth=0)
        self._map("TNotebook.Tab",
               background=[("selected", c["surface"]), ("active", c["accent_light"])],
               foreground=[("selected", c["accent_dark"]), ("active", c["text"])],
               font=[("selected", self.f_bold)],
               expand=[("selected", (0, px(3), 0, 0))])

        # -- tabeller -----------------------------------------------------
        self._cfg("Treeview", background=c["surface"],
                     fieldbackground=c["surface"], foreground=c["text"],
                     rowheight=row_h, borderwidth=0, relief="flat",
                     font=self.f_base)
        self._cfg("Treeview.Heading", background=c["header_bg"],
                     foreground=c["text_muted"], relief="flat",
                     padding=(px(10), px(8)), font=self.f_small, borderwidth=0)
        self._map("Treeview.Heading",
               background=[("active", c["accent_light"])],
               foreground=[("active", c["accent_dark"])])
        self._map("Treeview",
               background=[("selected", c["accent_light"])],
               foreground=[("selected", c["accent_dark"])])
        self._layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

        # -- fält ---------------------------------------------------------
        for cls in ("TEntry", "TCombobox", "TSpinbox"):
            self._cfg(cls, fieldbackground=c["surface"],
                         background=c["surface"], foreground=c["text"],
                         bordercolor=c["border_strong"], borderwidth=1,
                         relief="solid", padding=(px(9), px(7)),
                         arrowcolor=c["text_muted"], insertcolor=c["text"],
                         selectbackground=c["accent_light"],
                         selectforeground=c["accent_dark"])
            self._map(cls,
                   bordercolor=[("focus", c["accent"]), ("disabled", c["border"])],
                   fieldbackground=[("disabled", c["surface_alt"]),
                                    ("readonly", c["surface"])],
                   background=[("disabled", c["surface_alt"])],
                   lightcolor=[("disabled", c["surface_alt"])],
                   darkcolor=[("disabled", c["surface_alt"])],
                   foreground=[("disabled", c["text_faint"])],
                   arrowcolor=[("disabled", c["text_faint"])])
        self._cfg("TCombobox", selectbackground=c["surface"],
                     selectforeground=c["text"])
        try:
            self.root.option_add("*TCombobox*Listbox.background", c["surface"])
            self.root.option_add("*TCombobox*Listbox.foreground", c["text"])
            self.root.option_add("*TCombobox*Listbox.selectBackground", c["accent_light"])
            self.root.option_add("*TCombobox*Listbox.selectForeground", c["accent_dark"])
            self.root.option_add("*TCombobox*Listbox.font", self.f_base)
        except Exception:
            pass

        # -- kryss och radio ----------------------------------------------
        # clam ritar bocken som en glyf i `indicatorforeground` ovanpå
        # rutan i `indicatorcolor`. Bocken måste därför vara mörk mot en
        # ljus ruta - sätts båda till samma ton försvinner krysset helt.
        for cls in ("TCheckbutton", "TRadiobutton"):
            self._cfg(cls, background=c["bg"], foreground=c["text"],
                         focusthickness=0, padding=(px(3), px(5)),
                         indicatorforeground=c["accent_dark"],
                         indicatorrelief="solid",
                         indicatormargin=(0, 0, px(7), 0),
                         bordercolor=c["border_strong"])
            self._map(cls,
                   background=[("active", c["bg"])],
                   foreground=[("disabled", c["text_faint"])],
                   indicatorforeground=[("disabled", c["text_faint"])],
                   bordercolor=[("selected", c["accent"]),
                                ("active", c["accent"]),
                                ("disabled", c["border"])],
                   indicatorcolor=[("disabled", c["bg"]),
                                   ("selected", c["accent_light"]),
                                   ("!selected", c["surface"])])
            # Samma kontroll placerad på ett vitt kort
            self._cfg(f"Card.{cls}", background=c["surface"])
            self._map(f"Card.{cls}",
                   background=[("active", c["surface"])],
                   foreground=[("disabled", c["text_faint"])],
                   indicatorforeground=[("disabled", c["text_faint"])],
                   bordercolor=[("selected", c["accent"]),
                                ("active", c["accent"]),
                                ("disabled", c["border"])],
                   indicatorcolor=[("disabled", c["surface_alt"]),
                                   ("selected", c["accent_light"]),
                                   ("!selected", c["surface"])])

        # -- rullningslister ----------------------------------------------
        sb_w = max(12, px(14))
        for orient in ("Vertical", "Horizontal"):
            self._cfg(f"{orient}.TScrollbar", background=c["border"],
                         troughcolor=c["bg"], bordercolor=c["bg"],
                         arrowcolor=c["text_muted"], relief="flat",
                         width=sb_w, arrowsize=sb_w)
            self._map(f"{orient}.TScrollbar",
                   background=[("pressed", c["accent"]),
                               ("active", c["border_strong"])])

        self._cfg("TProgressbar", background=c["accent"],
                     troughcolor=c["surface_sunk"], bordercolor=c["surface_sunk"],
                     lightcolor=c["accent"], darkcolor=c["accent"],
                     thickness=max(5, px(7)))

        # -- statusrad -----------------------------------------------------
        self._cfg("Status.TFrame", background=c["header_bg"])
        self._cfg("Status.TLabel", background=c["header_bg"],
                     foreground=c["text_muted"], font=self.f_small,
                     padding=(px(12), px(7)))

    # ======================================================================
    # Byggstenar
    # ======================================================================
    def card(self, parent, title: str = "", subtitle: str = "", **kw):
        """Ett vitt kort med rubriken ovanför ramen.

        Returnerar själva kortet. Rubriken läggs i en egen etikett över
        kortet, vilket ger tydligare gruppering än ttk:s LabelFrame där
        rubriken skär genom ramlinjen.

        Anroparen ansvarar för geometrihanteringen (grid/pack) på det
        returnerade kortet; rubriken placeras med samma metod automatiskt.
        """
        ttk = self.ttk
        holder = ttk.Frame(parent, style="TFrame", **kw)
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(1, weight=1)
        if title:
            head = ttk.Frame(holder, style="TFrame")
            head.grid(row=0, column=0, sticky="ew", pady=(0, self.px(5)))
            ttk.Label(head, text=title.upper(), style="Section.TLabel"
                      ).pack(side="left")
            if subtitle:
                ttk.Label(head, text="   " + subtitle, style="Faint.TLabel"
                          ).pack(side="left")
        body = ttk.Frame(holder, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        holder.body = body                      # type: ignore[attr-defined]
        return holder

    def zebra(self, tree) -> None:
        """Varannan rad tonad, plus färger för status."""
        c = self.c
        tree.tag_configure("odd", background=c["surface_alt"])
        tree.tag_configure("even", background=c["surface"])
        tree.tag_configure("muted", foreground=c["text_muted"])
        tree.tag_configure("strong", foreground=c["ok"])
        tree.tag_configure("weak", foreground=c["text_muted"])
        tree.tag_configure("off", foreground=c["text_faint"])
        tree.tag_configure("bad", foreground=c["err"])

    def fit_columns(self, tree, spec) -> None:
        """Sätt kolumnbredder som rymmer både rubrik och innehåll.

        Rubrikerna klipptes tidigare ("TRÄFFAF" i stället för "TRÄFFAR")
        eftersom bredden gissades i bildpunkter. Här mäts texten i stället
        med det faktiska typsnittet.

        `spec` = lista av (kolumn, rubrik, minsta_innehållsbredd, anchor,
        stretch).
        """
        try:
            from tkinter import font as tkfont
            head_font = tkfont.Font(font=self.f_small)
            cell_font = tkfont.Font(font=self.f_base)
        except Exception:
            head_font = cell_font = None
        head_pad = self.px(36)
        cell_pad = self.px(26)
        for col, txt, sample, anchor, stretch in spec:
            tree.heading(col, text=txt)
            if head_font is not None:
                head_w = head_font.measure(txt) + head_pad
                cell_w = cell_font.measure("x" * sample) + cell_pad
            else:
                char_w = max(8, self.px(9))
                head_w, cell_w = len(txt) * char_w + head_pad, sample * char_w
            need = max(head_w, cell_w)
            # Rubriken måste alltid rymmas, annars står det "TRÄFFAF".
            # Innehållet får däremot krympa i en kolumn som sträcker sig.
            tree.column(col, width=need, minwidth=head_w if stretch else need,
                        anchor=anchor, stretch=stretch)


# ==========================================================================
# FRISTÅENDE KÖRNING - provkarta över stilarna
# ==========================================================================

def _demo() -> int:
    """Visa alla stilar i ett fönster, för att kunna se ändringar direkt."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("ArkivPiloten - provkarta")
    root.geometry("760x620")
    theme = Theme(root, ttk)
    c = theme.c

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=theme.PAD, pady=(theme.PAD, 0))
    page = ttk.Frame(nb)
    nb.add(page, text="Provkarta")
    nb.add(ttk.Frame(nb), text="Andra fliken")
    page.columnconfigure(0, weight=1)
    page.rowconfigure(2, weight=1)

    knappar = theme.card(page, "Knappar")
    knappar.grid(row=0, column=0, sticky="ew", pady=(theme.PAD, 0),
                 padx=theme.PAD)
    rad = knappar.body
    for i, (txt, stil) in enumerate((("Primär", "Accent.TButton"),
                                     ("Vanlig", "TButton"),
                                     ("Farlig", "Danger.TButton"),
                                     ("Länk", "CardLink.TButton"))):
        ttk.Button(rad, text=txt, style=stil).grid(
            row=0, column=i, padx=(theme.INNER if i == 0 else 6,
                                   theme.INNER if i == 3 else 0),
            pady=theme.INNER)

    val = theme.card(page, "Kryss, radio och fält")
    val.grid(row=1, column=0, sticky="ew", pady=(theme.GAP, 0), padx=theme.PAD)
    v = val.body
    on, off, radio = tk.BooleanVar(value=True), tk.BooleanVar(), tk.StringVar(value="a")
    ttk.Checkbutton(v, text="Ikryssad", variable=on,
                    style="Card.TCheckbutton").grid(row=0, column=0, sticky="w",
                                                    padx=theme.INNER, pady=(theme.INNER, 2))
    ttk.Checkbutton(v, text="Urkryssad", variable=off,
                    style="Card.TCheckbutton").grid(row=1, column=0, sticky="w",
                                                    padx=theme.INNER)
    d = ttk.Checkbutton(v, text="Avstängd", variable=on, style="Card.TCheckbutton")
    d.grid(row=2, column=0, sticky="w", padx=theme.INNER, pady=(0, theme.INNER))
    d.state(["disabled"])
    ttk.Radiobutton(v, text="Val A", value="a", variable=radio,
                    style="Card.TRadiobutton").grid(row=0, column=1, sticky="w", padx=20)
    ttk.Radiobutton(v, text="Val B", value="b", variable=radio,
                    style="Card.TRadiobutton").grid(row=1, column=1, sticky="w", padx=20)
    ttk.Entry(v).grid(row=0, column=2, sticky="ew", padx=theme.INNER)
    ttk.Combobox(v, values=["Ett", "Två"], state="readonly").grid(
        row=1, column=2, sticky="ew", padx=theme.INNER, pady=4)
    ttk.Progressbar(v, value=62).grid(row=2, column=2, sticky="ew",
                                      padx=theme.INNER, pady=(4, theme.INNER))
    v.columnconfigure(2, weight=1)

    tab = theme.card(page, "Tabell", "med zebrarader och statusfärger")
    tab.grid(row=2, column=0, sticky="nsew", pady=(theme.GAP, 0), padx=theme.PAD)
    tab.body.columnconfigure(0, weight=1)
    tab.body.rowconfigure(0, weight=1)
    tree = ttk.Treeview(tab.body, columns=("a", "b", "c"), show="headings")
    theme.fit_columns(tree, (("a", "STÖDORD", 18, "w", True),
                             ("b", "TYP", 18, "w", False),
                             ("c", "TRÄFFAR", 5, "center", False)))
    theme.zebra(tree)
    for i, (w, t, n, tag) in enumerate((
            ("556123-4567", "organisationsnummer", 41, "strong"),
            ("pilkington.se", "domän", 12, "strong"),
            ("optifloat", "vanligt ord", 7, ""),
            ("glasbruksvagen", "vanligt ord", 0, "weak"))):
        tags = ["odd" if i % 2 else "even"] + ([tag] if tag else [])
        tree.insert("", "end", values=(w, t, n), tags=tags)
    tree.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)

    def _statusrad():
        return (f"Typsnitt: {theme.f_base[0]}  ·  fast bredd: {theme.f_mono[0]}  ·  "
                f"accent {c['accent']}  ·  skala {theme.ui_scale:g}  ·  kontrast: "
                + ("OK (WCAG)" if not audit_palette(c)
                   else f"UNDERKÄND {audit_palette(c)}"))

    status = ttk.Label(root, text=_statusrad(),
                       style="Status.TLabel", anchor="w")
    status.pack(fill="x", side="bottom")

    # Provkartan kan växla tema live: alla ttk-stilar är namngivna, så en
    # ny Theme-instans räcker för att hela fönstret ska byta skepnad.
    var_dark = tk.BooleanVar(value=theme.dark)
    var_hc = tk.BooleanVar(value=getattr(theme, "contrast", "normal") == "high")

    def byt_tema(*_):
        nonlocal theme, c
        theme = Theme(root, ttk, dark=var_dark.get(),
                      contrast="high" if var_hc.get() else "normal")
        c = theme.c
        status.configure(text=_statusrad())

    ttk.Checkbutton(root, text="Mörkt läge", variable=var_dark,
                    command=byt_tema).pack(side="bottom")
    ttk.Checkbutton(root, text="Högkontrast", variable=var_hc,
                    command=byt_tema).pack(side="bottom")
    root.mainloop()
    return 0


def _main() -> int:
    """Fristående körning, med begripligt fel när fönster inte kan öppnas."""
    try:
        return _demo()
    except ImportError as exc:
        print(f"Provkartan kräver tkinter, som saknas här: {exc}")
        return 1
    except Exception as exc:
        namn = type(exc).__name__
        msg = str(exc).lower()
        if namn == "TclError" or "display" in msg or "screen" in msg:
            print(f"Kan inte öppna provkartan (ingen skärm på den här "
                  f"datorn?): {exc}")
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(_main())
