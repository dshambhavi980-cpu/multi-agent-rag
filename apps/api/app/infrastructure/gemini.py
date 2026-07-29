import asyncio
import math
from dataclasses import dataclass, field
from secrets import randbelow
from typing import Any, cast

import httpx

from app.api.errors import ApplicationError
from app.services.resilience import ProviderGuard, ResilienceConfig


@dataclass(frozen=True)
class GeminiEmbeddingConfig:
    model: str
    dimensions: int
    timeout_seconds: float
    max_retries: int
    retry_base_seconds: float
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)


class GeminiEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str,
        config: GeminiEmbeddingConfig,
    ) -> None:
        self.model = config.model
        self.dimensions = config.dimensions
        self.max_retries = config.max_retries
        self.retry_base_seconds = config.retry_base_seconds
        self._guard = ProviderGuard("Gemini embeddings", config.resilience)
        self._client = httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com/v1beta",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            timeout=httpx.Timeout(config.timeout_seconds, connect=min(config.timeout_seconds, 3)),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed_documents(
        self, texts: list[str], *, title: str | None = None
    ) -> list[list[float]]:
        return await self._embed(texts, task_type="RETRIEVAL_DOCUMENT", title=title)

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, task_type="RETRIEVAL_QUERY")

    async def _embed(
        self,
        texts: list[str],
        *,
        task_type: str,
        title: str | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []
        async with self._guard.call():
            return await self._embed_guarded(texts, task_type=task_type, title=title)

    async def _embed_guarded(
        self, texts: list[str], *, task_type: str, title: str | None = None
    ) -> list[list[float]]:
        model_path = f"models/{self.model}"
        requests = [
            {
                "model": model_path,
                "content": {"parts": [{"text": text}]},
                "taskType": task_type,
                **({"title": title} if title is not None else {}),
                "outputDimensionality": self.dimensions,
            }
            for text in texts
        ]
        payload = {"requests": requests}
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post(
                    f"/{model_path}:batchEmbedContents", json=payload
                )
                if (
                    response.status_code == 429 or response.status_code >= 500
                ) and attempt < self.max_retries:
                    await asyncio.sleep(self._retry_delay(response, attempt))
                    continue
                response.raise_for_status()
                body = cast(dict[str, Any], response.json())
                embeddings = [
                    self._normalize(cast(list[float], item["values"]))
                    for item in cast(list[dict[str, Any]], body["embeddings"])
                ]
                if len(embeddings) != len(texts):
                    raise ValueError("Embedding response count mismatch.")
                return embeddings
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                retryable = isinstance(exc, httpx.HTTPStatusError) and (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if retryable and attempt < self.max_retries:
                    response = cast(httpx.HTTPStatusError, exc).response
                    await asyncio.sleep(self._retry_delay(response, attempt))
                    continue
                raise ApplicationError(
                    "EMBEDDING_PROVIDER_ERROR",
                    "Embedding provider failed",
                    "Gemini could not generate the document embeddings.",
                    status=503 if retryable else 502,
                    retryable=retryable,
                ) from exc
        raise AssertionError("Embedding retry loop exited unexpectedly.")

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), 60)
            except ValueError:
                pass
        jitter = 0.5 + randbelow(1000) / 1000
        return float(min(self.retry_base_seconds * (2**attempt) * jitter, 60.0))

    def _normalize(self, values: list[float]) -> list[float]:
        if len(values) != self.dimensions:
            raise ValueError("Embedding dimension mismatch.")
        magnitude = math.sqrt(sum(value * value for value in values))
        if magnitude == 0:
            raise ValueError("Embedding vector has zero magnitude.")
        return [value / magnitude for value in values]


class UnavailableEmbeddingClient:
    model = "unconfigured"
    dimensions = 768

    async def aclose(self) -> None:
        return None

    async def embed_documents(
        self, texts: list[str], *, title: str | None = None
    ) -> list[list[float]]:
        del texts, title
        raise ApplicationError(
            "EMBEDDING_PROVIDER_NOT_CONFIGURED",
            "Embedding provider unavailable",
            "GEMINI_API_KEY is required by the ingestion worker.",
            status=503,
            retryable=False,
        )

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        del texts
        raise ApplicationError(
            "EMBEDDING_PROVIDER_NOT_CONFIGURED",
            "Embedding provider unavailable",
            "GEMINI_API_KEY is required for retrieval.",
            status=503,
            retryable=False,
        )
