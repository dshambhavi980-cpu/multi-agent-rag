from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AnswerStatus = Literal["grounded", "insufficient_evidence", "failed"]
RunStatus = Literal[
    "accepted",
    "running",
    "awaiting_approval",
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
    approval_id: UUID | None = None
    error: dict[str, object] | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class RunSummary(Run):
    question: str


class AgentStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    step_number: int = Field(ge=1, le=8)
    node: str
    status: Literal["succeeded", "failed", "skipped"]
    summary: str
    duration_ms: float = Field(ge=0)
    created_at: datetime


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    tool_name: str
    permission: str
    status: Literal["succeeded", "failed"]
    output_summary: dict[str, object]
    duration_ms: float = Field(ge=0)
    created_at: datetime


class RunPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RunSummary]
    next_cursor: str | None = None


class RunTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: RunSummary
    steps: list[AgentStep]
    tool_calls: list[ToolCall]


class ReplayRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["exact_snapshot", "current_configuration"]
    reason: str = Field(min_length=1, max_length=500)


class TraceEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    citation_id: str
    document_id: UUID
    label: str
    page: int | None = None
    section: str | None = None
    quote: str
    semantic_score: float | None = None
    sparse_rank: int | None = None
    rrf_score: float


class OperationalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    occurred_at: datetime
    latency_ms: float | None = None
    severity: Literal["info", "warning", "error"]
    attributes: dict[str, object]


class ObservabilityTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID | None = None
    trace_id: UUID
    run_id: UUID
    model: str
    prompt_version: str
    timings: dict[str, float]
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    token_usage_source: Literal["provider", "estimated"] | None = None
    replayed_from_run_id: UUID | None = None
    replay_mode: Literal["exact_snapshot", "current_configuration"] | None = None
    error: dict[str, object] | None = None
    evidence: list[TraceEvidence]
    events: list[OperationalEvent]


class WorkspaceObservability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_hours: int = Field(ge=1)
    total_runs: int = Field(ge=0)
    successful_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    success_rate: float = Field(ge=0, le=1)
    p95_latency_ms: float = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    active_runs: int = Field(ge=0)
    trace_count: int = Field(ge=0)
    trace_limit: int = Field(ge=1)
    retention_days: int = Field(ge=1)


class WorkspaceUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: int = Field(ge=0)
    document_bytes: int = Field(ge=0)
    ready_documents: int = Field(ge=0)
    conversations: int = Field(ge=0)
    runs: int = Field(ge=0)
    approvals: int = Field(ge=0)
    memories: int = Field(ge=0)


class OperationAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: str
