import pytest

from pdfsorter_theme import COLORS, COLORS_DARK, COLORS_HC, navigation_icon_image


@pytest.mark.parametrize("palette", [COLORS, COLORS_DARK, COLORS_HC])
def test_navigation_icons_are_drawn_in_each_theme(palette):
    pytest.importorskip("PIL")
    names = ("start", "review", "categories", "settings", "history", "help", "advanced")

    for name in names:
        icon = navigation_icon_image(name, palette, size=20)
        assert icon is not None
        assert icon.size == (20, 20)
        assert icon.mode == "RGBA"
        assert icon.getbbox() is not None


def test_navigation_icon_rejects_unknown_names():
    pytest.importorskip("PIL")
    assert navigation_icon_image("unknown", COLORS) is None


def test_navigation_icon_size_follows_ui_scale():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "pdfsorter_theme.py").read_text(
        encoding="utf-8")

    assert "20 * self.ui_scale" in source
    assert "size=icon_size" in source
