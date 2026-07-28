from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MemoryVisibility = Literal["private", "workspace"]


class MemoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    workspace_id: UUID
    owner_id: UUID
    conversation_id: UUID | None = None
    source_message_id: UUID | None = None
    content: str
    source_type: Literal["explicit_user", "approved"]
    source_excerpt: str
    confidence: float = Field(ge=0.9, le=1)
    visibility: MemoryVisibility
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    can_delete: bool


class MemoryPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MemoryItem]
    next_cursor: str | None = None


class MemoryDeleted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    deleted: bool
