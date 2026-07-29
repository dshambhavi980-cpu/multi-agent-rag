import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from secrets import randbelow
from typing import Any, cast

import httpx

from app.api.errors import ApplicationError
from app.services.resilience import ProviderGuard, ResilienceConfig


@dataclass(frozen=True)
class GeminiGenerationConfig:
    model: str
    timeout_seconds: float
    max_retries: int
    retry_base_seconds: float
    max_output_tokens: int
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)


class GeminiGenerationClient:
    def __init__(self, *, api_key: str, config: GeminiGenerationConfig) -> None:
        self.model = config.model
        self.max_retries = config.max_retries
        self.retry_base_seconds = config.retry_base_seconds
        self.max_output_tokens = config.max_output_tokens
        self._guard = ProviderGuard("Gemini generation", config.resilience)
        self._client = httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com/v1beta",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            timeout=httpx.Timeout(config.timeout_seconds, connect=min(config.timeout_seconds, 3)),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def stream_answer(self, *, system_prompt: str, prompt: str) -> AsyncIterator[str]:
        async with self._guard.call():
            async for token in self._stream_answer(system_prompt=system_prompt, prompt=prompt):
                yield token

    async def _stream_answer(self, *, system_prompt: str, prompt: str) -> AsyncIterator[str]:
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": self.max_output_tokens},
        }
        for attempt in range(self.max_retries + 1):
            emitted = False
            try:
                async with self._client.stream(
                    "POST",
                    f"/models/{self.model}:streamGenerateContent",
                    params={"alt": "sse"},
                    json=payload,
                ) as response:
                    if (
                        response.status_code == 429 or response.status_code >= 500
                    ) and attempt < self.max_retries:
                        await response.aread()
                        await asyncio.sleep(self._retry_delay(response, attempt))
                        continue
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        body = cast(dict[str, Any], json.loads(line[5:].strip()))
                        for candidate in cast(list[dict[str, Any]], body.get("candidates", [])):
                            content = cast(dict[str, Any], candidate.get("content", {}))
                            for part in cast(list[dict[str, Any]], content.get("parts", [])):
                                text = part.get("text")
                                if isinstance(text, str) and text:
                                    emitted = True
                                    yield text
                    return
            except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError) as exc:
                retryable = isinstance(exc, httpx.HTTPStatusError) and (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if (
                    retryable
                    and isinstance(exc, httpx.HTTPStatusError)
                    and not emitted
                    and attempt < self.max_retries
                ):
                    await asyncio.sleep(self._retry_delay(exc.response, attempt))
                    continue
                raise ApplicationError(
                    "GENERATION_PROVIDER_ERROR",
                    "Answer generation failed",
                    "Gemini could not generate the grounded answer.",
                    status=503 if retryable else 502,
                    retryable=retryable,
                ) from exc

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), 60)
            except ValueError:
                pass
        jitter = 0.5 + randbelow(1000) / 1000
        return float(min(self.retry_base_seconds * (2**attempt) * jitter, 60))


class UnavailableGenerationClient:
    model = "unconfigured"

    async def aclose(self) -> None:
        return None

    async def stream_answer(self, *, system_prompt: str, prompt: str) -> AsyncIterator[str]:
        if system_prompt:
            raise ApplicationError(
                "GENERATION_PROVIDER_NOT_CONFIGURED",
                "Answer generation unavailable",
                "GEMINI_API_KEY is required for grounded answer generation.",
                status=503,
            )
        yield prompt
