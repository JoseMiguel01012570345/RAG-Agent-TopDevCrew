import pymupdf


def build_pdf(pages: list[str]) -> bytes:
    document = pymupdf.open()
    try:
        for text in pages:
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text, fontsize=12, fontname="helv")
        return document.tobytes()
    finally:
        document.close()
