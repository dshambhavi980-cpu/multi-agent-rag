from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import UUID

from app.api.errors import ApplicationError


class RpcClient(Protocol):
    async def rpc(self, function: str, payload: dict[str, Any]) -> Any: ...


@dataclass(frozen=True)
class RateLimitConfig:
    user_requests_per_minute: int = 60
    workspace_requests_per_minute: int = 240
    expensive_requests_per_minute: int = 20


class PostgreSQLRateLimiter:
    def __init__(self, admin: RpcClient, config: RateLimitConfig) -> None:
        self.admin = admin
        self.config = config

    async def check(
        self, *, workspace_id: UUID, actor_id: UUID, bucket: str, expensive: bool
    ) -> None:
        user_limit = (
            self.config.expensive_requests_per_minute
            if expensive
            else self.config.user_requests_per_minute
        )
        result = cast(
            dict[str, Any],
            await self.admin.rpc(
                "consume_api_request_limits",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_bucket": bucket,
                    "p_user_limit": user_limit,
                    "p_workspace_limit": self.config.workspace_requests_per_minute,
                    "p_window_seconds": 60,
                },
            ),
        )
        if not bool(result.get("allowed")):
            raise ApplicationError(
                "RATE_LIMIT_EXCEEDED",
                "Too many requests",
                f"Request capacity is exhausted. Retry in {result.get('retry_after', 60)} seconds.",
                status=429,
                retryable=True,
                retry_after_seconds=int(result.get("retry_after", 60)),
            )
