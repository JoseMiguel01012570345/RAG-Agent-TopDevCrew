import pytest

from app.services.parsing import PermanentIngestionError, parse_document
from tests.pdfutil import build_pdf


def test_text_file_is_page_one():
    pages = parse_document(b"Acta del ascensor", "text/plain", "acta.txt", 80)
    assert pages == [(1, "Acta del ascensor")]


def test_pdf_keeps_page_numbers():
    payload = build_pdf(["jardin", "caldera"])
    pages = parse_document(payload, "application/pdf", "acta.pdf", 80)
    assert pages[0][0] == 1
    assert pages[1][0] == 2
    assert "jardin" in pages[0][1]
    assert "caldera" in pages[1][1]


def test_blank_pdf_has_no_text_layer():
    with pytest.raises(PermanentIngestionError) as caught:
        parse_document(build_pdf([""]), "application/pdf", "vacio.pdf", 80)
    assert caught.value.code == "no_text_layer"


def test_corrupt_pdf_is_permanent():
    with pytest.raises(PermanentIngestionError) as caught:
        parse_document(b"%PDF-1.4 esto no es un pdf", "application/pdf", "roto.pdf", 80)
    assert caught.value.code == "corrupt_pdf"


def test_too_many_pages_is_rejected_before_ocr_fallback():
    with pytest.raises(PermanentIngestionError) as caught:
        parse_document(build_pdf(["a", "b"]), "application/pdf", "largo.pdf", 1)
    assert caught.value.code == "too_many_pages"
