from __future__ import annotations

from pathlib import Path

import pytest

import pdfsorter as P
import pdfsorter_data as D


def _one_page_pdf(path: Path) -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as stream:
        writer.write(stream)
    return path.read_bytes()


def test_transfer_directories_are_created_under_config_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "config_dir", lambda: tmp_path / "settings")

    imports = P.rules_transfer_dir("imports")
    exports = P.rules_transfer_dir("exports")

    assert imports == tmp_path / "settings" / "imports"
    assert exports == tmp_path / "settings" / "exports"
    assert imports.is_dir() and exports.is_dir()
    with pytest.raises(ValueError):
        P.rules_transfer_dir("other")


def test_review_dialog_always_saves_selected_support_words():
    class _Value:
        def get(self):
            return ""

    class _Messagebox:
        def showwarning(self, *args, **kwargs):
            raise AssertionError("A valid category should not show a warning")

    dialog = type("DialogStub", (), {})()
    dialog._category = lambda: "Supplier"
    dialog._chosen = lambda: ["invoice", "bankgiro"]
    dialog.var_subfolder = _Value()
    dialog.win = object()
    dialog.messagebox = _Messagebox()
    dialog._close = lambda: setattr(dialog, "closed", True)

    P.ReviewDialog._ok(dialog)

    assert dialog.result["words"] == ["invoice", "bankgiro"]
    assert dialog.result["save_rule"] is True
    assert dialog.closed is True


def test_review_preview_shrinks_to_fit_short_displays():
    short = P._review_preview_height(430)
    medium = P._review_preview_height(720)
    tall = P._review_preview_height(1200)

    assert 100 <= short < medium <= tall <= 240


def test_shortcut_sheet_lists_platform_shortcuts_and_dialog_keys():
    text = P.shortcuts_help_text("darwin")

    assert "Command+O" in text
    assert "Command+Tab" in text
    assert "F6 / Shift+F6" in text
    assert "Escape" in text


def test_common_errors_have_safe_actionable_guidance():
    assert "behörighet" in P.error_next_step(PermissionError("denied"))
    assert "diskutrymme" in P.error_next_step(OSError(28, "full"))
    assert "originalfilen" in P.error_next_step(ValueError("bad setting"))


def test_old_settings_enable_review_preview_only_once():
    settings = {"preview_in_dialog": False}

    assert P.migrate_review_preview_setting(settings)
    assert settings["preview_in_dialog"] is True
    assert settings["review_preview_migrated_v1"] is True
    assert not P.migrate_review_preview_setting(settings)


def test_rotation_saves_a_new_pdf_and_preserves_original(tmp_path):
    source = tmp_path / "source.pdf"
    original = _one_page_pdf(source)
    target = tmp_path / "rotated.pdf"

    P.rotate_pdf_copy(source, target, 90)

    from pypdf import PdfReader
    assert source.read_bytes() == original
    assert int(PdfReader(str(target)).pages[0].rotation) == 90
    with pytest.raises(ValueError, match="original"):
        P.rotate_pdf_copy(source, source, 90)


def test_in_place_rotation_keeps_recoverable_backup_and_updates_original(tmp_path):
    source = tmp_path / "invoice.pdf"
    original = _one_page_pdf(source)

    updated, backup = P.rotate_pdf_with_backup(source, 90)

    from pypdf import PdfReader
    assert updated == source
    assert backup.read_bytes() == original
    assert backup.suffix == ".bak"
    assert int(PdfReader(str(source)).pages[0].rotation) == 90


def test_in_place_rotation_failure_leaves_original_unchanged(monkeypatch, tmp_path):
    source = tmp_path / "invoice.pdf"
    original = _one_page_pdf(source)

    def fail_rotation(*_args, **_kwargs):
        raise ValueError("invalid PDF")

    monkeypatch.setattr(P, "rotate_pdf_copy", fail_rotation)
    with pytest.raises(ValueError, match="invalid PDF"):
        P.rotate_pdf_with_backup(source, 90)

    assert source.read_bytes() == original
    assert not list(tmp_path.glob("*.bak"))


def test_in_place_rotation_replace_failure_keeps_original_and_backup(
        monkeypatch, tmp_path):
    source = tmp_path / "invoice.pdf"
    original = _one_page_pdf(source)
    real_replace = P.os.replace

    def fail_source_replace(src, dst):
        if Path(dst) == source:
            raise PermissionError("file is locked")
        return real_replace(src, dst)

    monkeypatch.setattr(P.os, "replace", fail_source_replace)
    with pytest.raises(PermissionError, match="locked"):
        P.rotate_pdf_with_backup(source, 90)

    assert source.read_bytes() == original
    backups = list(tmp_path.glob("*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original


def test_deskew_saves_image_copy_and_preserves_original(tmp_path):
    pytest.importorskip("fitz")
    source = tmp_path / "source.pdf"
    original = _one_page_pdf(source)
    target = tmp_path / "straightened.pdf"

    P.deskew_pdf_copy(source, target, 1.25, dpi=96)

    import fitz
    assert source.read_bytes() == original
    with fitz.open(target) as result:
        assert len(result) == 1
        assert result[0].get_images()


def test_automatic_deskew_estimates_each_page(monkeypatch, tmp_path):
    pytest.importorskip("fitz")
    source = tmp_path / "source.pdf"
    _one_page_pdf(source)
    target = tmp_path / "auto-straightened.pdf"
    estimated = []

    def estimate(image, **_kwargs):
        estimated.append(image.size)
        return 1.0

    monkeypatch.setattr(P, "_deskew_angle", estimate)
    P.deskew_pdf_copy(source, target, dpi=96)

    assert estimated
    assert target.is_file()


def test_deskew_rejects_large_angles_without_touching_source(tmp_path):
    source = tmp_path / "source.pdf"
    original = _one_page_pdf(source)

    with pytest.raises(ValueError, match="between -15"):
        P.deskew_pdf_copy(source, tmp_path / "bad.pdf", 30)

    assert source.read_bytes() == original


def test_review_usability_settings_have_safe_defaults():
    assert D.DEFAULT_SETTINGS["review_auto_advance"] is True
    assert D.DEFAULT_SETTINGS["preview_in_dialog"] is True
    assert D.DEFAULT_SETTINGS["ui_text_size"] == "normal"
