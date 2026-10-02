import asyncio
import math
from contextlib import suppress
from dataclasses import dataclass, field
from secrets import randbelow
from typing import Any, cast

import httpx

from app.api.errors import ApplicationError
from app.services.resilience import ProviderGuard, ResilienceConfig


@dataclass(frozen=True)
class CloudflareEmbeddingConfig:
    model: str = "@cf/baai/bge-base-en-v1.5"
    dimensions: int = 768
    timeout_seconds: float = 30.0
    max_retries: int = 5
    retry_base_seconds: float = 0.5
    batch_size: int = 32
    query_instruction: str = "Represent this sentence for searching relevant passages: "
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)


class CloudflareEmbeddingClient:
    def __init__(
        self,
        *,
        account_id: str,
        api_token: str,
        config: CloudflareEmbeddingConfig,
    ) -> None:
        self.model = config.model
        self.dimensions = config.dimensions
        self.max_retries = config.max_retries
        self.retry_base_seconds = config.retry_base_seconds
        self.batch_size = config.batch_size
        self.query_instruction = config.query_instruction
        self._guard = ProviderGuard("Cloudflare embeddings", config.resilience)
        account = account_id.strip()
        self._client = httpx.AsyncClient(
            base_url=f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run",
            headers={
                "Authorization": f"Bearer {api_token.strip()}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(config.timeout_seconds, connect=min(config.timeout_seconds, 3.0)),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed_documents(
        self, texts: list[str], *, title: str | None = None
    ) -> list[list[float]]:
        if not texts:
            return []
        formatted = [f"{title}: {text}" if title else text for text in texts]
        return await self._embed(formatted)

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        prefix = self.query_instruction or ""
        formatted = [
            f"{prefix}{text}" if prefix and not text.startswith(prefix) else text
            for text in texts
        ]
        return await self._embed(formatted)

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with self._guard.call():
            results: list[list[float]] = []
            for i in range(0, len(texts), self.batch_size):
                chunk = texts[i : i + self.batch_size]
                chunk_embeddings = await self._embed_guarded(chunk)
                results.extend(chunk_embeddings)
            return results

    async def _embed_guarded(self, texts: list[str]) -> list[list[float]]:
        model_path = self.model.lstrip("/")
        payload = {"text": texts}
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post(f"/{model_path}", json=payload)
                if (
                    response.status_code == 429 or response.status_code >= 500
                ) and attempt < self.max_retries:
                    await asyncio.sleep(self._retry_delay(response, attempt))
                    continue
                response.raise_for_status()
                body = cast(dict[str, Any], response.json())
                if isinstance(body, dict) and body.get("success") is False:
                    errors = body.get("errors", [])
                    error_msg = (
                        "; ".join(str(e.get("message", e)) for e in errors)
                        if errors
                        else "Unknown Cloudflare error"
                    )
                    raise ValueError(f"Cloudflare Workers AI returned error: {error_msg}")

                result = body.get("result", body)
                raw_data: Any
                if isinstance(result, dict) and "data" in result:
                    raw_data = result["data"]
                elif isinstance(result, list):
                    raw_data = result
                elif isinstance(body, dict) and "data" in body:
                    raw_data = body["data"]
                else:
                    raise ValueError(f"Unexpected Cloudflare embedding response format: {body}")

                if not isinstance(raw_data, list):
                    raise ValueError("Cloudflare embedding result data is not a list.")

                embeddings = [
                    self._normalize(cast(list[float], item))
                    for item in raw_data
                ]
                if len(embeddings) != len(texts):
                    raise ValueError(
                        f"Embedding response count mismatch: expected {len(texts)}, "
                        f"got {len(embeddings)}."
                    )
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
                    "Cloudflare Workers AI could not generate the embeddings.",
                    status=503 if retryable else 502,
                    retryable=retryable,
                ) from exc
        raise AssertionError("Embedding retry loop exited unexpectedly.")

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        delay: float | None = None
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            with suppress(ValueError):
                delay = float(retry_after)
        if delay is None:
            jitter = 0.5 + randbelow(1000) / 1000
            delay = self.retry_base_seconds * (2**attempt) * jitter
        if response.status_code == 429:
            delay = max(delay, 2.0 * (attempt + 1))
        return float(min(delay, 30.0))

    def _normalize(self, values: list[float]) -> list[float]:
        if len(values) != self.dimensions:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.dimensions}, got {len(values)}."
            )
        magnitude = math.sqrt(sum(value * value for value in values))
        if magnitude == 0:
            raise ValueError("Embedding vector has zero magnitude.")
        return [value / magnitude for value in values]
