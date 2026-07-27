import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest

from app.api.errors import ApplicationError
from app.models.rag import CreateMessageRequest
from app.models.retrieval import RetrievalResponse
from app.services.rag import (
    GroundedRagService,
    RagConfig,
    _split_complete_segments,
    _validate_segments,
    confidence_score,
)

USER_ID = UUID("10000000-0000-4000-8000-000000000001")
WORKSPACE_ID = UUID("a0000000-0000-4000-8000-000000000001")
RUN_ID = UUID("70000000-0000-4000-8000-000000000001")
MESSAGE_ID = UUID("80000000-0000-4000-8000-000000000001")
DOCUMENT_ID = UUID("40000000-0000-4000-8000-000000000001")
CHUNK_ID = UUID("50000000-0000-4000-8000-000000000001")
TRACE_ID = UUID("60000000-0000-4000-8000-000000000001")


def retrieval_response(*, items: bool = True) -> RetrievalResponse:
    selected = (
        [
            {
                "chunk_id": str(CHUNK_ID),
                "document_id": str(DOCUMENT_ID),
                "chunk_index": 0,
                "content": "Rotate the emergency token and record an audit event.",
                "page_start": 2,
                "page_end": 2,
                "section_heading": "Emergency reset",
                "char_start": 0,
                "char_end": 53,
                "token_count": 9,
                "filename": "operations.md",
                "title": "Operations",
                "content_type": "text/markdown",
                "tags": ["operations"],
                "document_created_at": "2026-07-28T00:00:00Z",
                "semantic_rank": 1,
                "sparse_rank": 1,
                "semantic_score": 0.82,
                "sparse_score": 0.7,
                "rrf_score": 0.0328,
                "final_rank": 1,
            }
        ]
        if items
        else []
    )
    return RetrievalResponse.model_validate(
        {
            "trace_id": str(TRACE_ID),
            "cache_hit": False,
            "embedding_cache_hit": False,
            "index_fingerprint": "a" * 32,
            "dense_candidate_count": len(selected),
            "sparse_candidate_count": len(selected),
            "embedding_ms": 10,
            "database_ms": 20,
            "total_ms": 30,
            "items": selected,
        }
    )


class Admin:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.sequence = 0

    async def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        self.calls.append((name, payload))
        if name == "append_rag_run_event":
            self.sequence += 1
            return {"sequence": self.sequence}
        if name == "complete_rag_run":
            return {"message_id": str(MESSAGE_ID), "run": {"id": str(RUN_ID)}}
        return True


class Retrieval:
    def __init__(self, response: RetrievalResponse) -> None:
        self.response = response

    async def search(self, **kwargs: Any) -> RetrievalResponse:
        del kwargs
        return self.response


class Generation:
    model = "gemini-3.1-flash-lite"

    def __init__(self, chunks: list[str] | None = None, error: bool = False) -> None:
        self.chunks = chunks or []
        self.error = error
        self.called = False

    async def stream_answer(self, **kwargs: Any) -> AsyncIterator[str]:
        del kwargs
        self.called = True
        if self.error:
            raise ApplicationError(
                "GENERATION_FAILED", "Generation failed", "provider failed", status=503
            )
        for chunk in self.chunks:
            yield chunk


def service(
    admin: Admin,
    retrieval: RetrievalResponse,
    generation: Generation,
) -> GroundedRagService:
    return GroundedRagService(
        admin=admin,  # type: ignore[arg-type]
        retrieval=Retrieval(retrieval),  # type: ignore[arg-type]
        generation=generation,
        config=RagConfig(timeout_seconds=2),
    )


async def execute(instance: GroundedRagService) -> None:
    await instance._execute(
        run_id=RUN_ID,
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        request_id=UUID(int=9),
        body=CreateMessageRequest(content="How is the emergency token rotated?"),
    )


def test_segment_validation_rejects_unknown_and_uncited_claims() -> None:
    segments, remainder = _split_complete_segments(
        "Supported [C1]. Unknown [C9]. Uncited claim. Partial"
    )
    valid, used, reviewed, accepted, conflict = _validate_segments(segments, allowed={"C1"})
    assert valid == ["Supported [C1]."]
    assert used == {"C1"}
    assert (reviewed, accepted, conflict) == (3, 1, False)
    assert remainder == "Partial"


async def test_grounded_run_persists_only_allowed_citations() -> None:
    admin = Admin()
    instance = service(
        admin,
        retrieval_response(),
        Generation(["Rotate the emergency token [C1]. ", "Never cite this [C9]."]),
    )
    await execute(instance)
    complete = next(payload for name, payload in admin.calls if name == "complete_rag_run")
    assert complete["p_answer_status"] == "grounded"
    assert complete["p_content"] == "Rotate the emergency token [C1]."
    assert [item["citation_id"] for item in complete["p_citations"]] == ["C1"]
    events = [
        payload["p_event_type"] for name, payload in admin.calls if name == "append_rag_run_event"
    ]
    assert "answer.delta" in events
    assert events[-1] == "run.completed"


async def test_missing_or_invalid_evidence_returns_controlled_fallback() -> None:
    admin = Admin()
    generation = Generation(["An unsupported answer [C9]."])
    await execute(service(admin, retrieval_response(), generation))
    complete = next(payload for name, payload in admin.calls if name == "complete_rag_run")
    assert complete["p_answer_status"] == "insufficient_evidence"
    assert complete["p_citations"] == []

    no_evidence_admin = Admin()
    unused_generation = Generation(["should not run"])
    await execute(service(no_evidence_admin, retrieval_response(items=False), unused_generation))
    assert unused_generation.called is False
    fallback = next(
        payload for name, payload in no_evidence_admin.calls if name == "complete_rag_run"
    )
    assert fallback["p_answer_status"] == "insufficient_evidence"


async def test_provider_failure_is_durable_and_sanitized() -> None:
    admin = Admin()
    await execute(service(admin, retrieval_response(), Generation(error=True)))
    transition = next(
        payload
        for name, payload in admin.calls
        if name == "transition_rag_run" and payload["p_status"] == "failed"
    )
    assert transition["p_error"]["code"] == "GENERATION_FAILED"
    assert any(
        payload["p_event_type"] == "run.failed"
        for name, payload in admin.calls
        if name == "append_rag_run_event"
    )


async def test_cancellation_persists_cancelled_state() -> None:
    gate = asyncio.Event()
    entered = asyncio.Event()

    class BlockingGeneration(Generation):
        async def stream_answer(self, **kwargs: Any) -> AsyncIterator[str]:
            del kwargs
            entered.set()
            await gate.wait()
            yield "Late answer [C1]."

    admin = Admin()
    instance = service(admin, retrieval_response(), BlockingGeneration())
    task = asyncio.create_task(execute(instance))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert any(
        name == "transition_rag_run" and payload["p_status"] == "cancelled"
        for name, payload in admin.calls
    )


def test_confidence_combines_retrieval_coverage_review_and_conflict() -> None:
    response = retrieval_response()
    normal = confidence_score(response, coverage=1, review_score=1, conflicting=False)
    conflict = confidence_score(response, coverage=1, review_score=1, conflicting=True)
    assert normal > 0.8
    assert conflict == 0.35
