import json
import math
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from app.api.errors import ApplicationError
from app.core.config import Settings
from app.infrastructure.cloudflare import (
    CloudflareEmbeddingClient,
    CloudflareEmbeddingConfig,
)
from app.infrastructure.gemini import GeminiEmbeddingClient, UnavailableEmbeddingClient
from app.main import _build_embedding_client


def cf_client(max_retries: int = 0, batch_size: int = 32) -> CloudflareEmbeddingClient:
    return CloudflareEmbeddingClient(
        account_id="test-account-id",
        api_token="test-token",
        config=CloudflareEmbeddingConfig(
            model="@cf/baai/bge-base-en-v1.5",
            dimensions=768,
            timeout_seconds=3.0,
            max_retries=max_retries,
            retry_base_seconds=0.001,
            batch_size=batch_size,
        ),
    )


async def test_cf_batches_and_normalizes_embeddings() -> None:
    instance = cf_client()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-token"
        assert "@cf/baai/bge-base-en-v1.5" in request.url.path
        return httpx.Response(
            200,
            json={
                "result": {
                    "shape": [1, 768],
                    "data": [[3.0, *([0.0] * 767)]],
                },
                "success": True,
            },
        )

    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://api.cloudflare.com/client/v4/accounts/test-account-id/ai/run",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(handler),
    )
    vectors = await instance.embed_documents(["hello world"], title="Guide")
    await instance.aclose()

    assert len(vectors) == 1
    assert len(vectors[0]) == 768
    assert math.isclose(sum(v * v for v in vectors[0]), 1.0)


async def test_cf_query_embedding_prepends_bge_instruction() -> None:
    instance = cf_client()
    captured_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read().decode())
        captured_payloads.append(payload)
        return httpx.Response(
            200,
            json={
                "result": {
                    "data": [[1.0, *([0.0] * 767)]],
                },
                "success": True,
            },
        )

    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://api.cloudflare.com/client/v4/accounts/test-account-id/ai/run",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(handler),
    )
    vectors = await instance.embed_queries(["how to reset password"])
    await instance.aclose()

    assert len(vectors) == 1
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["text"][0].startswith(
        "Represent this sentence for searching relevant passages: how to reset password"
    )


async def test_cf_chunks_large_batches() -> None:
    instance = cf_client(batch_size=2)
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        payload = json.loads(request.read().decode())
        batch_len = len(payload["text"])
        return httpx.Response(
            200,
            json={
                "result": {
                    "data": [[1.0, *([0.0] * 767)] for _ in range(batch_len)],
                },
                "success": True,
            },
        )

    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://api.cloudflare.com/client/v4/accounts/test-account-id/ai/run",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(handler),
    )
    texts = ["chunk 1", "chunk 2", "chunk 3", "chunk 4", "chunk 5"]
    vectors = await instance.embed_documents(texts)
    await instance.aclose()

    assert len(vectors) == 5
    assert request_count == 3


async def test_cf_retries_rate_limit_with_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = cf_client(max_retries=1)
    sleep = AsyncMock()
    monkeypatch.setattr("app.infrastructure.cloudflare.asyncio.sleep", sleep)

    responses = [
        httpx.Response(429, headers={"Retry-After": "2"}),
        httpx.Response(
            200,
            json={
                "result": {
                    "data": [[1.0, *([0.0] * 767)]],
                },
                "success": True,
            },
        ),
    ]

    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://api.cloudflare.com/client/v4/accounts/test-account-id/ai/run",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(lambda req: responses.pop(0)),
    )
    vectors = await instance.embed_documents(["hello"])
    await instance.aclose()

    assert len(vectors) == 1
    sleep.assert_awaited_once_with(2.0)


async def test_cf_retries_server_error_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = cf_client(max_retries=1)
    sleep = AsyncMock()
    monkeypatch.setattr("app.infrastructure.cloudflare.asyncio.sleep", sleep)

    responses = [
        httpx.Response(500, json={"error": "internal error"}),
        httpx.Response(
            200,
            json={
                "result": [[1.0, *([0.0] * 767)]],
                "success": True,
            },
        ),
    ]

    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://api.cloudflare.com/client/v4/accounts/test-account-id/ai/run",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(lambda req: responses.pop(0)),
    )
    vectors = await instance.embed_documents(["retry me"])
    await instance.aclose()

    assert len(vectors) == 1
    sleep.assert_awaited_once()


