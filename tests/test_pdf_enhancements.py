from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pdfsorter as P
import pdfsorter_read as R
from pdfsorter_data import Rules


def test_possible_document_breaks_need_a_new_document_number():
    starts = [
        "FAKTURA\nFakturanummer: 1001\nAcme AB",
        "FAKTURA\nFakturanummer: 1001\nAcme AB\nSida 2",
        "FAKTURA\nFakturanummer: 2044\nNorthwind AB",
    ]
    assert R._possible_document_breaks(starts) == [3]
    assert R._possible_document_breaks(starts[:2]) == []


def test_extraction_cache_round_trips_page_details(tmp_path):
    ext = R.Extraction(
        path=tmp_path / "scan.pdf",
        page_starts=["FAKTURA\nFakturanummer: 1234"],
        ocr_pages=[{"page": 1, "chars": 0, "confidence": -1,
                    "preview": "", "rotation": 90}],
    )
    restored = R.Extraction.from_cache_dict(ext.path, ext.to_cache_dict())
    assert restored.page_starts == ext.page_starts
    assert restored.ocr_pages == ext.ocr_pages


def test_detailed_ocr_keeps_blank_pages_and_corrects_rotation(monkeypatch, tmp_path):
    class FakeImage:
        def __init__(self, page, rotation=0):
            self.page = page
            self.rotation = rotation
            self.closed = False

        def rotate(self, angle, expand=False):
            assert expand is True
            return FakeImage(self.page, (self.rotation + angle) % 360)

        def close(self):
            self.closed = True

    images = [FakeImage(1), FakeImage(2)]

    def osd(image, **_kwargs):
        return {"rotate": 90 if image.page == 1 else 0,
                "orientation_conf": 4.0}

    fake_tess = SimpleNamespace(
        Output=SimpleNamespace(DICT="dict"),
        pytesseract=SimpleNamespace(tesseract_cmd=""),
        image_to_osd=osd,
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_tess)
    monkeypatch.setattr(R, "tesseract_binary", lambda: None)
    monkeypatch.setattr(R, "_resolve_langs", lambda *_args: "eng")
    monkeypatch.setattr(R, "_render_pages", lambda *_args, **_kwargs: images)
    monkeypatch.setattr(R, "_preprocess", lambda image, *_args, **_kwargs: image)
    monkeypatch.setattr(
        R, "_ocr_pass",
        lambda image, *_args: (90.0, "Readable page") if image.page == 1 else (0.0, ""),
    )

    text, confidence, pages = R._run_ocr_detailed(
        tmp_path / "scan.pdf", 2, "eng", quality="standard")

    assert "Readable page" in text
    assert "\f" in text  # the blank second page is still a positional page
    assert confidence > 0
    assert pages[0]["rotation"] == 90
    assert pages[0]["chars"] > 0
    assert pages[1]["chars"] == 0
    assert pages[1]["preview"] == ""


def test_content_duplicate_is_detected_across_output_subfolders(monkeypatch, tmp_path):
    output = tmp_path / "archive"
    monkeypatch.setattr(P, "json_dir", lambda: tmp_path / "app-json")
    old = output / "Other" / "2022" / "old-name.pdf"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"identical pdf bytes")
    source = tmp_path / "incoming.pdf"
    source.write_bytes(old.read_bytes())
    prompts = []
    rules = Rules({"categories": []}, tmp_path / "rules.json")
    engine = P.SortEngine(
        rules,
        {"output_dir": str(output), "action": "copy", "on_conflict": "rename",
         "year_subfolder": False, "tag_pdf_metadata": False},
        conflict_asker=lambda src, target, kind: (
            prompts.append((src, target, kind)) or "rename"),
    )

    ok, message = engine.apply(
        P.Decision(source, P.Extraction(path=source), [], "auto"),
        "New category", [],
    )

    assert ok, message
    assert prompts == [(source, old, "content")]
    assert old.exists()  # choosing “keep both” must not delete the earlier file
    assert source.exists()
    assert (output / "New category" / source.name).exists()


def test_multiple_document_signal_forces_review_before_auto_sort(monkeypatch, tmp_path):
    source = tmp_path / "combined.pdf"
    source.write_bytes(b"pdf bytes")
    extraction = R.Extraction(
        path=source, text="FAKTURA 1001\nFAKTURA 2044",
        page_starts=["FAKTURA\nFakturanummer: 1001",
                     "FAKTURA\nFakturanummer: 2044"],
    )
    monkeypatch.setattr(P, "is_ignored_file", lambda _path: False)
    monkeypatch.setattr(P, "read_pdf", lambda *_args, **_kwargs: extraction)
    monkeypatch.setattr(
        P, "decide",
        lambda _rules, ext, _settings: P.Decision(ext.path, ext, [], "auto", "säkert"),
    )
    engine = P.SortEngine(Rules({"categories": []}, tmp_path / "rules.json"), {})

    decision = engine.analyze(source)

    assert decision.status == "ask"
    assert "börjar på sida 2" in decision.reason


