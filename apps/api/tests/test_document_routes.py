import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from httpx import AsyncClient

from app.models.auth import AuthenticatedUser, WorkspaceAccess
from app.models.documents import Document, IngestionJob

USER_ID = UUID("10000000-0000-4000-8000-000000000001")
WORKSPACE_ID = UUID("a0000000-0000-4000-8000-000000000001")
UPLOAD_ID = UUID("20000000-0000-4000-8000-000000000001")
JOB_ID = UUID("30000000-0000-4000-8000-000000000001")
DOCUMENT_ID = UUID("40000000-0000-4000-8000-000000000001")
PAYLOAD = b"hello"
CHECKSUM = hashlib.sha256(PAYLOAD).hexdigest()
PATH = f"{WORKSPACE_ID}/{USER_ID}/{UPLOAD_ID}/one.txt"


class Verifier:
    async def aclose(self) -> None:
        return None

    async def verify(self, token: str) -> AuthenticatedUser:
        assert token == "token"
        return AuthenticatedUser(id=USER_ID, email="u@example.test", role="authenticated")


def document() -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "id": str(DOCUMENT_ID),
        "workspace_id": str(WORKSPACE_ID),
        "uploaded_by": str(USER_ID),
        "object_path": PATH,
        "filename": "one.txt",
        "title": None,
        "content_type": "text/plain",
        "size_bytes": 5,
        "sha256": CHECKSUM,
        "status": "queued",
        "processing_version": 1,
        "index_version": 0,
        "target_index_version": 1,
        "chunk_strategy": None,
        "embedding_model": None,
        "embedding_dimensions": None,
        "indexed_at": None,
        "page_count": None,
        "chunk_count": 0,
        "tags": [],
        "failure_code": None,
        "created_at": now,
        "updated_at": now,
    }


def job() -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "id": str(JOB_ID),
        "workspace_id": str(WORKSPACE_ID),
        "document_id": str(DOCUMENT_ID),
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "attempt": 0,
        "max_attempts": 3,
        "error_code": None,
        "error_detail": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }


class Data:
    async def aclose(self) -> None:
        return None

    async def get_workspace_access(self, **kwargs: Any) -> WorkspaceAccess:
        del kwargs
        return WorkspaceAccess(workspace_id=WORKSPACE_ID, user_id=USER_ID, role="owner")

    async def create_upload_session(self, **kwargs: Any) -> dict[str, Any]:
        return dict(kwargs["record"])

    async def get_upload_session(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        return {
            "object_path": PATH,
            "workspace_id": str(WORKSPACE_ID),
            "uploaded_by": str(USER_ID),
            "expected_sha256": CHECKSUM,
            "expected_size_bytes": 5,
            "expected_content_type": "text/plain",
        }

    async def list_documents(self, **kwargs: Any) -> list[Any]:
        del kwargs
        return [Document.model_validate(document())]

    async def get_document(self, **kwargs: Any) -> Document | None:
        del kwargs
        return Document.model_validate(document())

    async def get_ingestion_job(self, **kwargs: Any) -> Any:
        del kwargs
        return IngestionJob.model_validate(job())


class Storage:
    removed: str | None = None

    async def aclose(self) -> None:
        return None

    async def create_signed_upload(self, path: str, token: str) -> tuple[str, str]:
        assert path.endswith("one.txt")
        assert token == "token"
        return "https://signed", "upload-token"

    async def download(self, path: str, token: str) -> bytes:
        assert path == PATH
        assert token == "token"
        return PAYLOAD

    async def create_signed_download(self, path: str, token: str, *, expires_in: int = 60) -> str:
        assert path == PATH
        assert token == "token"
        assert expires_in == 60
        return "https://signed.example/document"

    async def remove(self, path: str) -> None:
        self.removed = path


class Admin:
    calls: list[tuple[str, dict[str, Any]]]

    def __init__(self) -> None:
        self.calls = []

    async def aclose(self) -> None:
        return None

    async def rpc(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, payload))
        if name == "enqueue_document_reindex":
            return job()
        assert name == "finalize_document_upload"
        assert payload["p_actual_sha256"] == CHECKSUM
        return {
            "document": document(),
            "job": job(),
            "deduplicated": False,
            "duplicate_object_path": None,
        }


