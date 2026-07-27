from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Problem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int
    code: str
    request_id: UUID
    detail: str | None = None
    instance: str | None = None
    retryable: bool = False
    fields: dict[str, list[str]] | None = None
