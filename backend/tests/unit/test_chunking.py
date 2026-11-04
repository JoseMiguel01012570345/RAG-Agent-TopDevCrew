from app.services.chunking import chunk_document, split_page


def test_short_page_is_one_chunk():
    chunks = chunk_document([(1, "Hola mundo")], chunk_size=1000, overlap=150)
    assert len(chunks) == 1
    assert chunks[0].page == 1
    assert chunks[0].text == "Hola mundo"


def test_empty_page_is_skipped():
    chunks = chunk_document([(1, "   \n"), (2, "texto util")], chunk_size=1000, overlap=150)
    assert [(chunk.page, chunk.text) for chunk in chunks] == [(2, "texto util")]


def test_chunks_do_not_cross_pages():
    chunks = chunk_document([(1, "A" * 500), (2, "B" * 500)], chunk_size=1000, overlap=150)
    assert [chunk.page for chunk in chunks] == [1, 2]
    assert "B" not in chunks[0].text
    assert "A" not in chunks[1].text


def test_long_text_overlaps_and_respects_size():
    parts = split_page("x" * 2500, chunk_size=1000, overlap=150)
    assert len(parts) >= 3
    assert all(len(part) <= 1000 for part in parts)
    assert parts[0][-150:] == parts[1][:150]


def test_paragraphs_pack_with_overlap_when_they_do_not_fit():
    first = "A" * 600
    second = "B" * 600
    parts = split_page(f"{first}\n\n{second}", chunk_size=1000, overlap=150)
    assert len(parts) == 2
    assert parts[0] == first
    assert parts[1].startswith("A" * 150)
    assert parts[1].endswith(second)
    assert len(parts[1]) <= 1000
