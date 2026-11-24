from pathlib import Path

from pdfsorter_read import (compare_extracted_pages, extract,
                            search_extracted_pages)


def test_archive_search_returns_case_insensitive_page_hits_and_snippets():
    hits = search_extracted_pages(
        Path("archive/report.pdf"),
        "page one\fThe INVOICE number is 42\fother page",
        "invoice", context=8)

    assert hits == [{
        "path": str(Path("archive/report.pdf")), "page": 2,
        "snippet": "The INVOICE number…",
    }]


def test_archive_search_handles_empty_query_and_caps_repeated_hits():
    assert search_extracted_pages(Path("a.pdf"), "invoice", "  ") == []
    hits = search_extracted_pages(Path("a.pdf"), "x " * 510, "x", context=0)
    assert len(hits) == 500


def test_page_comparison_reports_modified_added_and_removed_pages():
    changes = compare_extracted_pages(
        "same page\fold copy", "same page\fnew copy\fadded page")

    assert changes == [
        {"page": 2, "kind": "changed", "before": "old copy",
         "after": "new copy"},
        {"page": 3, "kind": "added", "before": "", "after": "added page"},
    ]


def test_page_comparison_caps_detail_but_not_page_boundaries():
    changes = compare_extracted_pages("a\fb\fc", "x\fy\fz", max_changes=2)
    assert [item["page"] for item in changes] == [1, 2]


def test_pdf_text_extraction_preserves_page_boundaries_for_search(tmp_path):
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    path = tmp_path / "two-pages.pdf"
    doc = pymupdf.open()
    first = doc.new_page()
    first.insert_text((72, 72), "First page only")
    second = doc.new_page()
    second.insert_text((72, 72), "Reference invoice ZX-42")
    doc.save(path)
    doc.close()

    extraction = extract(path, ocr_enabled=False)
    hits = search_extracted_pages(path, extraction.text, "invoice zx-42")

    assert "\f" in extraction.text
    assert [(hit["page"], hit["snippet"]) for hit in hits] == [
        (2, "Reference invoice ZX-42")]
