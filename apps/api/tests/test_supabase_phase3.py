import json

import httpx
import pytest

from app.api.errors import ApplicationError
from app.infrastructure.supabase.admin import SupabaseAdminClient, UnavailableAdminClient
from app.infrastructure.supabase.storage import SupabaseStorageClient


async def test_admin_rpc_and_claim() -> None:
    responses = [
        httpx.Response(200, json={"ok": True}),
        httpx.Response(200, json=[{"msg_id": 1}]),
    ]
    admin = SupabaseAdminClient(
        supabase_url="https://example.supabase.co",
        service_key="service",
        timeout_seconds=3,
    )
    await admin._client.aclose()
    admin._client = httpx.AsyncClient(
        base_url="https://example.supabase.co/rest/v1/rpc",
        transport=httpx.MockTransport(lambda request: responses.pop(0)),
    )
    assert await admin.rpc("function", {}) == {"ok": True}
    assert (await admin.claim(30, 1))[0]["msg_id"] == 1
    await admin.aclose()


async def test_admin_rpc_accepts_empty_success_response() -> None:
    admin = SupabaseAdminClient(
        supabase_url="https://example.supabase.co",
        service_key="service",
        timeout_seconds=3,
    )
    await admin._client.aclose()
    admin._client = httpx.AsyncClient(
        base_url="https://example.supabase.co/rest/v1/rpc",
        transport=httpx.MockTransport(lambda request: httpx.Response(204)),
    )

    assert await admin.rpc("attach_rag_run_correlation", {}) is None
    await admin.aclose()


async def test_admin_maps_errors_and_unavailable() -> None:
    admin = SupabaseAdminClient(
        supabase_url="https://example.supabase.co",
        service_key="service",
        timeout_seconds=3,
    )
    await admin._client.aclose()
    admin._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))
    )
    with pytest.raises(ApplicationError):
        await admin.rpc("function", {})
    await admin.aclose()
    unavailable = UnavailableAdminClient()
    with pytest.raises(ApplicationError):
        await unavailable.rpc("function", {})
    await unavailable.aclose()


@pytest.mark.parametrize(
    ("function_name", "provider_code", "expected_status", "expected_code"),
    [
        ("enqueue_document_reindex", "42501", 403, "INGESTION_PROVIDER_ERROR"),
        ("enqueue_document_reindex", "P0002", 404, "INGESTION_PROVIDER_ERROR"),
        ("enqueue_document_reindex", "55000", 409, "REINDEX_CONFLICT"),
        ("enqueue_document_reindex", "XX000", 503, "INGESTION_PROVIDER_ERROR"),
        ("hybrid_search", "22023", 400, "RETRIEVAL_REQUEST_REJECTED"),
        ("hybrid_search", "54000", 413, "RETRIEVAL_REQUEST_REJECTED"),
    ],
)
async def test_admin_maps_database_error_codes(
    function_name: str,
    provider_code: str,
    expected_status: int,
    expected_code: str,
) -> None:
    admin = SupabaseAdminClient(
        supabase_url="https://example.supabase.co",
        service_key="service",
        timeout_seconds=3,
    )
    await admin._client.aclose()
    admin._client = httpx.AsyncClient(
        base_url="https://example.supabase.co/rest/v1/rpc",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                400,
                json={"code": provider_code, "message": "rejected"},
            )
        ),
    )

    with pytest.raises(ApplicationError) as exc_info:
        await admin.rpc(function_name, {})

    assert exc_info.value.status == expected_status
    assert exc_info.value.code == expected_code
    await admin.aclose()


async def test_storage_signed_download_remove_and_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/upload/sign/" in str(request.url):
            return httpx.Response(200, json={"url": "/object/upload/sign/x?token=signed"})
        if request.method == "GET":
            return httpx.Response(200, content=b"content")
        return httpx.Response(200, json={})

    storage = SupabaseStorageClient(
        supabase_url="https://example.supabase.co",
        publishable_key="publishable",
        service_key="service",
        timeout_seconds=3,
    )
    await storage._client.aclose()
    storage._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    url, token = await storage.create_signed_upload("a/file.txt", "user")
    assert url.startswith("https://example.supabase.co")
    assert token == "signed"
    assert await storage.download("a/file.txt") == b"content"
    await storage.remove("a/file.txt")
    await storage.aclose()

    response = httpx.Response(503)
    with pytest.raises(ApplicationError):
        storage._raise(response, "failed")


async def test_storage_requires_key_for_worker_download() -> None:
    storage = SupabaseStorageClient(
        supabase_url="https://example.supabase.co",
        publishable_key="publishable",
        service_key=None,
        timeout_seconds=3,
    )
    with pytest.raises(ApplicationError):
        await storage.download("a")
    await storage.remove("a")
    await storage.aclose()


async def test_storage_creates_signed_download_url() -> None:
    storage = SupabaseStorageClient(
        supabase_url="https://example.supabase.co",
        publishable_key="publishable",
        service_key=None,
        timeout_seconds=3,
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/storage/v1/object/sign/workspace-documents/a/file.pdf")
        assert request.headers["authorization"] == "Bearer user"
        assert json.loads(request.content)["expiresIn"] == 90
        return httpx.Response(200, json={"signedURL": "/object/sign/signed-token"})

    await storage._client.aclose()
    storage._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    url = await storage.create_signed_download("a/file.pdf", "user", expires_in=90)

    assert url == "https://example.supabase.co/storage/v1/object/sign/signed-token"
    await storage.aclose()
