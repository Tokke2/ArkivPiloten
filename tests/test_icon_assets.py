from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

from PIL import Image

import pdfsorter_system as S

ROOT = Path(__file__).resolve().parents[1]


def test_shared_master_icon_has_transparency_and_expected_sizes():
    png = ROOT / "ArkivPiloten.png"
    ico = ROOT / "ArkivPiloten.ico"
    with Image.open(png) as image:
        assert image.size == (512, 512)
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0
        assert image.getpixel((256, 0))[3] == 255
    with Image.open(ico) as image:
        assert image.format == "ICO"
        assert {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                (128, 128), (256, 256)} <= set(image.ico.sizes())


def test_active_tray_icon_has_a_high_contrast_status_badge():
    from PIL import ImageChops

    idle = S.make_icon_image(64, active=False)
    active = S.make_icon_image(64, active=True)
    assert idle is not None and active is not None
    diff = ImageChops.difference(
        idle.convert("RGB"), active.convert("RGB")).getbbox()
    assert diff is not None
    assert diff[0] >= 32 and diff[1] >= 32  # endast statusbrickan nere till höger


def test_every_app_toplevel_is_explicitly_branded():
    lines = (ROOT / "pdfsorter.py").read_text(encoding="utf-8").splitlines()
    positions = [i for i, line in enumerate(lines) if "tk.Toplevel(" in line]
    assert positions
    for i in positions:
        assert any("brand_window(" in line for line in lines[i + 1:i + 3]), \
            f"Toplevel on line {i + 1} does not set the app icon"


def test_windows_app_id_is_set_with_a_unicode_argument(monkeypatch):
    calls = []

    class FakeSetter:
        argtypes = None
        restype = None

        def __call__(self, app_id):
            calls.append(app_id)
            return 0

    setter = FakeSetter()
    fake_ctypes = SimpleNamespace(
        c_wchar_p=object(), c_long=object(),
        windll=SimpleNamespace(
            shell32=SimpleNamespace(
                SetCurrentProcessExplicitAppUserModelID=setter)))
    monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)
    monkeypatch.setattr(S.sys, "platform", "win32")

    S.set_app_user_model_id()

    assert calls == [S.APP_USER_MODEL_ID]
    assert setter.argtypes == (fake_ctypes.c_wchar_p,)
    assert setter.restype is fake_ctypes.c_long


def test_brand_window_sets_both_window_and_default_icons_on_windows(
        monkeypatch, tmp_path):
    monkeypatch.setattr(S.sys, "platform", "win32")
    photo = object()
    icon_path = tmp_path / "arkivpiloten.ico"
    icon_path.write_bytes(b"ico")
    monkeypatch.setattr(S, "icon_photoimage", lambda size: photo)
    monkeypatch.setattr(S, "ensure_icon_file", lambda: icon_path)

    class FakeWindow:
        def __init__(self):
            self.calls = []

        def iconphoto(self, *args):
            self.calls.append(("iconphoto", args))

        def iconbitmap(self, *args, **kwargs):
            self.calls.append(("iconbitmap", args, kwargs))

    window = FakeWindow()
    assert S.brand_window(window) is photo
    assert window._arkivpiloten_icon_ref is photo
    assert ("iconphoto", (True, photo)) in window.calls
    assert ("iconbitmap", (str(icon_path),), {}) in window.calls
    assert ("iconbitmap", (), {"default": str(icon_path)}) in window.calls
