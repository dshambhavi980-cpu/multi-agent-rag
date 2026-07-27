from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str | None = None
    role: Literal["authenticated"]


class WorkspaceAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    user_id: UUID
    role: Literal["owner", "reviewer", "member"]
