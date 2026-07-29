from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ApprovalStatus = Literal["pending", "approved", "rejected", "revision_requested", "expired"]


class Approval(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    run_id: UUID
    status: ApprovalStatus
    risk_level: Literal["low", "medium", "high", "critical"]
    reasons: list[str] = Field(min_length=1)
    proposed_output: str | None = None
    reviewer_id: UUID | None = None
    reviewer_comment: str | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ApprovalPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Approval]
    next_cursor: str | None = None


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str = Field(min_length=1, max_length=2000)
    edited_output: str | None = Field(default=None, max_length=30000)


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str = Field(min_length=1, max_length=2000)