async def test_cf_maps_error_response() -> None:
    instance = cf_client()

    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://api.cloudflare.com/client/v4/accounts/test-account-id/ai/run",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={
                    "errors": [{"code": 1000, "message": "Invalid token"}],
                    "success": False,
                },
            )
        ),
    )
    with pytest.raises(ApplicationError) as exc_info:
        await instance.embed_documents(["hello"])
    assert exc_info.value.code == "EMBEDDING_PROVIDER_ERROR"
    await instance.aclose()


async def test_cf_rejects_dimension_mismatch() -> None:
    instance = cf_client()

    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://api.cloudflare.com/client/v4/accounts/test-account-id/ai/run",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={
                    "result": {"data": [[1.0, 2.0]]},  # only 2 dims instead of 768
                    "success": True,
                },
            )
        ),
    )
    with pytest.raises(ApplicationError) as exc_info:
        await instance.embed_documents(["hello"])
    assert exc_info.value.status == 502
    await instance.aclose()


async def test_cf_rejects_zero_magnitude_vector() -> None:
    instance = cf_client()

    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://api.cloudflare.com/client/v4/accounts/test-account-id/ai/run",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={
                    "result": {"data": [[0.0] * 768]},
                    "success": True,
                },
            )
        ),
    )
    with pytest.raises(ApplicationError) as exc_info:
        await instance.embed_documents(["zero"])
    assert exc_info.value.status == 502
    await instance.aclose()


async def test_cf_rejects_count_mismatch() -> None:
    instance = cf_client()

    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://api.cloudflare.com/client/v4/accounts/test-account-id/ai/run",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={
                    "result": {"data": []},
                    "success": True,
                },
            )
        ),
    )
    with pytest.raises(ApplicationError) as exc_info:
        await instance.embed_documents(["expected one item"])
    assert exc_info.value.code == "EMBEDDING_PROVIDER_ERROR"
    await instance.aclose()


async def test_cf_supports_body_data_wrapper() -> None:
    instance = cf_client()

    await instance._client.aclose()
    instance._client = httpx.AsyncClient(
        base_url="https://api.cloudflare.com/client/v4/accounts/test-account-id/ai/run",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={
                    "data": [[1.0, *([0.0] * 767)]],
                    "success": True,
                },
            )
        ),
    )
    vectors = await instance.embed_documents(["wrapper test"])
    await instance.aclose()
    assert len(vectors) == 1


async def test_cf_empty_batch_does_not_call_provider() -> None:
    instance = cf_client()
    assert await instance.embed_documents([]) == []
    assert await instance.embed_queries([]) == []
    await instance.aclose()


def test_build_embedding_client_provider_selection() -> None:
    # 1. Cloudflare configured
    cf_settings = Settings(
        embedding_provider="cloudflare",
        cloudflare_account_id="acc123",
        cloudflare_api_token=SecretStr("token123"),
    )
    client_cf = _build_embedding_client(cf_settings)
    assert isinstance(client_cf, CloudflareEmbeddingClient)
    assert client_cf.model == "@cf/baai/bge-base-en-v1.5"

    # 2. Cloudflare selected but unconfigured, falling back to Gemini
    fallback_settings = Settings(
        embedding_provider="cloudflare",
        cloudflare_account_id=None,
        cloudflare_api_token=None,
        gemini_api_key=SecretStr("gemini-key"),
    )
    client_fallback = _build_embedding_client(fallback_settings)
    assert isinstance(client_fallback, GeminiEmbeddingClient)

    # 3. Gemini selected explicitly
    gemini_settings = Settings(
        embedding_provider="gemini",
        gemini_api_key=SecretStr("gemini-key"),
    )
    client_gemini = _build_embedding_client(gemini_settings)
    assert isinstance(client_gemini, GeminiEmbeddingClient)

    # 4. Neither configured
    none_settings = Settings(
        embedding_provider="cloudflare",
        cloudflare_account_id=None,
        cloudflare_api_token=None,
        gemini_api_key=None,
    )
    client_none = _build_embedding_client(none_settings)
    assert isinstance(client_none, UnavailableEmbeddingClient)
