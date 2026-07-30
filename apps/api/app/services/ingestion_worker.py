import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol, cast

from app.api.errors import ApplicationError
from app.core.logging import get_logger
from app.infrastructure.supabase.admin import SupabaseAdminClient
from app.infrastructure.supabase.storage import SupabaseStorageClient
from app.models.documents import ContentType
from app.services.chunking import ChunkingConfig, ChunkStrategy, chunk_pages
from app.services.document_parser import DocumentParseError, ParsedPage, parse_document


@dataclass(frozen=True)
class WorkerConfig:
    poll_seconds: float
    visibility_seconds: int
    batch_size: int
    parse_timeout_seconds: float
    index_version: int = 1
    chunk_strategy: ChunkStrategy = "heading_recursive"
    chunk_target_chars: int = 1800
    chunk_overlap_chars: int = 0
    embedding_batch_size: int = 64
    embedding_batch_delay_seconds: float = 0.25


@dataclass(frozen=True)
class Failure:
    code: str
    detail: str
    quarantined: bool
    retryable: bool


class EmbeddingClient(Protocol):
    model: str
    dimensions: int

    async def embed_documents(
        self, texts: list[str], *, title: str | None = None
    ) -> list[list[float]]: ...


class IngestionWorker:
    def __init__(
        self,
        *,
        admin: SupabaseAdminClient,
        storage: SupabaseStorageClient,
        embeddings: EmbeddingClient,
        config: WorkerConfig,
    ) -> None:
        self.admin = admin
        self.storage = storage
        self.embeddings = embeddings
        self.config = config
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self.run(), name="document-ingestion-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                messages = await self.admin.claim(
                    self.config.visibility_seconds, self.config.batch_size
                )
                if not messages:
                    await asyncio.sleep(self.config.poll_seconds)
                    continue
                for message in messages:
                    await self.process(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                get_logger().exception("ingestion_poll_failed")
                await asyncio.sleep(self.config.poll_seconds)

    async def process(self, queue_item: dict[str, Any]) -> None:
        message_id = int(queue_item["msg_id"])
        payload = queue_item["message"]
        job_id = str(payload["job_id"])
        started = await self.admin.rpc(
            "start_document_ingestion",
            {"p_job_id": job_id, "p_message_id": message_id},
        )
        if not started.get("should_process"):
            await self.admin.rpc("archive_document_ingestion", {"p_message_id": message_id})
            return
        try:
            document = cast(dict[str, Any], started["document"])
            is_reindex = bool(payload.get("reindex"))
            if is_reindex:
                source = cast(
                    dict[str, Any],
                    await self.admin.rpc(
                        "load_document_for_indexing",
                        {"p_document_id": str(payload["document_id"])},
                    ),
                )
                pages = [
                    ParsedPage(
                        page_number=int(page["page_number"]),
                        content=str(page["content"]),
                    )
                    for page in cast(list[dict[str, Any]], source["pages"])
                ]
                pages_json: list[dict[str, object]] = []
            else:
                data = await self.storage.download(str(payload["object_path"]))
                parsed = await asyncio.wait_for(
                    asyncio.to_thread(
                        parse_document, data, cast(ContentType, str(payload["content_type"]))
                    ),
                    timeout=self.config.parse_timeout_seconds,
                )
                pages = parsed.pages
                pages_json = parsed.pages_json()
            await self._progress(job_id, "chunking", 0.25)
            strategy = cast(ChunkStrategy, str(payload.get("strategy", self.config.chunk_strategy)))
            chunks = chunk_pages(
                pages,
                ChunkingConfig(
                    strategy=strategy,
                    target_chars=self.config.chunk_target_chars,
                    overlap_chars=self.config.chunk_overlap_chars,
                ),
            )
            if not chunks:
                raise DocumentParseError(
                    "NO_INDEXABLE_TEXT", "The document contains no indexable text."
                )
            await self._progress(job_id, "embedding", 0.35)
            chunk_records = [chunk.__dict__.copy() for chunk in chunks]
            title = cast(str | None, document.get("title")) or str(document["filename"])
            batch_size = self.config.embedding_batch_size
            for offset in range(0, len(chunks), batch_size):
                if offset > 0 and self.config.embedding_batch_delay_seconds > 0:
                    await asyncio.sleep(self.config.embedding_batch_delay_seconds)
                batch = chunks[offset : offset + batch_size]
                vectors = await self.embeddings.embed_documents(
                    [chunk.content for chunk in batch], title=title
                )
                for index, vector in enumerate(vectors):
                    chunk_records[offset + index]["embedding"] = vector
                progress = 0.35 + 0.55 * min(offset + len(batch), len(chunks)) / len(chunks)
                await self._progress(job_id, "embedding", progress)
            await self.admin.rpc(
                "complete_document_ingestion",
                {
                    "p_job_id": job_id,
                    "p_pages": pages_json,
                    "p_chunks": chunk_records,
                    "p_index_version": int(
                        payload.get("processing_version", self.config.index_version)
                    ),
                    "p_strategy": strategy,
                    "p_embedding_model": self.embeddings.model,
                    "p_embedding_dimensions": self.embeddings.dimensions,
                },
            )
            await self.admin.rpc("archive_document_ingestion", {"p_message_id": message_id})

        except DocumentParseError as exc:
            await self._fail(job_id, message_id, Failure(exc.code, exc.detail, True, False))
        except TimeoutError:
            await self._fail(
                job_id,
                message_id,
                Failure(
                    "PARSE_TIMEOUT",
                    "Document parsing exceeded the configured timeout.",
                    False,
                    True,
                ),
            )
        except ApplicationError as exc:
            await self._fail(
                job_id,
                message_id,
                Failure(exc.code, exc.detail, False, exc.retryable),
            )
        except Exception:
            get_logger().exception("ingestion_job_failed", job_id=job_id)
            await self._fail(
                job_id,
                message_id,
                Failure(
                    "INGESTION_ERROR",
                    "An unexpected ingestion error occurred.",
                    False,
                    True,
                ),
            )

    async def _progress(self, job_id: str, stage: str, progress: float) -> None:
        await self.admin.rpc(
            "update_document_ingestion_progress",
            {"p_job_id": job_id, "p_stage": stage, "p_progress": progress},
        )

    async def _fail(self, job_id: str, message_id: int, failure: Failure) -> None:
        result = await self.admin.rpc(
            "fail_document_ingestion",
            {
                "p_job_id": job_id,
                "p_error_code": failure.code,
                "p_error_detail": failure.detail,
                "p_quarantined": failure.quarantined,
                "p_retryable": failure.retryable,
            },
        )
        if result.get("retry"):
            await self.admin.rpc(
                "defer_document_ingestion",
                {"p_message_id": message_id, "p_delay_seconds": result["delay_seconds"]},
            )
        else:
            await self.admin.rpc("archive_document_ingestion", {"p_message_id": message_id})
