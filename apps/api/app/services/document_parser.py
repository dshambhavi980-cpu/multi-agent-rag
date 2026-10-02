import re
from dataclasses import asdict, dataclass, field

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
class ParsedFigure:
    figure_id: str
    page_number: int
    image_bytes: bytes
    image_ext: str
    width: int
    height: int
    caption: str
    context_snippet: str


@dataclass(frozen=True)
class ParsedDocument:
    pages: list[ParsedPage]
    chunks: list[ParsedChunk]
    figures: list[ParsedFigure] = field(default_factory=list)

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


def _pdf_pages_and_figures(data: bytes) -> tuple[list[ParsedPage], list[ParsedFigure]]:
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise DocumentParseError("MALFORMED_PDF", "The PDF could not be opened.") from exc
    try:
        if document.needs_pass:
            raise DocumentParseError("ENCRYPTED_PDF", "Encrypted PDFs are not supported.")
        if document.page_count > MAX_PAGES:
            raise DocumentParseError("PAGE_LIMIT_EXCEEDED", "The PDF exceeds the 1,000 page limit.")

        pages: list[ParsedPage] = []
        figures: list[ParsedFigure] = []

        for index, page in enumerate(document):
            page_num = index + 1
            text = _normalize(page.get_text("text"))
            pages.append(ParsedPage(page_num, text))

            try:
                image_list = page.get_images(full=True)
                blocks = page.get_text("blocks")
                for img_idx, img_info in enumerate(image_list):
                    xref = img_info[0]
                    base_image = document.extract_image(xref)
                    w, h = base_image.get("width", 0), base_image.get("height", 0)
                    if w < 250 or h < 150:
                        continue
                    ext = base_image.get("ext", "png")
                    raw_bytes = base_image.get("image", b"")
                    if not raw_bytes:
                        continue

                    caption = f"Figure on Page {page_num}"
                    snippet = ""
                    figure_candidates = [
                        b[4].strip()
                        for b in blocks
                        if len(b) > 4
                        and isinstance(b[4], str)
                        and ("figure" in b[4].lower() or "diagram" in b[4].lower())
                    ]
                    if figure_candidates:
                        first_line = figure_candidates[0].split("\n")[0].strip()
                        caption = first_line[:120]
                        snippet = figure_candidates[0][:300]
                    else:
                        for b in blocks:
                            if len(b) > 4 and isinstance(b[4], str) and b[4].strip():
                                lines = [ln.strip() for ln in b[4].split("\n") if ln.strip()]
                                if lines and len(lines[0]) < 80:
                                    caption = f"{lines[0]} (Page {page_num})"
                                    snippet = b[4][:200]
                                    break

                    figure_id = f"fig_p{page_num}_{img_idx + 1}"
                    figures.append(
                        ParsedFigure(
                            figure_id=figure_id,
                            page_number=page_num,
                            image_bytes=raw_bytes,
                            image_ext=ext,
                            width=w,
                            height=h,
                            caption=caption,
                            context_snippet=snippet or caption,
                        )
                    )
            except Exception:
                continue

        return pages, figures
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
    if content_type == "application/pdf":
        pages, figures = _pdf_pages_and_figures(data)
    else:
        pages = _text_pages(data, content_type)
        figures = []
    if not any(page.content for page in pages):
        raise DocumentParseError(
            "NO_EXTRACTABLE_TEXT", "The document contains no extractable text."
        )
    return ParsedDocument(pages=pages, chunks=_chunks(pages), figures=figures)
