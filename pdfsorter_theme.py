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

import sys

from typing import Dict, Tuple

#: Programmets version. Höjs vid varje leverans.
VERSION = "1.4.5"


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


class Theme:
    """Samlar färger, typsnitt och ttk-stilar på ett ställe.

    Tkinter ser förvalt ganska tråkigt ut, särskilt på Linux. Här byggs ett
    genomgående utseende: vita kort mot en svalt grå bakgrund, tydlig
    typografisk hierarki och en blå accentfärg reserverad för det som är
    viktigast på varje flik.
    """

    #: Standardavstånd i bildpunkter. Att gå via namn i stället för siffror
    #: gör att luften blir densamma på alla flikar.
    PAD = 14        # ytterkant mot fönstret
    GAP = 10        # mellan två kort
    INNER = 12      # inuti ett kort

    def __init__(self, root, ttk, dark: bool = False,
                 contrast: str = "normal"):
        self.root = root
        self.ttk = ttk
        self.dark = dark
        self.contrast = contrast
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

        # HiDPI: skala typsnitten efter skärmens pixeltäthet så att
        # gränssnittet inte blir pyttelitet på 4K-skärmar (design/läsbarhet).
        try:
            dpi = float(root.winfo_fpixels("1i"))
        except Exception:
            dpi = 96.0
        self.ui_scale = 1.25 if dpi >= 144 else (1.1 if dpi >= 120 else 1.0)

        def _sz(n: int) -> int:
            return max(8, int(round(n * self.ui_scale)))

        ui = ("Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text",
              "Helvetica Neue", "Cantarell", "Ubuntu", "DejaVu Sans", "Arial")
        mono = ("Cascadia Mono", "Consolas", "SF Mono", "JetBrains Mono",
                "DejaVu Sans Mono", "Menlo", "Courier New")
        self.f_base = _pick_font(root, ui, _sz(10))
        self.f_small = _pick_font(root, ui, _sz(9))
        self.f_tiny = _pick_font(root, ui, _sz(8))
        self.f_bold = _pick_font(root, ui, _sz(10), "bold")
        self.f_head = _pick_font(root, ui, _sz(12), "bold")
        self.f_title = _pick_font(root, ui, _sz(16), "bold")
        self.f_huge = _pick_font(root, ui, _sz(22), "bold")
        self.f_mono = _pick_font(root, mono, _sz(9))
        self.f_mono_bold = _pick_font(root, mono, _sz(9), "bold")

        self._apply()

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
        for tone in ("ok", "warn", "err", "accent"):
            self._cfg(f"Pill{tone.title()}.TLabel",
                         background=c[f"{tone}_light"], foreground=c[tone],
                         font=self.f_small, padding=(9, 3))
        # Neutral statuspille (t.ex. "Bevakning: AV") - samma form som
        # statuspillerna men utan att ropa.
        self._cfg("PillMuted.TLabel", background=c["surface_alt"],
                     foreground=c["text_muted"], font=self.f_small,
                     padding=(9, 3))

        self._cfg("TLabelframe", background=c["bg"], borderwidth=1,
                     relief="solid", bordercolor=c["border"])
        self._cfg("TLabelframe.Label", background=c["bg"],
                     foreground=c["text_muted"], font=self.f_small)

        # -- knappar ------------------------------------------------------
        self._cfg("TButton", background=c["surface"], foreground=c["text"],
                     bordercolor=c["border_strong"], relief="solid",
                     borderwidth=1, padding=(13, 7), font=self.f_base,
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
                     padding=(17, 8), font=self.f_bold)
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
                     borderwidth=0, relief="flat", padding=(8, 5),
                     font=self.f_base)
        self._map("Link.TButton",
               background=[("active", c["accent_light"]), ("pressed", c["accent_light"])],
               foreground=[("active", c["accent_dark"])])

        self._cfg("CardLink.TButton", background=c["surface"],
                     foreground=c["accent"], borderwidth=0, relief="flat",
                     padding=(8, 5))
        self._map("CardLink.TButton",
               background=[("active", c["accent_light"])],
               foreground=[("active", c["accent_dark"])])

        # -- flikar -------------------------------------------------------
        # Vald flik får vit botten och en kraftig accentkant upptill, så
        # den läses ihop med kortytan under.
        self._cfg("TNotebook", background=c["bg"], borderwidth=0,
                     tabmargins=(4, 6, 4, 0))
        self._cfg("TNotebook.Tab", background=c["bg"],
                     foreground=c["text_muted"], padding=(20, 10),
                     font=self.f_base, borderwidth=0)
        self._map("TNotebook.Tab",
               background=[("selected", c["surface"]), ("active", c["accent_light"])],
               foreground=[("selected", c["accent_dark"]), ("active", c["text"])],
               font=[("selected", self.f_bold)],
               expand=[("selected", (0, 3, 0, 0))])

        # -- tabeller -----------------------------------------------------
        self._cfg("Treeview", background=c["surface"],
                     fieldbackground=c["surface"], foreground=c["text"],
                     rowheight=30, borderwidth=0, relief="flat",
                     font=self.f_base)
        self._cfg("Treeview.Heading", background=c["header_bg"],
                     foreground=c["text_muted"], relief="flat",
                     padding=(10, 9), font=self.f_small, borderwidth=0)
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
                         relief="solid", padding=(9, 7),
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
                         focusthickness=0, padding=(3, 5),
                         indicatorforeground=c["accent_dark"],
                         indicatorrelief="solid", indicatormargin=(0, 0, 7, 0),
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
        for orient in ("Vertical", "Horizontal"):
            self._cfg(f"{orient}.TScrollbar", background=c["border"],
                         troughcolor=c["bg"], bordercolor=c["bg"],
                         arrowcolor=c["text_muted"], relief="flat",
                         width=13, arrowsize=13)
            self._map(f"{orient}.TScrollbar",
                   background=[("pressed", c["accent"]),
                               ("active", c["border_strong"])])

        self._cfg("TProgressbar", background=c["accent"],
                     troughcolor=c["surface_sunk"], bordercolor=c["surface_sunk"],
                     lightcolor=c["accent"], darkcolor=c["accent"], thickness=6)

        # -- statusrad -----------------------------------------------------
        self._cfg("Status.TFrame", background=c["header_bg"])
        self._cfg("Status.TLabel", background=c["header_bg"],
                     foreground=c["text_muted"], font=self.f_small,
                     padding=(12, 7))

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
            head.grid(row=0, column=0, sticky="ew", pady=(0, 5))
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
        for col, txt, sample, anchor, stretch in spec:
            tree.heading(col, text=txt)
            if head_font is not None:
                head_w = head_font.measure(txt) + 34
                cell_w = cell_font.measure("x" * sample) + 24
            else:
                head_w, cell_w = len(txt) * 9 + 34, sample * 9
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
