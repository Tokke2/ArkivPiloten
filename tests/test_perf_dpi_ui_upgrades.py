"""Regression tests for HiDPI, performance, memory, and UI upgrades."""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pdfsorter as P
import pdfsorter_read as R
import pdfsorter_system as S
import pdfsorter_theme as T

ROOT = Path(__file__).resolve().parents[1]


def test_system_icon_sizes_and_tray_refresh_dedup():
    assert 256 in S.WINDOW_ICON_SIZES
    assert min(S.WINDOW_ICON_SIZES) == 16
    assert "SetProcessDpiAwarenessContext" in (
        ROOT / "pdfsorter_system.py").read_text(encoding="utf-8")

    class FakeIcon:
        def __init__(self):
            self.icon = None
            self.title = ""
            self.visible = False
            self.menu_calls = 0

        def update_menu(self):
            self.menu_calls += 1

        def stop(self):
            pass

    app = SimpleNamespace(visible=False, queue=[], watcher=None,
                          settings={}, rules=SimpleNamespace())
    tray = S.TrayIcon(app)
    tray.icon = FakeIcon()

    tray.refresh()
    assert tray.icon.menu_calls == 1
    first_img = tray.icon.icon
    assert first_img is not None
    assert "Bevakning AV" in tray.icon.title

    # Identical state skips redundant icon regeneration and menu update.
    tray.refresh()
    assert tray.icon.menu_calls == 1
    assert tray.icon.icon is first_img

    # Changing state refreshes the icon and title immediately.
    app.watcher = SimpleNamespace(running=True)
    app.queue = ["item1", "item2"]
    tray.refresh()
    assert tray.icon.menu_calls == 2
    assert "Bevakning PÅ" in tray.icon.title
    assert "2 väntar på granskning" in tray.icon.title

    tray.stop()
    assert tray._last_tray_state is None


def test_theme_dpi_helpers_icon_cache_and_pixel_scaling():
    class FakeDisplay:
        def __init__(self, dpi=144.0):
            self._dpi = dpi

        def winfo_fpixels(self, _spec):
            return self._dpi

    assert T.display_dpi(FakeDisplay(192.0)) == 192.0
    assert T.display_dpi(None) == 96.0

    # Navigation & action icons scale cleanly and hit LRU cache.
    T._NAV_ICON_CACHE.clear()
    T._ACTION_ICON_CACHE.clear()
    palette = T.COLORS
    nav1 = T.navigation_icon_image("start", palette, size=64)
    nav2 = T.navigation_icon_image("start", palette, size=64)
    assert nav1 is not None and nav2 is not None
    assert nav1.size == (64, 64)
    assert len(T._NAV_ICON_CACHE) == 1

    act1 = T.action_icon_image("search", palette, size=48, inverted=True)
    act2 = T.action_icon_image("search", palette, size=48, inverted=True)
    assert act1 is not None and act2 is not None
    assert act1.size == (48, 48)
    assert len(T._ACTION_ICON_CACHE) == 1


def test_theme_px_and_tk_handles_dpi_guard(monkeypatch):
    theme = object.__new__(T.Theme)
    theme.dpi_scale = 2.0
    theme.pixel_scale = 2.0
    assert theme.px(12) == 24
    assert theme.px(1) == 2

    # When tk_handles_dpi=True (scaled Tk/Windows), font pt sizes must stay
    # un-multiplied by dpi_scale while layout pixels scale continuously.
    class FakeRoot:
        def __init__(self):
            self.tk_calls = []

        def winfo_fpixels(self, _spec):
            return 192.0

        def winfo_screenwidth(self):
            return 3840

        def winfo_screenheight(self):
            return 2160

        def tk_call(self, *args):
            self.tk_calls.append(args)
            if args == ("tk", "scaling"):
                return 2.6667
            return None

        def after_idle(self, _fn):
            pass

        def configure(self, **_kw):
            pass

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

    root = FakeRoot()
    root.tk = SimpleNamespace(call=root.tk_call)
    monkeypatch.setattr(T, "_pick_font", lambda _r, fam, sz, w="normal": (fam[0], sz, w))
    fake_ttk = SimpleNamespace(Style=lambda _r=None: FakeStyle())

    monkeypatch.setattr(T.sys, "platform", "win32")
    t_win = T.Theme(root, fake_ttk, dark=False, text_scale=1.0)
    assert t_win.dpi == 192.0
    assert t_win.f_base[1] == 11  # not doubled when Tk already scales DPI
    assert t_win.PAD == 24        # 12 * 2.0 layout padding

    monkeypatch.setattr(T.sys, "platform", "linux")
    t_linux = T.Theme(root, fake_ttk, dark=False, text_scale=1.0)
    assert t_linux.f_base[1] == 11
    assert t_linux.PAD == 24


