import math
from unittest.mock import AsyncMock

import httpx
import pytest

from app.api.errors import ApplicationError
from app.infrastructure.gemini import (
    GeminiEmbeddingClient,
    GeminiEmbeddingConfig,
    UnavailableEmbeddingClient,
)


def client(max_retries: int = 0) -> GeminiEmbeddingClient:
    return GeminiEmbeddingClient(
        api_key="key",
        config=GeminiEmbeddingConfig(
            model="gemini-embedding-001",
            dimensions=768,
            timeout_seconds=3,
            max_retries=max_retries,
            retry_base_seconds=0.001,
        ),
    )


async def test_batches_and_normalizes_embeddings() -> None:
    instance = client()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "key"
        assert request.url.path.endswith(":batchEmbedContents")
        return httpx.Response(
            200,
            json={"embeddings": [{"values": [2.0, *([0.0] * 767)]}]},
        )

    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        headers={"x-goog-api-key": "key"},
        transport=httpx.MockTransport(handler),
    )
    vectors = await instance.embed_documents(["hello"], title="Guide")
    await instance.aclose()

    assert len(vectors[0]) == 768
    assert math.isclose(sum(value * value for value in vectors[0]), 1.0)


async def test_query_embedding_uses_retrieval_query_task_without_title() -> None:
    instance = client()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read().decode()
        assert '"taskType":"RETRIEVAL_QUERY"' in payload
        assert '"title"' not in payload
        assert '"autoTruncate"' not in payload
        return httpx.Response(
            200,
            json={"embeddings": [{"values": [1.0, *([0.0] * 767)]}]},
        )

    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        transport=httpx.MockTransport(handler),
    )
    assert len(await instance.embed_queries(["reset token"])) == 1
    await instance.aclose()


async def test_retries_rate_limit_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = client(max_retries=1)
    sleep = AsyncMock()
    monkeypatch.setattr("app.infrastructure.gemini.asyncio.sleep", sleep)
    responses = [
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={"embeddings": [{"values": [1.0] * 768}]}),
    ]
    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        transport=httpx.MockTransport(lambda request: responses.pop(0)),
    )
    assert len(await instance.embed_documents(["hello"])) == 1
    sleep.assert_awaited_once_with(10.0)
    await instance.aclose()


async def test_maps_invalid_provider_response() -> None:
    instance = client()
    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"embeddings": []})),
    )
    with pytest.raises(ApplicationError) as exc_info:
        await instance.embed_documents(["hello"])
    assert exc_info.value.code == "EMBEDDING_PROVIDER_ERROR"
    await instance.aclose()


async def test_unavailable_provider_is_controlled() -> None:
    instance = UnavailableEmbeddingClient()
    with pytest.raises(ApplicationError):
        await instance.embed_documents(["hello"])
    await instance.aclose()


async def test_empty_batch_does_not_call_provider() -> None:
    instance = client()
    assert await instance.embed_documents([]) == []
    await instance.aclose()


@pytest.mark.parametrize(
    "values",
    [
        [1.0],
        [0.0] * 768,
    ],
)
async def test_rejects_invalid_embedding_vectors(values: list[float]) -> None:
    instance = client()
    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"embeddings": [{"values": values}]})
        ),
    )

    with pytest.raises(ApplicationError) as exc_info:
        await instance.embed_documents(["hello"])

    assert exc_info.value.status == 502
    await instance.aclose()
