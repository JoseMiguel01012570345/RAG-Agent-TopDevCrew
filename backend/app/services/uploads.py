import re
from pathlib import Path

MAX_FILENAME_LENGTH = 255
PDF_TYPES = {"", "application/pdf", "application/octet-stream", "binary/octet-stream"}
TEXT_TYPES = {"", "text/plain", "application/octet-stream", "text/utf-8"}


class UploadRejected(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def validate_upload(
    filename: str | None,
    content_type: str | None,
    data: bytes,
    max_bytes: int,
) -> tuple[str, str]:
    if filename is None or not filename.strip():
        raise UploadRejected(422, "El archivo no tiene nombre")
    name = Path(filename).name.replace("\n", " ").replace("\r", " ").strip()
    if not name or name in {".", ".."}:
        raise UploadRejected(422, "Nombre de archivo inválido")
    if len(name) > MAX_FILENAME_LENGTH:
        raise UploadRejected(422, "El nombre supera 255 caracteres")
    if not data:
        raise UploadRejected(422, "El archivo está vacío")
    if len(data) > max_bytes:
        raise UploadRejected(413, "El archivo supera el máximo de 20 MB")

    extension = Path(name).suffix.lower()
    media = (content_type or "").split(";")[0].strip().lower()
    if extension == ".pdf":
        if media not in PDF_TYPES:
            raise UploadRejected(422, "Tipo de contenido no permitido para PDF")
        if not data.startswith(b"%PDF"):
            raise UploadRejected(422, "El archivo no es un PDF válido")
        return name, "application/pdf"
    if extension == ".txt":
        if media not in TEXT_TYPES:
            raise UploadRejected(422, "Tipo de contenido no permitido para texto")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UploadRejected(422, "El texto debe estar en UTF-8") from exc
        if not text.strip():
            raise UploadRejected(422, "El archivo de texto está vacío")
        return name, "text/plain"
    raise UploadRejected(422, "Solo se aceptan archivos PDF o texto (.pdf, .txt)")


USER_ID_RE = re.compile(r"[A-Za-z0-9._@-]{1,120}")
