"""Regression tests for Omgång 11 selected proposals:
#237, #240, #243, #245, #249, #255, #260.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

import pdfsorter as P
import pdfsorter_data as D
import pdfsorter_theme as T


# ---------------------------------------------------------------------------
# #237 — Dynamic per-monitor DPI scaling
# ---------------------------------------------------------------------------
def test_window_dpi_calibrate_down_and_theme_override(monkeypatch):
    class FakeRoot:
        def __init__(self, dpi: float):
            self._dpi = dpi
            self.scaling_calls = []

        def winfo_id(self):
            return 12345

        def winfo_fpixels(self, _spec):
            return self._dpi

        def winfo_screenwidth(self):
            return 3840

        def winfo_screenheight(self):
            return 2160

        def tk_call(self, *args):
            if args[:2] == ("tk", "scaling") and len(args) == 3:
                self.scaling_calls.append(float(args[2]))
                return None
            if args == ("tk", "scaling"):
                return 2.6667
            return None

        def after_idle(self, _fn):
            pass

        def configure(self, **_kw):
            pass

    root = FakeRoot(96.0)
    root.tk = SimpleNamespace(call=root.tk_call)

    # Mock Windows GetDpiForWindow returning 192 DPI (200% monitor)
    fake_ctypes = SimpleNamespace(
        windll=SimpleNamespace(
            user32=SimpleNamespace(GetDpiForWindow=lambda hwnd: 192 if hwnd == 12345 else 96)))
    monkeypatch.setattr(T.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)
    assert T.window_dpi(root) == 192.0

    # Startup guard blocks scaling down, while dynamic move with allow_down=True permits it.
    root._dpi = 96.0
    fake_ctypes_96 = SimpleNamespace(
        windll=SimpleNamespace(user32=SimpleNamespace(GetDpiForWindow=lambda _h: 96)))
    monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes_96)
    assert T.calibrate_tk_scaling(root, allow_down=False) == pytest.approx(2.6667)
    applied = T.calibrate_tk_scaling(root, allow_down=True)
    assert applied == pytest.approx(96.0 / 72.0, rel=1e-4)
    assert root.scaling_calls[-1] == pytest.approx(96.0 / 72.0, rel=1e-4)

    class FakeStyle:
        def theme_names(self):
            return ("clam",)

        def theme_use(self, _name):
            pass

        def configure(self, *_a, **_kw):
            pass

        def map(self, *_a, **_kw):
            pass

        def layout(self, *_a, **_kw):
            pass

    monkeypatch.setattr(T, "_pick_font", lambda _r, fam, sz, w="normal": (fam[0], sz, w))
    fake_ttk = SimpleNamespace(Style=lambda _r=None: FakeStyle())
    theme_192 = T.Theme(root, fake_ttk, dark=False, text_scale=1.0, dpi_override=192.0)
    theme_96 = T.Theme(root, fake_ttk, dark=False, text_scale=1.0, dpi_override=96.0)
    assert theme_192.dpi == 192.0
    assert theme_192.pixel_scale == pytest.approx(2.0)
    assert theme_96.dpi == 96.0
    assert theme_96.pixel_scale == pytest.approx(1.0)
    assert theme_192.PAD > theme_96.PAD


def test_app_check_window_dpi_debounce_and_threshold(monkeypatch):
    app = object.__new__(P.App)
    app._closing = False
    app._dpi_check_job = None
    app.settings = {"ui_text_size": "normal"}
    app.theme = SimpleNamespace(dpi=96.0, dark=False, contrast="normal")
    app.root = SimpleNamespace(winfo_exists=lambda: True)
    applied = []
    app._apply_dpi_change = lambda d: applied.append(d)

    # Small jitter (< 12 DPI) is ignored.
    monkeypatch.setattr(P, "window_dpi", lambda _w: 102.0)
    P.App._check_window_dpi(app)
    assert applied == []

    # Crossing to 144 DPI triggers live rescaling.
    monkeypatch.setattr(P, "window_dpi", lambda _w: 144.0)
    P.App._check_window_dpi(app)
    assert applied == [144.0]


# ---------------------------------------------------------------------------
# #240 — Excerpt highlighting & PyMuPDF preview overlay rotation
# ---------------------------------------------------------------------------
def test_extract_highlight_terms_and_excerpt_windowing():
    cand = P.Candidate(text="Elbolaget AB", display="Elbolaget AB",
                       kind="company", score=4.0, count=2)
    best = SimpleNamespace(matched=["Elbolaget", "elbolaget", "Faktura"])
    strong = SimpleNamespace(
        text="Elbolaget AB " + ("lorem ipsum dolor " * 30) + "556033-9086 slutet",
        strong_ids=[{"kind": "orgnr", "value": "556033-9086"}],
    )
    decision = SimpleNamespace(best=best, extraction=strong)
    terms = P._extract_highlight_terms(decision, [cand])
    term_map = {t.lower(): kind for t, kind in terms}
    assert term_map["elbolaget"] == "keyword"
    assert term_map["556033-9086"] == "strong"

    excerpt, spans = P._build_highlighted_excerpt(strong.text, terms, max_chars=260)
    assert excerpt
    assert len(excerpt) <= 270
    assert spans
    for start, end, _kind, term in spans:
        assert excerpt[start:end].lower() == term.lower()


def test_transform_norm_box_matches_pil_ccw_rotation():
    # Verify normalized bounding box coordinates track PIL's CCW image.rotate().
    from PIL import Image, ImageDraw

    w, h = 200, 100
    orig = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(orig)
    # Paint a marker rectangle at normalized (0.10, 0.20, 0.30, 0.40)
    draw.rectangle((20, 20, 59, 39), fill=(255, 0, 0))

    norm = (0.10, 0.20, 0.30, 0.40)
    for angle in (0, 90, 180, 270):
        rot = orig.rotate(angle, expand=True, fillcolor="white")
        rw, rh = rot.size
        nx0, ny0, nx1, ny1 = P._transform_norm_box(norm, angle)
        cx = int((nx0 + nx1) * 0.5 * rw)
        cy = int((ny0 + ny1) * 0.5 * rh)
        r, g, b = rot.getpixel((cx, cy))
        assert (r, g, b) == (255, 0, 0), f"Mismatch at {angle}°: {(r, g, b)}"
        assert 0.0 <= nx0 < nx1 <= 1.0
        assert 0.0 <= ny0 < ny1 <= 1.0


def test_pymupdf_search_for_collects_normalized_hit_boxes(tmp_path):
    pdf_path = tmp_path / "faktura.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 120), "Pilkington Automotive Sverige AB\nOrg.nr 556033-9086")
    doc.save(str(pdf_path))
    doc.close()

    with fitz.open(str(pdf_path)) as doc:
        p = doc[0]
        rects = p.search_for("Pilkington")
        assert rects
        pw, ph = float(p.rect.width or 1.0), float(p.rect.height or 1.0)
        box = (rects[0].x0 / pw, rects[0].y0 / ph, rects[0].x1 / pw, rects[0].y1 / ph)
        assert 0.0 <= box[0] < box[2] <= 1.0
        assert 0.0 <= box[1] < box[3] <= 1.0


def test_review_dialog_prev_show_draws_highlight_overlay(monkeypatch):
    from PIL import Image

    captured_images = []
    fake_imagetk = SimpleNamespace(
        PhotoImage=lambda im: captured_images.append(im.copy()) or im)
    monkeypatch.setitem(sys.modules, "PIL.ImageTk", fake_imagetk)
    import PIL
    monkeypatch.setattr(PIL, "ImageTk", fake_imagetk, raising=False)

    dlg = object.__new__(P.ReviewDialog)
    base = Image.new("RGB", (400, 500), "white")
    dlg._prev_pil = [base]
    dlg._prev_hit_boxes = [[(0.15, 0.20, 0.55, 0.28, "strong", "556033-9086")]]
    dlg._prev_page = 0
    dlg._prev_rotation = 0
    dlg._prev_pages = []
    dlg._prev_display_size = (0, 0)
    dlg._review_two_columns = False
    dlg._preview_max_height = 500
    dlg.C = dict(T.COLORS)
    dlg.win = SimpleNamespace(winfo_fpixels=lambda _s: 96.0)
    dlg._all = SimpleNamespace(winfo_width=lambda: 800)
    dlg._prev_img = SimpleNamespace(
        delete=lambda *_a: None,
        configure=lambda **_kw: None,
        create_image=lambda *_a, **_kw: None,
    )
    info_cfg = {}
    hit_cfg = {}
    dlg._prev_info = SimpleNamespace(configure=lambda **kw: info_cfg.update(kw))
    dlg._prev_hit_label = SimpleNamespace(configure=lambda **kw: hit_cfg.update(kw))

    dlg.var_prev_highlights = SimpleNamespace(get=lambda: True)
    P.ReviewDialog._prev_show(dlg, 0)
    assert hit_cfg["text"] == "1 träffar markerade"
    assert "0°" in info_cfg["text"]
    highlighted_img = captured_images[-1]
    # Overlay pixels inside the bounding box are tinted (not pure white 255,255,255)
    assert highlighted_img.getextrema() != ((255, 255), (255, 255), (255, 255))

    dlg.var_prev_highlights = SimpleNamespace(get=lambda: False)
    P.ReviewDialog._prev_show(dlg, 0)
    assert hit_cfg["text"] == "1 dolda"
    plain_img = captured_images[-1]
    assert plain_img.getextrema() == ((255, 255), (255, 255), (255, 255))


# ---------------------------------------------------------------------------
# #243 — Jump from ReviewDialog to rule in Categories tab
# ---------------------------------------------------------------------------
def test_jump_to_keyword_rule_selects_category_and_unhides_linked():
    class FakeTree:
        def __init__(self, rows):
            self.rows = rows
            self.selected = ()
            self.focused = ""
            self.seen = ""

        def get_children(self):
            return list(self.rows.keys())

        def item(self, iid, option=None):
            if option == "values":
                return self.rows[iid]
            return {"values": self.rows[iid]}

        def selection_set(self, iid):
            self.selected = (iid,)

        def focus(self, iid):
            self.focused = iid

        def see(self, iid):
            self.seen = iid

    app = object.__new__(P.App)
    app.rules = SimpleNamespace(get=lambda name: {"name": name} if name == "Fakturor" else None)
    app.nb = SimpleNamespace(selected=None, select=lambda tab: setattr(app.nb, "selected", tab))
    app.tab_cats = "TAB_CATS"
    app.var_cat_select = SimpleNamespace(val="", set=lambda v: setattr(app.var_cat_select, "val", v))
    app.var_kw_hide_linked = SimpleNamespace(
        val=True,
        get=lambda: app.var_kw_hide_linked.val,
        set=lambda v: setattr(app.var_kw_hide_linked, "val", bool(v)),
    )
    app.kw_tree = FakeTree({"r1": ("Annat ord",)})
    app._on_cat_select = lambda: None
    app._log = lambda *_a, **_kw: None

    def reveal_linked():
        if not app.var_kw_hide_linked.val:
            app.kw_tree.rows["r2"] = ("556033-9086",)

    app._toggle_kw_hide_linked = reveal_linked

    found = P.App.jump_to_keyword_rule(app, "Fakturor", "556033-9086")
    assert found is True
    assert app.nb.selected == "TAB_CATS"
    assert app.var_cat_select.val == "Fakturor"
    assert app.var_kw_hide_linked.val is False
    assert app.kw_tree.selected == ("r2",)
    assert app.kw_tree.focused == "r2"
    assert app.kw_tree.seen == "r2"


def test_review_dialog_jump_sets_result_and_closes():
    closed = []
    dlg = object.__new__(P.ReviewDialog)
    dlg.result = None
    dlg._close = lambda: closed.append(True)
    P.ReviewDialog._jump_to_rule(dlg, "El", "Vattenfall")
    assert dlg.result == {"jump_rule": {"category": "El", "word": "Vattenfall"}}
    assert closed == [True]


# ---------------------------------------------------------------------------
# #245 — Customizable columns & widths in Granska & Historik
# ---------------------------------------------------------------------------
def test_q_and_h_column_order_and_widths_normalization(monkeypatch):
    assert D.DEFAULT_SETTINGS["q_column_order"] == []
    assert D.DEFAULT_SETTINGS["q_column_widths"] == {}
    assert D.DEFAULT_SETTINGS["h_column_order"] == []
    assert D.DEFAULT_SETTINGS["h_column_widths"] == {}

    assert P.normalize_column_order(["guess", "file"], columns=P.Q_COLUMNS) == [
        "guess", "file", "reason", "ocr"]
    assert P.normalize_column_order(["bad"], columns=P.H_COLUMNS) == list(P.H_COLUMNS)

    widths = P.normalize_column_widths(
        {"file": 320, "bad": 999, "score": -10, "matched": "abc"},
        columns=P.H_COLUMNS,
    )
    assert widths == {"file": 320}

    class FakeTree:
        def __init__(self, cols):
            self.cols = list(cols)
            self.display = list(cols)
            self.widths = {c: 200 for c in cols}
            self.bindings = {}

        def __getitem__(self, key):
            assert key == "displaycolumns"
            return list(self.display)

        def __setitem__(self, key, value):
            assert key == "displaycolumns"
            self.display = list(value)

        def column(self, col, option=None, **kw):
            if "width" in kw:
                self.widths[col] = int(kw["width"])
                return None
            if option == "width":
                return self.widths[col]
            return {}

        def identify_region(self, _x, _y):
            return self._region

        def identify_column(self, _x):
            return self._col_id

        def configure(self, **_kw):
            pass

        def bind(self, seq, fn, add=None):
            self.bindings[seq] = fn

    saved_history = []
    monkeypatch.setattr(P, "save_settings", lambda s: saved_history.append(dict(s)))

    app = object.__new__(P.App)
    app.settings = {"q_column_order": ["ocr", "file"], "q_column_widths": {"file": 280}}
    app.theme = SimpleNamespace(pixel_scale=2.0, px=lambda v: int(round(v * 2.0)))
    app.root = SimpleNamespace(after=lambda _ms, fn: fn())

    tree = FakeTree(P.Q_COLUMNS)
    P.App._install_tree_column_customization(
        app, tree, P.Q_COLUMNS, "q_column_order", "q_column_widths")
    assert tree.display == ["ocr", "file", "reason", "guess"]
    assert tree.widths["file"] == 560  # 280 * pixel_scale(2.0)

    # Simulate heading drag reordering and separator resize width persistence.
    # Display is ["ocr", "file", "reason", "guess"]; widths=[200, 560, 200, 200],
    # so dropping at x=820 crosses past "file" (edge 760).
    tree._region = "heading"
    tree._col_id = "#1"
    tree.bindings["<ButtonPress-1>"](SimpleNamespace(x=20, y=5))
    tree.bindings["<B1-Motion>"](SimpleNamespace(x=820, y=5))
    tree.bindings["<ButtonRelease-1>"](SimpleNamespace(x=820, y=5))
    assert app.settings["q_column_order"][0] != "ocr"

    tree._region = "separator"
    tree.widths["reason"] = 600
    tree.bindings["<ButtonPress-1>"](SimpleNamespace(x=200, y=5))
    tree.bindings["<ButtonRelease-1>"](SimpleNamespace(x=200, y=5))
    assert app.settings["q_column_widths"]["reason"] == 300  # 600 / pixel_scale(2.0)
    assert saved_history


# ---------------------------------------------------------------------------
# #249 — Extended ReviewDialog keyboard shortcuts & text-input guard
# ---------------------------------------------------------------------------
def test_review_dialog_focus_guard_blocks_letter_shortcuts_in_text_inputs():
    dlg = object.__new__(P.ReviewDialog)
    for cls in ("Entry", "TEntry", "TCombobox", "Text", "Spinbox"):
        dlg.win = SimpleNamespace(focus_get=lambda c=cls: SimpleNamespace(winfo_class=lambda c=c: c))
        assert P.ReviewDialog._focus_is_text_input(dlg, SimpleNamespace(state=0)) is True

    dlg.win = SimpleNamespace(focus_get=lambda: SimpleNamespace(winfo_class=lambda: "TButton"))
    assert P.ReviewDialog._focus_is_text_input(dlg, SimpleNamespace(state=0)) is False
    # Control/Alt held down should prevent bare r/u handlers from firing.
    assert P.ReviewDialog._focus_is_text_input(dlg, SimpleNamespace(state=0x4)) is True

    source = (Path(__file__).resolve().parents[1] / "pdfsorter.py").read_text(encoding="utf-8")
    for binding in (
        'self.win.bind("<Control-Return>", save_shortcut)',
        'self.win.bind("<KeyPress-r>"',
        'self.win.bind("<KeyPress-R>"',
        'self.win.bind("<KeyPress-u>"',
        'self.win.bind("<KeyPress-U>"',
    ):
        assert binding in source


# ---------------------------------------------------------------------------
# #255 — Vector SVG micro-icons scaled by pixel_scale
# ---------------------------------------------------------------------------
def test_micro_icon_svg_and_raster_cache():
    T._ACTION_ICON_CACHE.clear()
    for name in T.MICRO_ICON_SVGS:
        svg = T.micro_icon_svg(name, "#0a5ac8", size=24, bg="#ffffff")
        assert "<svg " in svg and "</svg>" in svg

    img_1x = T.micro_icon_image("sort", T.COLORS, size=16, tone="on_accent")
    img_2x = T.micro_icon_image("sort", T.COLORS, size=32, tone="on_accent")
    img_2x_cached = T.micro_icon_image("sort", T.COLORS, size=32, tone="on_accent")
    assert img_1x is not None and img_2x is not None and img_2x_cached is not None
    assert img_1x.size == (16, 16)
    assert img_2x.size == (32, 32)
    assert img_2x.tobytes() == img_2x_cached.tobytes()
    assert len(T._ACTION_ICON_CACHE) == 2

    # All icon names configured in App._apply_micro_icons must exist in MICRO_ICON_SVGS.
    for required in ("sort", "stop", "watch", "folder", "search", "audit",
                     "folder_clean", "help", "trash", "refresh", "review",
                     "undo", "status_active", "status_idle", "jump",
                     "pdf_text", "ocr"):
        assert T.micro_icon_image(required, T.COLORS, size=16) is not None

    # Fallback when Pillow icon rendering returns None keeps pill text intact.
    app = object.__new__(P.App)
    app.pill_dry = SimpleNamespace(grid=lambda: None, grid_remove=lambda: None)
    app.var_dry = SimpleNamespace(get=lambda: False)
    app.watcher = None
    app.archive_watcher = None
    app._refresh_watch_activity = lambda: None
    app.theme = SimpleNamespace(micro_icon_photo=lambda *_a, **_kw: None)
    pill_cfg = {}
    app.lbl_watch = SimpleNamespace(configure=lambda **kw: pill_cfg.update(kw))
    P.App._update_pills(app)
    assert pill_cfg["text"] == "● Bevakning: AV"
    assert pill_cfg["image"] == ""


# ---------------------------------------------------------------------------
# #260 — Safe empty archive folder discovery, cleanup & undo offer
# ---------------------------------------------------------------------------
def test_find_classify_and_prune_empty_archive_dirs(tmp_path):
    root = tmp_path / "Arkiv"
    cat_empty = root / "TomKategori"
    year_empty = root / "Fakturor" / "2024"
    sub_empty = root / "Avtal" / "2025" / "Leverantör"
    non_empty = root / "Kvitton" / "2025"
    cat_empty.mkdir(parents=True)
    year_empty.mkdir(parents=True)
    sub_empty.mkdir(parents=True)
    non_empty.mkdir(parents=True)
    (non_empty / "kvitto.pdf").write_bytes(b"%PDF-1.4\n")

    assert P.classify_archive_empty_dir(cat_empty, root) == "Kategorimapp"
    assert P.classify_archive_empty_dir(year_empty, root) == "Årsmapp"
    assert P.classify_archive_empty_dir(sub_empty, root) == "Undermapp"

    found = P.find_empty_archive_dirs(root)
    assert root not in found
    assert non_empty not in found
    assert non_empty.parent not in found
    assert set(found) == {
        cat_empty,
        year_empty,
        root / "Fakturor",
        sub_empty,
        root / "Avtal" / "2025",
        root / "Avtal",
    }

    # Nested empty tree is pruned deepest-first when prune_empty_archive_dirs runs.
    nested_parent = root / "El" / "2023"
    nested_leaf = nested_parent / "Vattenfall"
    nested_leaf.mkdir(parents=True)
    scoped = P.find_empty_archive_dirs(root, scope_dirs=[nested_leaf])
    assert set(scoped) == {root / "El", nested_parent, nested_leaf}

    # Put a file into sub_empty before pruning to verify safety check skips it.
    (sub_empty / "skyddad.pdf").write_bytes(b"%PDF-1.4\n")
    outside = tmp_path / "Utanför"
    outside.mkdir()
    removed, errors = P.prune_empty_archive_dirs(
        root,
        targets=[root, outside, sub_empty, cat_empty, year_empty,
                 nested_parent, nested_leaf],
    )
    assert not cat_empty.exists()
    assert not year_empty.exists()
    assert not nested_leaf.exists()
    assert not nested_parent.exists()
    assert sub_empty.exists()
    assert outside.exists()
    assert root.exists()
    assert {p.resolve() for p in removed} == {
        cat_empty.resolve(), year_empty.resolve(),
        nested_leaf.resolve(), nested_parent.resolve(),
    }
    err_paths = {p.resolve() for p, _msg in errors}
    assert sub_empty.resolve() in err_paths
    assert outside.resolve() in err_paths
    assert root.resolve() not in err_paths


def test_undo_selected_prompts_cleanup_when_archive_dir_becomes_empty(tmp_path, monkeypatch):
    inbox = tmp_path / "In"
    archive = tmp_path / "Arkiv"
    target_dir = archive / "Fakturor" / "2025"
    inbox.mkdir()
    target_dir.mkdir(parents=True)
    moved_pdf = target_dir / "faktura.pdf"
    orig_pdf = inbox / "faktura.pdf"
    moved_pdf.write_bytes(b"%PDF-1.4\n")

    ev = {"source": str(orig_pdf), "target": str(moved_pdf), "category": "Fakturor"}
    monkeypatch.setattr(P, "undo_event", lambda _e: (
        os.replace(moved_pdf, orig_pdf) or True, "ok"))
    monkeypatch.setattr(P, "replace_history", lambda _r: None)

    asks = []
    cleaned = []
    app = object.__new__(P.App)
    app._history = [ev]
    app.settings = {"output_dir": str(archive)}
    app.root = None
    app._selected_events = lambda: [ev]
    app._refresh_history = lambda: None
    app._log = lambda *_a, **_kw: None
    app._open_empty_archive_cleanup = lambda initial_dirs=None: cleaned.append(initial_dirs)
    app.messagebox = SimpleNamespace(
        askyesno=lambda _t, msg, **_kw: (asks.append(msg) or True),
        showinfo=lambda *_a, **_kw: None,
    )

    P.App._undo_selected(app)
    assert orig_pdf.exists()
    assert len(asks) == 2
    assert "tom(ma)" in asks[1]
    assert cleaned and {Path(p) for p in cleaned[0]} == {target_dir}
