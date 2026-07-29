import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import monotonic

from app.api.errors import ApplicationError


@dataclass(frozen=True)
class ResilienceConfig:
    max_concurrency: int = 8
    acquire_timeout_seconds: float = 0.25
    failure_threshold: int = 5
    recovery_seconds: float = 30


class ProviderGuard:
    """Bound provider concurrency and stop traffic while a dependency is unhealthy."""

    def __init__(self, name: str, config: ResilienceConfig) -> None:
        self.name = name
        self._config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self._failures = 0
        self._opened_at: float | None = None
        self._probe_in_flight = False
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def call(self) -> AsyncIterator[None]:
        await self._before_call()
        acquired = False
        try:
            async with asyncio.timeout(self._config.acquire_timeout_seconds):
                await self._semaphore.acquire()
                acquired = True
        except TimeoutError as exc:
            await self._release_probe()
            raise ApplicationError(
                "PROVIDER_BACKPRESSURE",
                "Service is busy",
                f"The {self.name} capacity limit was reached. Retry shortly.",
                status=503,
                retryable=True,
            ) from exc

        try:
            yield
        except ApplicationError as exc:
            if exc.retryable or exc.status >= 500:
                await self._record_failure()
            else:
                await self._record_success()
            raise
        except Exception:
            await self._record_failure()
            raise
        else:
            await self._record_success()
        finally:
            if acquired:
                self._semaphore.release()

    async def _before_call(self) -> None:
        async with self._lock:
            if self._opened_at is None:
                return
            if monotonic() - self._opened_at < self._config.recovery_seconds:
                raise ApplicationError(
                    "PROVIDER_CIRCUIT_OPEN",
                    "Provider temporarily unavailable",
                    f"The {self.name} circuit breaker is open. Retry shortly.",
                    status=503,
                    retryable=True,
                )
            if self._probe_in_flight:
                raise ApplicationError(
                    "PROVIDER_CIRCUIT_OPEN",
                    "Provider temporarily unavailable",
                    f"The {self.name} circuit breaker is testing recovery.",
                    status=503,
                    retryable=True,
                )
            self._probe_in_flight = True

    async def _record_success(self) -> None:
        async with self._lock:
            self._failures = 0
            self._opened_at = None
            self._probe_in_flight = False

    async def _record_failure(self) -> None:
        async with self._lock:
            self._probe_in_flight = False
            self._failures += 1
            if self._failures >= self._config.failure_threshold:
                self._opened_at = monotonic()

    async def _release_probe(self) -> None:
        async with self._lock:
            self._probe_in_flight = False