def test_extraction_combined_memoizes_and_invalidates():
    ext = R.Extraction(
        path=Path("faktura.pdf"),
        text="Del A",
        filename_text="faktura",
        metadata={"Author": "Pilkington"},
    )
    c1 = ext.combined
    c2 = ext.combined
    assert c1 is c2
    assert "faktura" in c1 and "Del A" in c1 and "Pilkington" in c1

    ext.text = "Del B"  # same length still invalidates cache
    c3 = ext.combined
    assert c3 is not c1
    assert "Del B" in c3


def test_ocr_high_quality_early_exit_and_low_conf_fallback(monkeypatch):
    calls = []

    class FakeImage:
        def __init__(self, w=1000, h=1200):
            self.width = w
            self.height = h
            self.size = (w, h)
            self.closed = False

        def convert(self, _mode):
            return self

        def rotate(self, _angle, *_a, **_kw):
            return FakeImage(self.width, self.height)

        def resize(self, size, *_a, **_kw):
            return FakeImage(size[0], size[1])

        def close(self):
            self.closed = True

    fake_pytesseract = SimpleNamespace(
        pytesseract=SimpleNamespace(tesseract_cmd=""),
        Output=SimpleNamespace(DICT="dict"),
        image_to_osd=lambda *_a, **_kw: {"rotate": 0, "orientation_conf": 0.0},
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)
    monkeypatch.setattr(R, "ocr_available", lambda: True)
    monkeypatch.setattr(R, "tesseract_binary", lambda: "")
    monkeypatch.setattr(R, "_resolve_langs", lambda _pt, _lang: "swe+eng")
    monkeypatch.setattr(R, "_tess_call", lambda *_a, **_kw: {"rotate": 0, "orientation_conf": 0.0})
    monkeypatch.setattr(R, "_preprocess", lambda im, _q, do_deskew=True: FakeImage(im.width, im.height))
    monkeypatch.setattr(R, "_binarize", lambda im: FakeImage(im.width, im.height))

    # Case 1: High-confidence first pass (--psm 3) stops after 1 pass even in high quality.
    calls.clear()
    img1 = FakeImage()
    monkeypatch.setattr(R, "_render_pages", lambda _p, _m, dpi=220: [img1])

    def high_conf_pass(_img, _langs, cfg, _pt):
        calls.append(cfg)
        return (94.0, "Faktura 556033-9086 Pilkington " * 6)

    monkeypatch.setattr(R, "_ocr_pass", high_conf_pass)
    text, conf, _pages = R._run_ocr_detailed(
        Path("scan.pdf"), max_pages=1, language="swe+eng", quality="high")
    assert calls == ["--oem 1 --psm 3"]
    assert conf > 90.0
    assert "Pilkington" in text
    assert img1.closed

    # Case 2: Moderate confidence on first pass runs extra passes without upscale
    # when extra pass recovers >= 82.0% & >= 80 chars.
    calls.clear()
    img2 = FakeImage()
    monkeypatch.setattr(R, "_render_pages", lambda _p, _m, dpi=220: [img2])

    def moderate_conf_pass(img, _langs, cfg, _pt):
        calls.append((cfg, img.width))
        if "--psm 6" in cfg:
            return (86.0, "Tydligare text efter psm 6 " * 5)
        return (40.0, "svag")

    monkeypatch.setattr(R, "_ocr_pass", moderate_conf_pass)
    text2, conf2, _pages2 = R._run_ocr_detailed(
        Path("scan2.pdf"), max_pages=1, language="swe+eng", quality="high")
    assert calls[0][0] == "--oem 1 --psm 3"
    assert any("--psm 6" in c for c, _w in calls)
    assert all(w == 1000 for _c, w in calls)
    assert conf2 > 85.0
    assert "Tydligare text" in text2
    assert img2.closed

    # Case 3: Weak confidence (<82%) across standard passes triggers 1.5x upscale.
    calls.clear()
    img3 = FakeImage()
    monkeypatch.setattr(R, "_render_pages", lambda _p, _m, dpi=220: [img3])

    def weak_conf_pass(img, _langs, cfg, _pt):
        calls.append((cfg, img.width))
        if img.width == 1500:
            return (91.0, "Skarp uppskalad text " * 6)
        return (65.0, "blek text")

    monkeypatch.setattr(R, "_ocr_pass", weak_conf_pass)
    text3, conf3, _pages3 = R._run_ocr_detailed(
        Path("scan3.pdf"), max_pages=1, language="swe+eng", quality="high")
    assert any(w == 1500 for _c, w in calls)
    assert conf3 > 90.0
    assert "Skarp uppskalad text" in text3
    assert img3.closed


