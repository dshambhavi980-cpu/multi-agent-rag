from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ContentType = Literal[
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/html",
]
DocumentStatus = Literal[
    "uploaded",
    "queued",
    "processing",
    "ready",
    "failed",
    "quarantined",
]
IngestionJobStatus = Literal[
    "queued",
    "processing",
    "completed",
    "failed",
    "quarantined",
]
ChunkStrategy = Literal["fixed", "recursive", "heading_recursive"]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-fA-F0-9]{64}$")]


class CreateUploadUrlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    content_type: ContentType
    size_bytes: int = Field(ge=1, le=26_214_400)
    sha256: Sha256

    @field_validator("sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        return value.lower()


class CreateUploadUrlResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: UUID
    object_path: str
    signed_url: str
    upload_token: str
    expires_at: datetime


class CompleteUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: UUID
    object_path: str = Field(min_length=1, max_length=1024)
    sha256: Sha256
    title: str | None = Field(default=None, max_length=255)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        return value.lower()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized = [tag.strip() for tag in value if tag.strip()]
        if any(len(tag) > 50 for tag in normalized):
            raise ValueError("Tags cannot exceed 50 characters.")
        return list(dict.fromkeys(normalized))


class Document(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    workspace_id: UUID
    uploaded_by: UUID
    object_path: str
    filename: str
    title: str | None = None
    content_type: ContentType
    size_bytes: int
    sha256: str
    status: DocumentStatus
    processing_version: int
    index_version: int = 0
    target_index_version: int = 1
    chunk_strategy: ChunkStrategy | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    indexed_at: datetime | None = None
    page_count: int | None = None
    chunk_count: int
    tags: list[str]
    failure_code: str | None = None
    created_at: datetime
    updated_at: datetime


class IngestionJob(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    workspace_id: UUID
    document_id: UUID
    status: IngestionJobStatus
    stage: str | None = None
    progress: float
    attempt: int
    max_attempts: int
    error_code: str | None = None
    error_detail: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class IngestionAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: Document
    job: IngestionJob | None
    deduplicated: bool


class DocumentPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Document]
    next_cursor: str | None = None


class DocumentSourceAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    expires_at: datetime


class ReindexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: ChunkStrategy | None = None
