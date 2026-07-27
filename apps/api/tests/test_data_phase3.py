from typing import Any
from uuid import UUID

import httpx

from app.infrastructure.supabase.data import SupabaseDataClient

WORKSPACE_ID = UUID("a0000000-0000-4000-8000-000000000001")


async def test_phase3_data_operations() -> None:
    now = "2026-07-28T00:00:00Z"
    doc: dict[str, Any] = {
        "id": "40000000-0000-4000-8000-000000000001",
        "workspace_id": str(WORKSPACE_ID),
        "uploaded_by": "10000000-0000-4000-8000-000000000001",
        "object_path": "path",
        "filename": "one.txt",
        "title": None,
        "content_type": "text/plain",
        "size_bytes": 5,
        "sha256": "a" * 64,
        "status": "ready",
        "processing_version": 1,
        "page_count": 1,
        "chunk_count": 1,
        "tags": [],
        "failure_code": None,
        "created_at": now,
        "updated_at": now,
    }
    job: dict[str, Any] = {
        "id": "30000000-0000-4000-8000-000000000001",
        "workspace_id": str(WORKSPACE_ID),
        "document_id": doc["id"],
        "status": "completed",
        "stage": "completed",
        "progress": 1,
        "attempt": 1,
        "max_attempts": 3,
        "error_code": None,
        "error_detail": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": now,
    }
    responses = [
        httpx.Response(201, json=[{"id": "upload"}]),
        httpx.Response(200, json=[{"id": "upload"}]),
        httpx.Response(200, json=[doc]),
        httpx.Response(200, json=[job]),
    ]
    client = SupabaseDataClient(
        supabase_url="https://example.supabase.co",
        publishable_key="key",
        timeout_seconds=3,
    )
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://example.supabase.co/rest/v1",
        transport=httpx.MockTransport(lambda request: responses.pop(0)),
    )
    assert (await client.create_upload_session(access_token="t", record={}))["id"] == "upload"
    assert (await client.get_upload_session(access_token="t", upload_id=UUID(int=1))) is not None
    assert (
        len(await client.list_documents(access_token="t", workspace_id=WORKSPACE_ID, limit=10)) == 1
    )
    assert await client.get_ingestion_job(access_token="t", job_id=UUID(str(job["id"]))) is not None
    await client.aclose()
