import pymupdf

TEXT_CHAR_LIMIT = 320_000


class PermanentIngestionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_document(
    content: bytes,
    content_type: str,
    filename: str,
    max_pages: int,
) -> list[tuple[int, str]]:
    if content_type == "text/plain" or filename.lower().endswith(".txt"):
        return _parse_text(content)
    return _parse_pdf(content, max_pages)


def _parse_text(content: bytes) -> list[tuple[int, str]]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PermanentIngestionError("corrupt_text", "El texto no es UTF-8.") from exc
    if len(text) > TEXT_CHAR_LIMIT:
        raise PermanentIngestionError(
            "too_many_pages",
            "El texto supera el tamaño equivalente al máximo de páginas del MVP.",
        )
    return [(1, text)]


def _parse_pdf(content: bytes, max_pages: int) -> list[tuple[int, str]]:
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise PermanentIngestionError(
            "corrupt_pdf",
            "El PDF está dañado y no se pudo leer.",
        ) from exc
    try:
        page_count = document.page_count
        if page_count <= 0:
            raise PermanentIngestionError("corrupt_pdf", "El PDF está dañado y no se pudo leer.")
        if page_count > max_pages:
            raise PermanentIngestionError(
                "too_many_pages",
                f"El documento supera el máximo de {max_pages} páginas.",
            )
        pages = [
            (index, page.get_text("text") or "")
            for index, page in enumerate(document, start=1)
        ]
    finally:
        document.close()
    if not any(text.strip() for _, text in pages):
        raise PermanentIngestionError(
            "no_text_layer",
            "El PDF no tiene capa de texto. Este MVP no aplica OCR.",
        )
    return pages
