from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

RetrievalMode = Literal["hybrid", "dense", "sparse"]


class RetrievalFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: list[UUID] | None = Field(default=None, max_length=20)
    created_after: datetime | None = None
    created_before: datetime | None = None
    content_types: (
        list[Literal["application/pdf", "text/plain", "text/markdown", "text/html"]] | None
    ) = Field(default=None, max_length=4)
    tags: list[str] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def validate_range(self) -> "RetrievalFilters":
        if (
            self.created_after is not None
            and self.created_before is not None
            and self.created_after >= self.created_before
        ):
            raise ValueError("created_after must be earlier than created_before.")
        if self.tags is not None:
            normalized = [tag.strip() for tag in self.tags if tag.strip()]
            if any(len(tag) > 50 for tag in normalized):
                raise ValueError("Tags cannot exceed 50 characters.")
            self.tags = list(dict.fromkeys(normalized)) or None
        return self


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    mode: RetrievalMode = "hybrid"
    limit: int = Field(default=6, ge=1, le=20)
    candidate_count: int = Field(default=30, ge=1, le=100)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)

    @model_validator(mode="after")
    def validate_candidate_count(self) -> "RetrievalRequest":
        self.query = " ".join(self.query.split())
        if not self.query:
            raise ValueError("Query cannot contain only whitespace.")
        if self.candidate_count < self.limit:
            raise ValueError("candidate_count must be at least limit.")
        return self


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    page_start: int
    page_end: int
    section_heading: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    token_count: int | None = None
    filename: str
    title: str | None = None
    content_type: str
    tags: list[str]
    document_created_at: datetime
    semantic_rank: int | None = None
    sparse_rank: int | None = None
    semantic_score: float | None = None
    sparse_score: float | None = None
    rrf_score: float
    final_rank: int


class RetrievalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: UUID
    cache_hit: bool
    embedding_cache_hit: bool
    index_fingerprint: str
    dense_candidate_count: int
    sparse_candidate_count: int
    embedding_ms: float
    database_ms: float
    total_ms: float
    items: list[RetrievalResult]
