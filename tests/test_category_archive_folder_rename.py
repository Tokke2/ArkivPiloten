from pathlib import Path

import pdfsorter as P


def _app(output: Path):
    app = object.__new__(P.App)
    app.settings = {"output_dir": str(output)}
    return app


def test_renaming_category_folder_in_app_renames_archive_tree(tmp_path):
    output = tmp_path / "archive"
    old = output / "Old Name"
    nested = old / "2025" / "Invoices"
    nested.mkdir(parents=True)
    original = nested / "invoice.pdf"
    original.write_bytes(b"keep this file")

    ok, message = P.App._rename_category_archive_folder(
        _app(output), "Old Name", "New Name")

    assert ok is True
    assert message == ""
    assert not old.exists()
    assert (output / "New Name" / "2025" / "Invoices" / "invoice.pdf").read_bytes() == b"keep this file"


def test_folder_rename_refuses_to_merge_with_existing_destination(tmp_path):
    output = tmp_path / "archive"
    old = output / "Old Name"
    old.mkdir(parents=True)
    (old / "old.pdf").write_bytes(b"old")
    new = output / "New Name"
    new.mkdir()
    (new / "new.pdf").write_bytes(b"new")

    ok, message = P.App._rename_category_archive_folder(
        _app(output), "Old Name", "New Name")

    assert ok is False
    assert "finns redan" in message
    assert (old / "old.pdf").exists()
    assert (new / "new.pdf").exists()


def test_save_can_follow_a_folder_already_renamed_in_explorer(tmp_path):
    output = tmp_path / "archive"
    already_renamed = output / "New Name"
    already_renamed.mkdir(parents=True)
    (already_renamed / "2026").mkdir()

    ok, message = P.App._rename_category_archive_folder(
        _app(output), "Old Name", "New Name")

    assert ok is True
    assert message == ""
    assert (already_renamed / "2026").is_dir()
