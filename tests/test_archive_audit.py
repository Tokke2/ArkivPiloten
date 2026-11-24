from pathlib import Path
from types import SimpleNamespace

import pdfsorter as P


def test_low_memory_mode_caps_parallel_pdf_reads(monkeypatch):
    monkeypatch.setattr(P.os, "cpu_count", lambda: 64)
    assert P.processing_worker_count({"low_memory_mode": True}) == 2
    assert P.processing_worker_count({"low_memory_mode": False}) == 8
    assert P.processing_batch_size({"low_memory_mode": True}, 2, 10_000) == 4
    assert P.processing_batch_size({"low_memory_mode": False}, 8, 10_000) == 10_000
    assert P.processing_batch_size({"low_memory_mode": True}, 2, 1) == 1


def test_archive_audit_is_read_only_and_flags_exact_duplicates(tmp_path, monkeypatch):
    first = tmp_path / "2025" / "report.pdf"
    second = tmp_path / "2026" / "report.pdf"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"same bytes")
    second.write_bytes(b"same bytes")
    monkeypatch.setattr(P, "pdf_looks_complete", lambda _path: True)
    monkeypatch.setattr(P, "extract", lambda path, **_kw: SimpleNamespace(
        error="", page_count=1, text="searchable text"))

    report = P.audit_archive([first, second])

    kinds = {issue["kind"] for issue in report["issues"]}
    assert report["checked"] == 2
    assert "Identiska PDF-filer" in kinds
    assert "Samma filnamn på flera platser" in kinds
    assert first.read_bytes() == second.read_bytes() == b"same bytes"


def test_archive_audit_separates_damaged_and_scanned_documents(
        tmp_path, monkeypatch):
    damaged = tmp_path / "damaged.pdf"
    scanned = tmp_path / "scanned.pdf"
    damaged.write_bytes(b"not a complete pdf")
    scanned.write_bytes(b"complete pdf placeholder")
    monkeypatch.setattr(P, "pdf_looks_complete",
                        lambda path: path.name == "scanned.pdf")
    monkeypatch.setattr(P, "extract", lambda _path, **_kw: SimpleNamespace(
        error="", page_count=2, text=""))

    report = P.audit_archive([damaged, scanned])

    assert [(item["kind"], Path(item["path"]).name)
            for item in report["issues"]] == [
        ("PDF verkar ofullständig", "damaged.pdf"),
        ("Saknar sökbart textlager", "scanned.pdf"),
    ]


def test_archive_audit_reports_empty_folders_without_deleting_them(tmp_path):
    empty = tmp_path / "empty category" / "2024"
    empty.mkdir(parents=True)

    report = P.audit_archive([], root=tmp_path)

    assert [(issue["kind"], issue["path"])
            for issue in report["issues"]] == [("Tom mapp", str(empty))]
    assert empty.is_dir()


def test_archive_audit_reports_unreadable_pdfs(tmp_path, monkeypatch):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"valid-looking placeholder")
    monkeypatch.setattr(P, "pdf_looks_complete", lambda _path: True)
    monkeypatch.setattr(P, "extract", lambda *_a, **_k: SimpleNamespace(
        error="password required", page_count=0, text=""))

    report = P.audit_archive([path])

    assert report["issues"][0]["kind"] == "PDF kunde inte öppnas"
    assert "password" in report["issues"][0]["details"]
