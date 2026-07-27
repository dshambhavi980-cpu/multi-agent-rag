import pytest

from app.services.chunking import ChunkingConfig, chunk_pages
from app.services.document_parser import ParsedPage


@pytest.mark.parametrize("strategy", ["fixed", "recursive", "heading_recursive"])
def test_strategies_preserve_exact_source_spans(strategy: str) -> None:
    content = "# First\n\n" + ("alpha beta. " * 80) + "\n# Second\n\nfinal text"
    page = ParsedPage(3, content)
    chunks = chunk_pages(
        [page],
        ChunkingConfig(strategy=strategy, target_chars=300),  # type: ignore[arg-type]
    )

    assert len(chunks) > 1
    for index, chunk in enumerate(chunks):
        assert chunk.chunk_index == index
        assert content[chunk.char_start : chunk.char_end] == chunk.content
        assert chunk.page_start == chunk.page_end == 3
    if strategy == "heading_recursive":
        assert {chunk.section_heading for chunk in chunks} == {"First", "Second"}


def test_overlap_is_explicit_and_config_is_validated() -> None:
    content = "word " * 180
    chunks = chunk_pages(
        [ParsedPage(1, content)],
        ChunkingConfig(strategy="fixed", target_chars=300, overlap_chars=20),
    )
    assert chunks[1].char_start < chunks[0].char_end

    with pytest.raises(ValueError, match="target_chars"):
        ChunkingConfig(target_chars=100)
    with pytest.raises(ValueError, match="overlap_chars"):
        ChunkingConfig(target_chars=300, overlap_chars=300)


def test_empty_pages_produce_no_chunks() -> None:
    assert chunk_pages([ParsedPage(1, "")]) == []
