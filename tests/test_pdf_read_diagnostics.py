import io
import logging
import sys
import threading
import warnings

import pytest
from PIL import Image

import pdfsorter as P
import pdfsorter_read as R


def test_pdf_engine_log_warnings_are_grouped_and_counted(tmp_path, monkeypatch):
    path = tmp_path / "recoverable.pdf"
    path.write_bytes(b"not parsed by the fake backend")
    logger = logging.getLogger("pypdf._reader")
    old_level = logger.level
    logger.setLevel(logging.WARNING)

    def read_with_duplicate_warnings(_path, _max_pages):
        logger.warning("EOF marker not found")
        logger.warning("EOF marker not found")
        return "läsbar PDF-text " * 20, {}, 1, 1

    monkeypatch.setattr(R, "has_pymupdf", lambda: True)
    monkeypatch.setattr(R, "has_pypdf", lambda: False)
    monkeypatch.setattr(R, "has_pdfminer", lambda: False)
    monkeypatch.setattr(R, "_x_pymupdf", read_with_duplicate_warnings)
    try:
        result = R.extract(path, ocr_enabled=False)
    finally:
        logger.setLevel(old_level)

    assert result.text
    assert result.pdf_diagnostics == [{
        "engine": "pypdf", "level": "warning",
        "message": "EOF marker not found", "count": 2,
    }]


def test_pdf_diagnostics_are_summarized_without_losing_file_readability(
        tmp_path, monkeypatch):
    path = tmp_path / "recoverable.pdf"
    path.write_bytes(b"PDF bytes")
    ext = R.Extraction(
        path=path, text="text from fallback engine", pdf_diagnostics=[
            {"engine": "pdfminer", "level": "warning",
             "message": "Ignoring final token", "count": 4},
            {"engine": "pypdf", "level": "error",
             "message": "bad xref repaired by fallback", "count": 1},
        ])
    logged = []
    engine = object.__new__(P.SortEngine)
    engine.settings = {}
    engine.rules = object()
    engine.lock = threading.RLock()
    engine.log = lambda message, level="info": logged.append((message, level))

    monkeypatch.setattr(P, "read_pdf", lambda *_args, **_kwargs: ext)
    monkeypatch.setattr(P, "_ignore_reason", lambda *_args: None)
    monkeypatch.setattr(
        P, "decide",
        lambda _rules, extraction, _settings: P.Decision(
            extraction.path, extraction, [], "ignored", "test"))

    P.SortEngine.analyze(engine, path)

    assert any("text kunde ändå läsas" in message and "4 varningar" in message
               and "1 reservmotorfel" in message
               and level == "warn" for message, level in logged)
    assert any("upprepades 4 gånger" in message for message, _level in logged)
    assert ext.pdf_diagnostics == []


def test_pdf_engine_warnings_outside_extract_do_not_spam_stderr(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    root_logger = logging.getLogger()
    old_handlers = list(root_logger.handlers)
    root_logger.handlers.clear()
    try:
        R._configure_pdf_engine_loggers()
        logging.getLogger("pdfminer.pdfinterp").warning(
            "Ignoring final token of odd-length line")
        logging.getLogger("pypdf._reader").warning("EOF marker not found")
    finally:
        root_logger.handlers[:] = old_handlers

    assert buf.getvalue() == ""


def test_open_image_quiet_suppresses_decompression_bomb_warning_not_error(
        tmp_path, monkeypatch):
    img_path = tmp_path / "large.png"
    Image.new("RGB", (64, 64), "white").save(img_path)  # 4096 px

    # Warning threshold: MAX_IMAGE_PIXELS < 4096 <= 2 * MAX_IMAGE_PIXELS
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 3000)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with R._open_image_quiet(img_path) as im:
            assert im.size == (64, 64)
    assert not any(
        issubclass(w.category, Image.DecompressionBombWarning) for w in caught
    )

    # Error threshold: 4096 > 2 * MAX_IMAGE_PIXELS
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(Image.DecompressionBombError):
        R._open_image_quiet(img_path)