def test_deskew_refines_skew_angle_below_one_degree():
    from PIL import Image, ImageDraw

    page = Image.new("L", (600, 800), 255)
    draw = ImageDraw.Draw(page)
    for y in range(100, 700, 45):
        draw.line((80, y, 520, y), fill=0, width=3)
    skewed = page.rotate(1.7, resample=Image.BICUBIC, expand=False,
                         fillcolor=255)

    correction = R._deskew_angle(skewed)

    assert -2.2 <= correction <= -1.2


def test_tagged_output_keeps_original_content_fingerprint_across_restarts(
        monkeypatch, tmp_path):
    output = tmp_path / "archive"
    app_json = tmp_path / "app-json"
    monkeypatch.setattr(P, "json_dir", lambda: app_json)
    monkeypatch.setattr(
        P, "tag_pdf_metadata",
        lambda path, _category: Path(path).write_bytes(Path(path).read_bytes() + b"tag"),
    )
    source = tmp_path / "incoming.pdf"
    source.write_bytes(b"original pdf bytes")
    first = P.SortEngine(
        Rules({"categories": []}, tmp_path / "rules1.json"),
        {"output_dir": str(output), "action": "copy", "year_subfolder": False},
        conflict_asker=lambda *_args: "rename",
    )
    ok, message = first.apply(
        P.Decision(source, R.Extraction(path=source), [], "auto"), "Sorted", [])
    assert ok, message
    stored = output / "Sorted" / source.name
    assert stored.read_bytes().endswith(b"tag")

    second_source = tmp_path / "renamed.pdf"
    second_source.write_bytes(b"original pdf bytes")
    prompts = []
    second = P.SortEngine(
        Rules({"categories": []}, tmp_path / "rules2.json"),
        {"output_dir": str(output), "action": "copy", "year_subfolder": False},
        conflict_asker=lambda src, target, kind: (
            prompts.append((src, target, kind)) or "rename"),
    )
    ok, message = second.apply(
        P.Decision(second_source, R.Extraction(path=second_source), [], "auto"),
        "Other", [],
    )
    assert ok, message
    assert prompts == [(second_source, stored, "content")]


def test_replace_keeps_old_duplicate_if_new_placement_fails(monkeypatch, tmp_path):
    output = tmp_path / "archive"
    old = output / "Old" / "old-name.pdf"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"same bytes")
    source = tmp_path / "incoming.pdf"
    source.write_bytes(old.read_bytes())
    monkeypatch.setattr(P, "json_dir", lambda: tmp_path / "app-json")
    monkeypatch.setattr(
        P, "place_file", lambda *_args, **_kwargs: (False, "disk full", None))
    engine = P.SortEngine(
        Rules({"categories": []}, tmp_path / "rules.json"),
        {"output_dir": str(output), "action": "copy", "year_subfolder": False},
        conflict_asker=lambda *_args: "replace",
    )

    ok, _message = engine.apply(
        P.Decision(source, R.Extraction(path=source), [], "auto"), "New", [])

    assert not ok
    assert old.read_bytes() == b"same bytes"
    assert source.exists()


def _make_pdf(path, pages=4):
    pymupdf = R._open_pymupdf()
    document = pymupdf.open()
    for page_no in range(1, pages + 1):
        page = document.new_page()
        page.insert_text((72, 72), f"Page {page_no}")
    document.save(path)
    document.close()


def test_split_suggestion_creates_safe_unique_copies_and_preserves_source(tmp_path):
    source = tmp_path / "bundle.pdf"
    output = tmp_path / "split"
    _make_pdf(source)

    first = P.create_pdf_split_copies(source, [3], output)
    second = P.create_pdf_split_copies(source, [3], output)

    assert [path.name for path in first] == [
        "bundle - del 1.pdf", "bundle - del 2.pdf"]
    assert [path.name for path in second] == [
        "bundle - del 1 (2).pdf", "bundle - del 2 (2).pdf"]
    pymupdf = R._open_pymupdf()
    source_doc = pymupdf.open(source)
    parts = [pymupdf.open(path) for path in first]
    try:
        assert len(source_doc) == 4
        assert [len(part) for part in parts] == [2, 2]
        assert [part[0].get_text().strip() for part in parts] == [
            "Page 1", "Page 3"]
    finally:
        source_doc.close()
        for part in parts:
            part.close()


def test_split_failure_rolls_back_created_copies_and_keeps_source(monkeypatch, tmp_path):
    source = tmp_path / "bundle.pdf"
    output = tmp_path / "split"
    _make_pdf(source)
    real_replace = P.os.replace
    replacements = 0

    def fail_second_replace(src, dst):
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("simulated write failure")
        return real_replace(src, dst)

    monkeypatch.setattr(P.os, "replace", fail_second_replace)

    try:
        P.create_pdf_split_copies(source, [3], output)
    except OSError as exc:
        assert "simulated" in str(exc)
    else:
        raise AssertionError("expected simulated failure")

    assert source.exists()
    assert list(output.iterdir()) == []
