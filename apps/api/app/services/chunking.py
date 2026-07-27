import re
from dataclasses import dataclass
from typing import Literal

from app.services.document_parser import ParsedChunk, ParsedPage

ChunkStrategy = Literal["fixed", "recursive", "heading_recursive"]
HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*$")
BOUNDARIES = ("\n\n", "\n", ". ", " ")


@dataclass(frozen=True)
class ChunkingConfig:
    strategy: ChunkStrategy = "heading_recursive"
    target_chars: int = 1800
    overlap_chars: int = 0

    def __post_init__(self) -> None:
        if not 256 <= self.target_chars <= 4000:
            raise ValueError("target_chars must be between 256 and 4000.")
        if not 0 <= self.overlap_chars < self.target_chars:
            raise ValueError("overlap_chars must be smaller than target_chars.")


def _trimmed_span(content: str, start: int, end: int) -> tuple[int, int]:
    while start < end and content[start].isspace():
        start += 1
    while end > start and content[end - 1].isspace():
        end -= 1
    return start, end


def _natural_end(content: str, start: int, target: int, limit: int) -> int:
    proposed = min(start + target, limit)
    if proposed == limit:
        return proposed
    minimum = start + target // 2
    for separator in BOUNDARIES:
        boundary = content.rfind(separator, minimum, proposed)
        if boundary >= minimum:
            return boundary + (2 if separator == ". " else len(separator))
    return proposed


def _spans(
    content: str,
    start: int,
    end: int,
    *,
    config: ChunkingConfig,
    natural: bool,
) -> list[tuple[int, int]]:
    output: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        chunk_end = (
            _natural_end(content, cursor, config.target_chars, end)
            if natural
            else min(cursor + config.target_chars, end)
        )
        trimmed = _trimmed_span(content, cursor, chunk_end)
        if trimmed[0] < trimmed[1]:
            output.append(trimmed)
        if chunk_end >= end:
            break
        cursor = max(chunk_end - config.overlap_chars, cursor + 1)
    return output


def _heading_sections(content: str) -> list[tuple[int, int, str | None]]:
    matches = list(HEADING.finditer(content))
    if not matches:
        return [(0, len(content), None)]
    sections: list[tuple[int, int, str | None]] = []
    if matches[0].start() > 0:
        sections.append((0, matches[0].start(), None))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        sections.append((match.start(), end, match.group(1).strip()))
    return sections


def chunk_pages(
    pages: list[ParsedPage],
    config: ChunkingConfig | None = None,
) -> list[ParsedChunk]:
    resolved = config or ChunkingConfig()
    chunks: list[ParsedChunk] = []
    for page in pages:
        if resolved.strategy == "heading_recursive":
            sections = _heading_sections(page.content)
        else:
            sections = [(0, len(page.content), None)]

        for section_start, section_end, heading in sections:
            spans = _spans(
                page.content,
                section_start,
                section_end,
                config=resolved,
                natural=resolved.strategy != "fixed",
            )
            for start, end in spans:
                text = page.content[start:end]
                chunks.append(
                    ParsedChunk(
                        chunk_index=len(chunks),
                        content=text,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        section_heading=heading,
                        char_start=start,
                        char_end=end,
                        token_count=max(1, len(text.split())),
                    )
                )
    return chunks
