from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ReadinessStatus = Literal["ready", "degraded", "unavailable"]


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    time: datetime
    cold_start: bool


class Readiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReadinessStatus
    dependencies: dict[str, ReadinessStatus]


class Version(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    commit: str
    environment: str
