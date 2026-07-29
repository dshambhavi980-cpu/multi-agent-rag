from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EvaluationVariant = Literal[
    "keyword_only",
    "dense_only",
    "hybrid",
    "simple_rag",
    "agentic",
]
EvaluationStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


def default_variants() -> list[EvaluationVariant]:
    return ["keyword_only", "dense_only", "hybrid"]


class CreateEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: Literal["phase12-reviewed-v1"] = "phase12-reviewed-v1"
    variants: list[EvaluationVariant] = Field(
        default_factory=default_variants,
        min_length=1,
        max_length=5,
    )
    max_cases: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def unique_variants(self) -> "CreateEvaluationRequest":
        if len(self.variants) != len(set(self.variants)):
            raise ValueError("Evaluation variants must be unique.")
        return self


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    case_id: str
    category: str
    variant: EvaluationVariant
    status: Literal["passed", "failed", "error"]
    metrics: dict[str, float]
    latency_ms: float = Field(ge=0)
    model_calls: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    failure_code: str | None = None
    created_at: datetime


class EvaluationRun(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    workspace_id: UUID
    suite: str
    suite_version: int = Field(ge=1)
    variants: list[EvaluationVariant]
    status: EvaluationStatus
    case_count: int = Field(ge=0, le=50)
    metrics: dict[str, float] = Field(default_factory=dict)
    gate_passed: bool | None = None
    gate_failures: list[str] = Field(default_factory=list)
    error: dict[str, object] | None = None
    created_at: datetime
    completed_at: datetime | None = None
    results: list[EvaluationResult] = Field(default_factory=list)


class EvaluationPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EvaluationRun]
    next_cursor: str | None = None


class EvaluationSuiteSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: str
    version: int
    reviewed_by: str
    reviewed_at: date
    case_count: int = Field(ge=50)
    categories: dict[str, int]
    thresholds: dict[str, float]