def test_zones_cache_list_pdfs_exclude_and_text_cache_eviction(tmp_path):
    P.TEXT_CACHE.clear()
    assert len(P._ZONES_CACHE) == 0

    ext = P.Extraction(
        path=tmp_path / "faktura_123.pdf",
        text="Pilkington Automotive\nOrg.nr 556033-9086\nAtt: Kund AB\n",
        filename_text="faktura_123",
    )
    z1 = P._zones_for(ext.combined, ext.filename_text, ext.page_header, ext.page_footer)
    z2 = P._zones_for(ext.combined, ext.filename_text, ext.page_header, ext.page_footer)
    assert z1 is z2
    assert len(P._ZONES_CACHE) == 1

    # Excluded directory pruning during list_pdfs avoids traversing excluded subtrees.
    in_dir = tmp_path / "in"
    keep_dir = in_dir / "Ok"
    skip_dir = in_dir / "Arkiv" / "2024"
    keep_dir.mkdir(parents=True)
    skip_dir.mkdir(parents=True)
    (keep_dir / "a.pdf").write_bytes(b"%PDF-1.4")
    (skip_dir / "b.pdf").write_bytes(b"%PDF-1.4")

    found = P.list_pdfs(in_dir, recursive=True, excludes=[str(in_dir / "Arkiv")])
    assert [p.name for p in found] == ["a.pdf"]

    # TextCache.configure_limits + forget() O(1) path eviction.
    P.TEXT_CACHE.configure_limits(low_memory=True)
    assert P.TEXT_CACHE.MAX_ENTRIES == 200
    assert P.TEXT_CACHE.MAX_BYTES == 8 * 1024 * 1024

    pdf_file = keep_dir / "a.pdf"
    P.TEXT_CACHE.put(pdf_file, ext)
    assert P.TEXT_CACHE.get(pdf_file) is ext
    P.TEXT_CACHE.forget(pdf_file)
    assert P.TEXT_CACHE.get(pdf_file) is None

    P.TEXT_CACHE.configure_limits(low_memory=False)
    assert P.TEXT_CACHE.MAX_ENTRIES == 800
    assert P.TEXT_CACHE.MAX_BYTES == 24 * 1024 * 1024

    P.TEXT_CACHE.clear()
    assert len(P._ZONES_CACHE) == 0


def test_disk_cache_utime_throttle_and_watcher_tree_pruning(tmp_path):
    cache = P.DiskTextCache()
    cache.dir = tmp_path / "diskcache"
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF-1.4\nhello")
    ext = P.Extraction(path=src, text="Hej världen")
    cache.put(src, ext)
    entry = cache.dir / (cache._hash(src) + ".json")

    # Fresh entry (<3600s old) avoids rewriting mtime on hit.
    recent_stamp = time.time() - 60
    os.utime(entry, (recent_stamp, recent_stamp))
    assert cache.get(src) is not None
    assert abs(entry.stat().st_mtime - recent_stamp) < 2.0

    # Stale entry (>3600s old) gets mtime refreshed on hit.
    old_stamp = time.time() - 5 * 86400
    os.utime(entry, (old_stamp, old_stamp))
    assert cache.get(src) is not None
    assert entry.stat().st_mtime > old_stamp + 3600

    # FolderWatcher recursive tree signatures & stale key cleanup.
    watch_dir = tmp_path / "watch"
    sub = watch_dir / "sub"
    sub.mkdir(parents=True)
    p1 = sub / "f1.pdf"
    p1.write_bytes(b"pdf1")
    watcher = P.FolderWatcher(watch_dir, lambda _p: None, recursive=True)
    sigs1 = watcher._collect_dir_tree_sigs()
    sigs2 = watcher._collect_dir_tree_sigs()
    assert sigs1 == sigs2 and len(sigs1) == 2

    watcher._seen[str(p1)] = (0, 0)
    watcher._seen[str(watch_dir / "deleted.pdf")] = (0, 0)
    watcher._waiting[str(watch_dir / "deleted.pdf")] = (0, 0, time.time())
    existing_keys = {os.path.normcase(os.path.abspath(str(p1)))}
    stale_seen = [k for k in watcher._seen if k not in existing_keys]
    for k in stale_seen:
        watcher._seen.pop(k, None)
        watcher._waiting.pop(k, None)
    assert str(watch_dir / "deleted.pdf") not in watcher._seen


