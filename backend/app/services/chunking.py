import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    page: int
    text: str


def chunk_document(
    pages: list[tuple[int, str]],
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[TextChunk]:
    if chunk_size < 1:
        raise ValueError("chunk_size debe ser positivo")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap debe ser menor que chunk_size")
    chunks: list[TextChunk] = []
    for page, text in pages:
        for piece in split_page(text, chunk_size, overlap):
            chunks.append(TextChunk(page=page, text=piece))
    return chunks


def split_page(text: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    atoms: list[str] = []
    for paragraph in paragraphs:
        atoms.extend(_split_long(paragraph, chunk_size, overlap))
    return _pack(atoms, chunk_size, overlap)


def _split_long(paragraph: str, chunk_size: int, overlap: int) -> list[str]:
    if len(paragraph) <= chunk_size:
        return [paragraph]
    step = max(chunk_size - overlap, 1)
    parts: list[str] = []
    start = 0
    while start < len(paragraph):
        end = min(start + chunk_size, len(paragraph))
        parts.append(paragraph[start:end])
        if end >= len(paragraph):
            break
        start += step
    return parts


def _pack(atoms: list[str], chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for atom in atoms:
        if not current:
            current = atom
            continue
        joined = f"{current}\n\n{atom}"
        if len(joined) <= chunk_size:
            current = joined
            continue
        chunks.append(current)
        tail = current[-overlap:].strip() if overlap else ""
        candidate = f"{tail}\n\n{atom}" if tail else atom
        current = candidate if tail and len(candidate) <= chunk_size else atom
    if current:
        chunks.append(current)
    return chunks
