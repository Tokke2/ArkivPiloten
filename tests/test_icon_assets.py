from __future__ import annotations

from pathlib import Path

from PIL import Image

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
