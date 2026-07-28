from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AnswerStatus = Literal["grounded", "insufficient_evidence", "failed"]
RunStatus = Literal[
    "accepted",
    "running",
    "cancelling",
    "cancelled",
    "completed",
    "failed",
    "timed_out",
]


class Citation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    citation_id: str = Field(pattern=r"^C[1-9][0-9]*$")
    document_id: UUID
    chunk_id: UUID
    label: str
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    quote: str = Field(max_length=1000)
    source_url: str


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    workspace_id: UUID
    owner_id: UUID
    title: str | None = None
    summary: str | None = None
    summary_through_message_id: UUID | None = None
    summary_message_count: int = Field(default=0, ge=0)
    summary_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)


class ConversationPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Conversation]
    next_cursor: str | None = None


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    answer_status: AnswerStatus | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime


class ConversationDetail(Conversation):
    messages: list[Message]


class CreateMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=12000)
    document_ids: list[UUID] | None = Field(default=None, max_length=100)
    force_mode: Literal["auto", "simple", "agentic"] = "auto"


class RunAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    message_id: UUID
    status: RunStatus
    events_url: str


class Run(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    conversation_id: UUID
    status: RunStatus
    mode: Literal["simple", "agentic"]
    current_node: str | None = None
    step_count: int = Field(ge=0, le=8)
    confidence: float | None = Field(default=None, ge=0, le=1)
    answer_status: AnswerStatus | None = None
    output_message_id: UUID | None = None
    error: dict[str, object] | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class OperationAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: str
