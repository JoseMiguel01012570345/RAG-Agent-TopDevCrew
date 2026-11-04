import pytest

from app.services.uploads import UploadRejected, validate_upload


def test_accepts_utf8_text():
    name, media = validate_upload("acta.txt", "text/plain", b"ascensor", 1000)
    assert name == "acta.txt"
    assert media == "text/plain"


def test_accepts_pdf_magic_bytes():
    name, media = validate_upload("acta.PDF", "application/pdf", b"%PDF-1.7\n", 1000)
    assert name == "acta.PDF"
    assert media == "application/pdf"


def test_strips_directory_from_filename():
    name, _media = validate_upload("../secret/acta.txt", "text/plain", b"hola", 1000)
    assert name == "acta.txt"


@pytest.mark.parametrize(
    ("filename", "media", "data", "limit", "status"),
    [
        ("nota.txt", "text/plain", b"", 1000, 422),
        ("nota.txt", "text/plain", b"   \n", 1000, 422),
        ("nota.txt", "text/plain", "á".encode("latin-1"), 1000, 422),
        ("nota.txt", "text/plain", b"hola mundo", 4, 413),
        ("nota.pdf", "application/pdf", b"not a pdf", 1000, 422),
        ("nota.exe", "application/octet-stream", b"hello", 1000, 422),
        ("nota.txt", "text/html", b"hola", 1000, 422),
        ("", "text/plain", b"hola", 1000, 422),
    ],
)
def test_rejects_invalid_uploads(filename, media, data, limit, status):
    with pytest.raises(UploadRejected) as caught:
        validate_upload(filename, media, data, limit)
    assert caught.value.status_code == status