def configure(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.state.auth_verifier = Verifier()
    app.state.supabase_data = Data()
    app.state.supabase_storage = Storage()
    app.state.supabase_admin = Admin()


def headers() -> dict[str, str]:
    return {"Authorization": "Bearer token", "X-Workspace-ID": str(WORKSPACE_ID)}


async def test_upload_list_complete_and_get_job(client: AsyncClient) -> None:
    configure(client)
    create = await client.post(
        "/v1/documents/upload-url",
        headers=headers(),
        json={
            "filename": "one.txt",
            "content_type": "text/plain",
            "size_bytes": 5,
            "sha256": CHECKSUM,
        },
    )
    assert create.status_code == 201, create.text
    assert create.json()["upload_token"] == "upload-token"

    complete = await client.post(
        "/v1/documents/complete-upload",
        headers=headers(),
        json={"upload_id": str(UPLOAD_ID), "object_path": PATH, "sha256": CHECKSUM},
    )
    assert complete.status_code == 202
    assert complete.json()["document"]["status"] == "queued"

    listed = await client.get("/v1/documents", headers=headers())
    assert listed.json()["items"][0]["filename"] == "one.txt"
    fetched = await client.get(f"/v1/ingestion-jobs/{JOB_ID}", headers=headers())
    assert fetched.json()["id"] == str(JOB_ID)


async def test_get_document_and_open_exact_source(client: AsyncClient) -> None:
    configure(client)

    fetched = await client.get(f"/v1/documents/{DOCUMENT_ID}", headers=headers())
    assert fetched.status_code == 200
    assert fetched.json()["id"] == str(DOCUMENT_ID)

    source = await client.get(
        f"/v1/documents/{DOCUMENT_ID}/source?page=3",
        headers=headers(),
        follow_redirects=False,
    )
    assert source.status_code == 307
    assert source.headers["location"] == "https://signed.example/document"


async def test_document_source_rejects_other_workspace(client: AsyncClient) -> None:
    configure(client)
    data = client._transport.app.state.supabase_data  # type: ignore[attr-defined]
    record = document()
    record["workspace_id"] = "a0000000-0000-4000-8000-000000000099"
    data.get_document = lambda **kwargs: _async_value(Document.model_validate(record))

    response = await client.get(
        f"/v1/documents/{DOCUMENT_ID}/source",
        headers=headers(),
        follow_redirects=False,
    )

    assert response.status_code == 404


async def test_rejects_extension_and_signature(client: AsyncClient) -> None:
    configure(client)
    invalid = await client.post(
        "/v1/documents/upload-url",
        headers=headers(),
        json={
            "filename": "one.pdf",
            "content_type": "text/plain",
            "size_bytes": 5,
            "sha256": CHECKSUM,
        },
    )
    assert invalid.status_code == 422

    data = client._transport.app.state.supabase_data  # type: ignore[attr-defined]
    session = await data.get_upload_session()
    session["expected_content_type"] = "application/pdf"
    data.get_upload_session = lambda **kwargs: _async_value(session)
    invalid_bytes = await client.post(
        "/v1/documents/complete-upload",
        headers=headers(),
        json={"upload_id": str(UPLOAD_ID), "object_path": PATH, "sha256": CHECKSUM},
    )
    assert invalid_bytes.status_code == 422


async def test_owner_can_reindex_with_default_strategy(client: AsyncClient) -> None:
    configure(client)

    response = await client.post(
        f"/v1/documents/{DOCUMENT_ID}/reindex",
        headers=headers(),
    )

    assert response.status_code == 202, response.text
    assert response.json()["id"] == str(JOB_ID)
    admin = client._transport.app.state.supabase_admin  # type: ignore[attr-defined]
    name, payload = admin.calls[-1]
    assert name == "enqueue_document_reindex"
    assert payload["p_document_id"] == str(DOCUMENT_ID)
    assert payload["p_strategy"] is None


async def test_only_owner_can_reindex(client: AsyncClient) -> None:
    configure(client)
    app = client._transport.app  # type: ignore[attr-defined]

    async def member_access(**kwargs: Any) -> WorkspaceAccess:
        del kwargs
        return WorkspaceAccess(workspace_id=WORKSPACE_ID, user_id=USER_ID, role="member")

    app.state.supabase_data.get_workspace_access = member_access
    response = await client.post(
        f"/v1/documents/{DOCUMENT_ID}/reindex",
        headers=headers(),
        json={"strategy": "fixed"},
    )

    assert response.status_code == 403


async def _async_value(value: Any) -> Any:
    return value