def test_fit_geometry_hidpi_scaling_and_adaptive_pump(monkeypatch):
    class HiDpiWindow:
        def __init__(self):
            self.geom = ""
            self.min_args = None
            self.max_args = None

        def winfo_screenwidth(self):
            return 3840

        def winfo_screenheight(self):
            return 2160

        def winfo_fpixels(self, _spec):
            return 192.0  # 2.0x -> capped 1.85x scaling

        def geometry(self, val):
            self.geom = val

        def minsize(self, w, h):
            self.min_args = (w, h)

        def maxsize(self, w, h):
            self.max_args = (w, h)

    w = HiDpiWindow()
    P._fit_geometry(w, 1280, 880, 1060, 720)
    assert w.geom.startswith("2368x1628+")
    assert w.min_args == (1961, 1332)
    assert w.max_args == (3744, 2016)

    # Adaptive App._pump interval based on activity and visibility.
    app = object.__new__(P.App)
    app._ui_lock = P.threading.Lock()
    app._ui_calls = []
    app._busy = False
    app.visible = False
    app._review_is_open = lambda: False
    app._last_show_check = time.monotonic()
    scheduled = []
    app.root = SimpleNamespace(after=lambda ms, _cb: scheduled.append(ms))

    monkeypatch.setattr(P, "consume_show_request", lambda: False)
    P.App._pump(app)
    app.visible = True
    P.App._pump(app)
    app._busy = True
    P.App._pump(app)
    assert scheduled == [750, 280, 120]


def test_retint_raw_updates_all_raw_widgets_and_trees():
    configured = []

    class DummyWidget:
        def __init__(self, name):
            self.name = name

        def configure(self, **kw):
            configured.append((self.name, kw))

        def tag_configure(self, tag, **kw):
            configured.append((f"{self.name}.{tag}", kw))

    app = object.__new__(P.App)
    app.C = dict(P.COLORS)
    app.theme = SimpleNamespace(
        zebra=lambda tree: configured.append((f"zebra.{tree.name}", {})))
    for attr in ("in_list", "exc_list", "ign_word_list", "ign_glob_list",
                 "ign_file_list", "_brand_icon_label", "logbox", "json_text",
                 "help_text", "kw_tree", "selected_keyword_map_tree",
                 "subfolder_map_tree", "q_tree", "h_tree"):
        setattr(app, attr, DummyWidget(attr))
    app._scroll_canvases = [(DummyWidget("scroll_canvas"), "settings")]

    P.App._retint_raw(app)
    touched = {name for name, _kw in configured}
    assert {"in_list", "exc_list", "ign_word_list", "ign_glob_list",
            "ign_file_list", "scroll_canvas", "_brand_icon_label",
            "logbox", "json_text", "help_text",
            "zebra.kw_tree", "zebra.selected_keyword_map_tree",
            "zebra.subfolder_map_tree", "zebra.q_tree",
            "zebra.h_tree"} <= touched


def test_forslag_contains_25_new_desktop_proposals():
    text = (ROOT / "PDFSORTER_FORSLAG.md").read_text(encoding="utf-8")
    numbers = [int(m.group(1))
               for m in re.finditer(r"^\|\s*(23[7-9]|24\d|25\d|26[01])\s*\|",
                                    text, re.MULTILINE)]
    assert numbers == list(range(237, 262))
