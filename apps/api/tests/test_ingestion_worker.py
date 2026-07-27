import asyncio
from typing import Any

from app.api.errors import ApplicationError
from app.services.ingestion_worker import IngestionWorker, WorkerConfig


class Admin:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.start = {
            "should_process": True,
            "document": {"filename": "one.txt", "title": None},
        }
        self.failure = {"retry": False, "delay_seconds": 0}

    async def claim(self, visibility: int, batch: int) -> list[dict[str, Any]]:
        del visibility, batch
        return []

    async def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        self.calls.append((name, payload))
        if name == "start_document_ingestion":
            return self.start
        if name == "fail_document_ingestion":
            return self.failure
        if name == "load_document_for_indexing":
            return {"pages": [{"page_number": 1, "content": "# Heading\n\nhello"}]}
        return True


class Storage:
    def __init__(self, payload: bytes | Exception) -> None:
        self.payload = payload

    async def download(self, path: str) -> bytes:
        assert path == "one.txt"
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class Embeddings:
    model = "gemini-embedding-001"
    dimensions = 768

    async def embed_documents(
        self, texts: list[str], *, title: str | None = None
    ) -> list[list[float]]:
        assert title == "one.txt"
        return [[1.0, *([0.0] * 767)] for _ in texts]


def worker(admin: Admin, storage: Storage) -> IngestionWorker:
    return IngestionWorker(
        admin=admin,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        embeddings=Embeddings(),
        config=WorkerConfig(0.01, 30, 1, 1),
    )


def item(content_type: str = "text/plain") -> dict[str, Any]:
    return {
        "msg_id": 7,
        "message": {
            "job_id": "job",
            "object_path": "one.txt",
            "content_type": content_type,
            "document_id": "document",
            "processing_version": 1,
        },
    }


async def test_completes_and_archives_document() -> None:
    admin = Admin()
    await worker(admin, Storage(b"hello")).process(item())
    names = [call[0] for call in admin.calls]
    assert names[0] == "start_document_ingestion"
    assert "complete_document_ingestion" in names
    assert names[-1] == "archive_document_ingestion"
    completed = next(call for call in admin.calls if call[0] == "complete_document_ingestion")
    assert completed[1]["p_embedding_dimensions"] == 768
    assert len(completed[1]["p_chunks"][0]["embedding"]) == 768


async def test_archives_already_completed_message() -> None:
    admin = Admin()
    admin.start = {"should_process": False}
    await worker(admin, Storage(b"hello")).process(item())
    assert admin.calls[-1][0] == "archive_document_ingestion"


async def test_quarantines_malformed_document() -> None:
    admin = Admin()
    await worker(admin, Storage(b"\xff")).process(item())
    assert admin.calls[-2][1]["p_quarantined"] is True
    assert admin.calls[-1][0] == "archive_document_ingestion"


async def test_defers_retryable_provider_failure() -> None:
    admin = Admin()
    admin.failure = {"retry": True, "delay_seconds": 4}
    failure = ApplicationError("DOWN", "Down", "temporary", status=503, retryable=True)
    await worker(admin, Storage(failure)).process(item())
    assert admin.calls[-1] == (
        "defer_document_ingestion",
        {"p_message_id": 7, "p_delay_seconds": 4},
    )


async def test_worker_starts_and_stops() -> None:
    instance = worker(Admin(), Storage(b"hello"))
    instance.start()
    await asyncio.sleep(0.02)
    await instance.stop()


async def test_reindexes_from_retained_pages_without_storage_download() -> None:
    admin = Admin()
    await worker(admin, Storage(AssertionError("storage should not be used"))).process(
        {**item(), "message": {**item()["message"], "reindex": True}}
    )
    names = [call[0] for call in admin.calls]
    assert "load_document_for_indexing" in names
    assert "complete_document_ingestion" in names
