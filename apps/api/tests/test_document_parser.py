import fitz  # type: ignore[import-untyped]
import pytest

from app.services.document_parser import DocumentParseError, parse_document


def test_parses_markdown_with_provenance_and_chunks() -> None:
    parsed = parse_document(
        ("# Heading\n\n" + "word " * 700).encode(),
        "text/markdown",
    )

    assert parsed.pages[0].page_number == 1
    assert parsed.chunks[0].section_heading == "Heading"
    assert len(parsed.chunks) > 1
    assert str(parsed.pages_json()[0]["content"]).startswith("# Heading")
    assert parsed.chunks_json()[0]["char_start"] == 0


def test_parses_html_without_scripts() -> None:
    parsed = parse_document(
        b"<h2>Title</h2><script>bad()</script><p>Hello   world</p>",
        "text/html",
    )

    assert "bad()" not in parsed.pages[0].content
    assert "# Title" in parsed.pages[0].content
    assert "Hello world" in parsed.pages[0].content


def test_parses_pdf_pages() -> None:
    document = fitz.open()
    document.new_page().insert_text((72, 72), "First page")
    document.new_page().insert_text((72, 72), "Second page")
    payload = document.tobytes()
    document.close()

    parsed = parse_document(payload, "application/pdf")

    assert [page.page_number for page in parsed.pages] == [1, 2]
    assert parsed.chunks[1].page_start == 2


@pytest.mark.parametrize(
    ("payload", "content_type", "code"),
    [
        (b"", "text/plain", "EMPTY_DOCUMENT"),
        (b"\xff", "text/plain", "INVALID_TEXT_ENCODING"),
        (b"a\x00b", "text/plain", "MALFORMED_TEXT"),
        (b"not a pdf", "application/pdf", "MALFORMED_PDF"),
        (b"  \n\n ", "text/plain", "NO_EXTRACTABLE_TEXT"),
    ],
)
def test_rejects_malformed_documents(payload: bytes, content_type: str, code: str) -> None:
    with pytest.raises(DocumentParseError) as exc_info:
        parse_document(payload, content_type)  # type: ignore[arg-type]
    assert exc_info.value.code == code


def test_rejects_encrypted_pdf() -> None:
    document = fitz.open()
    document.new_page().insert_text((72, 72), "secret")
    payload = document.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="user",
    )
    document.close()

    with pytest.raises(DocumentParseError) as exc_info:
        parse_document(payload, "application/pdf")
    assert exc_info.value.code == "ENCRYPTED_PDF"
