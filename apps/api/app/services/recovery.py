import asyncio
from contextlib import suppress
from typing import Any, Protocol

from app.core.logging import get_logger


class RecoveryAdmin(Protocol):
    async def rpc(self, function: str, payload: dict[str, Any]) -> Any: ...


class RecoveryMonitor:
    def __init__(self, admin: RecoveryAdmin, interval_seconds: int) -> None:
        self.admin = admin
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="stale-work-recovery")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task

    async def recover_once(self) -> None:
        result = await self.admin.rpc("recover_stale_work", {})
        get_logger().info("stale_work_recovered", result=result)

    async def _run(self) -> None:
        while True:
            try:
                await self.recover_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                get_logger().exception("stale_work_recovery_failed")
            await asyncio.sleep(self.interval_seconds)
