from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field

AgentNode = Literal[
    "supervisor", "planner", "retrieval", "synthesis", "writer", "reviewer", "complete"
]


class PlannedSubtask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^T[1-5]$")
    objective: str = Field(min_length=1, max_length=500)
    query: str = Field(min_length=1, max_length=1000)


class RetrievalToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    document_ids: list[str] | None = Field(default=None, max_length=100)
    limit: int = Field(default=6, ge=1, le=10)


class AgentState(TypedDict):
    run_id: str
    workspace_id: str
    actor_id: str
    request_id: str
    question: str
    document_ids: list[str] | None
    step_count: int
    started_at: float
    resume_node: AgentNode
    route_reason: str
    conversation_id: NotRequired[str]
    memory_context: NotRequired[str]
    plan: NotRequired[list[dict[str, object]]]
    evidence: NotRequired[list[dict[str, object]]]
    retrieval_trace_ids: NotRequired[list[str]]
    context: NotRequired[str]
    draft: NotRequired[str]
    answer: NotRequired[str]
    citation_ids: NotRequired[list[str]]
    coverage: NotRequired[float]
    review_score: NotRequired[float]
    answer_status: NotRequired[str]


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    answer_status: Literal["grounded", "insufficient_evidence"]
    confidence: float = Field(ge=0, le=1)
    evidence: list[dict[str, object]]
    citation_ids: list[str]
    retrieval_trace_ids: list[str]
    step_count: int = Field(ge=0, le=8)
