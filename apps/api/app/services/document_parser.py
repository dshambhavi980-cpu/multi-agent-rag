import re
from dataclasses import asdict, dataclass

import fitz  # type: ignore[import-untyped]
from bs4 import BeautifulSoup

from app.models.documents import ContentType

MAX_PAGES = 1000
CHUNK_CHARS = 2000
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")


class DocumentParseError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ParsedPage:
    page_number: int
    content: str


@dataclass(frozen=True)
class ParsedChunk:
    chunk_index: int
    content: str
    page_start: int
    page_end: int
    section_heading: str | None
    char_start: int
    char_end: int
    token_count: int


@dataclass(frozen=True)
class ParsedDocument:
    pages: list[ParsedPage]
    chunks: list[ParsedChunk]

    def pages_json(self) -> list[dict[str, object]]:
        return [asdict(page) for page in self.pages]

    def chunks_json(self) -> list[dict[str, object]]:
        return [asdict(chunk) for chunk in self.chunks]


def _normalize(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.replace("\r", "\n").split("\n")]
    output: list[str] = []
    blank = False
    for line in lines:
        if line:
            output.append(line)
            blank = False
        elif output and not blank:
            output.append("")
            blank = True
    return "\n".join(output).strip()


def _decode(data: bytes) -> str:
    if b"\x00" in data:
        raise DocumentParseError("MALFORMED_TEXT", "Text documents cannot contain null bytes.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentParseError("INVALID_TEXT_ENCODING", "Text must use UTF-8 encoding.") from exc


def _pdf_pages(data: bytes) -> list[ParsedPage]:
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise DocumentParseError("MALFORMED_PDF", "The PDF could not be opened.") from exc
    try:
        if document.needs_pass:
            raise DocumentParseError("ENCRYPTED_PDF", "Encrypted PDFs are not supported.")
        if document.page_count > MAX_PAGES:
            raise DocumentParseError("PAGE_LIMIT_EXCEEDED", "The PDF exceeds the 1,000 page limit.")
        return [
            ParsedPage(index + 1, _normalize(page.get_text("text")))
            for index, page in enumerate(document)
        ]
    except DocumentParseError:
        raise
    except Exception as exc:
        raise DocumentParseError(
            "MALFORMED_PDF", "The PDF content could not be extracted."
        ) from exc
    finally:
        document.close()


def _text_pages(data: bytes, content_type: ContentType) -> list[ParsedPage]:
    text = _decode(data)
    if content_type == "text/html":
        try:
            soup = BeautifulSoup(text, "html.parser")
            for node in soup(["script", "style", "noscript"]):
                node.decompose()
            for heading in soup.find_all(re.compile(r"^h[1-6]$")):
                heading.string = f"\n# {heading.get_text(' ', strip=True)}\n"
            text = soup.get_text("\n")
        except Exception as exc:
            raise DocumentParseError("MALFORMED_HTML", "The HTML could not be parsed.") from exc
    return [ParsedPage(1, _normalize(text))]


def _chunks(pages: list[ParsedPage]) -> list[ParsedChunk]:
    chunks: list[ParsedChunk] = []
    for page in pages:
        content = page.content
        position = 0
        heading: str | None = None
        while position < len(content):
            end = min(position + CHUNK_CHARS, len(content))
            if end < len(content):
                boundary = content.rfind("\n", position, end)
                if boundary > position + CHUNK_CHARS // 2:
                    end = boundary
            piece = content[position:end].strip()
            for line in piece.splitlines():
                match = HEADING.match(line)
                if match:
                    heading = match.group(1)
            if piece:
                start = content.find(piece, position, end + 1)
                chunks.append(
                    ParsedChunk(
                        chunk_index=len(chunks),
                        content=piece,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        section_heading=heading,
                        char_start=start,
                        char_end=start + len(piece),
                        token_count=max(1, len(piece.split())),
                    )
                )
            position = max(end, position + 1)
    return chunks


def parse_document(data: bytes, content_type: ContentType) -> ParsedDocument:
    if not data:
        raise DocumentParseError("EMPTY_DOCUMENT", "The document is empty.")
    pages = (
        _pdf_pages(data) if content_type == "application/pdf" else _text_pages(data, content_type)
    )
    if not any(page.content for page in pages):
        raise DocumentParseError(
            "NO_EXTRACTABLE_TEXT", "The document contains no extractable text."
        )
    return ParsedDocument(pages=pages, chunks=_chunks(pages))
