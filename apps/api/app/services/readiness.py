import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

ReadinessStatus = Literal["ready", "degraded", "unavailable"]
ReadinessCheck = Callable[[], Awaitable[ReadinessStatus]]


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    status: ReadinessStatus
    dependencies: dict[str, ReadinessStatus]


class ReadinessRegistry:
    def __init__(self, checks: dict[str, ReadinessCheck]) -> None:
        self._checks = checks

    async def evaluate(self) -> ReadinessResult:
        names = list(self._checks)
        states = await asyncio.gather(*(self._checks[name]() for name in names))
        dependencies = dict(zip(names, states, strict=True))

        if "unavailable" in states:
            status: ReadinessStatus = "unavailable"
        elif "degraded" in states:
            status = "degraded"
        else:
            status = "ready"
        return ReadinessResult(status=status, dependencies=dependencies)


def static_check(status: ReadinessStatus) -> ReadinessCheck:
    async def check() -> ReadinessStatus:
        return status

    return check
