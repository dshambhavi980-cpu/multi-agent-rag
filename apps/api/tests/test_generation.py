import httpx
import pytest

from app.api.errors import ApplicationError
from app.infrastructure.generation import (
    GeminiGenerationClient,
    GeminiGenerationConfig,
    UnavailableGenerationClient,
)


def generation_client(max_retries: int = 0) -> GeminiGenerationClient:
    return GeminiGenerationClient(
        api_key="key",
        config=GeminiGenerationConfig(
            model="gemini-3.1-flash-lite",
            timeout_seconds=3,
            max_retries=max_retries,
            retry_base_seconds=0.001,
            max_output_tokens=128,
        ),
    )


async def test_streams_gemini_sse_text_and_payload() -> None:
    instance = generation_client()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["alt"] == "sse"
        assert request.headers["x-goog-api-key"] == "key"
        payload = request.read().decode()
        assert '"systemInstruction"' in payload
        assert '"maxOutputTokens":128' in payload
        return httpx.Response(
            200,
            text=(
                'data: {"candidates":[{"content":{"parts":[{"text":"First "}]}}]}\n\n'
                'data: {"candidates":[{"content":{"parts":[{"text":"answer."}]}}]}\n\n'
            ),
            headers={"Content-Type": "text/event-stream"},
        )

    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        headers={"x-goog-api-key": "key"},
        transport=httpx.MockTransport(handler),
    )
    chunks = [
        chunk async for chunk in instance.stream_answer(system_prompt="system", prompt="question")
    ]
    await instance.aclose()
    assert chunks == ["First ", "answer."]


async def test_retries_transient_stream_response_before_emission() -> None:
    instance = generation_client(max_retries=1)
    responses = [
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(
            200,
            text='data: {"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}\n\n',
        ),
    ]
    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        transport=httpx.MockTransport(lambda request: responses.pop(0)),
    )
    chunks = [chunk async for chunk in instance.stream_answer(system_prompt="s", prompt="p")]
    await instance.aclose()
    assert chunks == ["ok"]


async def test_maps_invalid_stream_and_unavailable_provider() -> None:
    instance = generation_client()
    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="data: not-json\n\n")
        ),
    )
    with pytest.raises(ApplicationError) as exc_info:
        _ = [chunk async for chunk in instance.stream_answer(system_prompt="s", prompt="p")]
    assert exc_info.value.code == "GENERATION_PROVIDER_ERROR"
    await instance.aclose()

    unavailable = UnavailableGenerationClient()
    with pytest.raises(ApplicationError):
        _ = [chunk async for chunk in unavailable.stream_answer(system_prompt="s", prompt="p")]
    await unavailable.aclose()
