import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
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
CONVERSATION_ID = UUID("90000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 7, 29, tzinfo=UTC)


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
        run_summary = {
            "id": str(RUN_ID),
            "conversation_id": str(CONVERSATION_ID),
            "status": "completed",
            "mode": "simple",
            "step_count": 1,
            "confidence": 0.9,
            "answer_status": "grounded",
            "question": "How is the token rotated?",
            "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
            "completed_at": NOW.isoformat(),
        }
        if name == "list_rag_runs":
            return {"items": [run_summary], "next_cursor": None}
        if name == "get_agent_run_trace":
            return {"run": run_summary, "steps": [], "tool_calls": []}
        if name == "get_workspace_usage":
            return {
                "documents": 2,
                "document_bytes": 2048,
                "ready_documents": 1,
                "conversations": 1,
                "runs": 1,
                "approvals": 0,
                "memories": 3,
            }
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
        conversation_id=UUID(int=10),
        source_message_id=MESSAGE_ID,
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


async def test_product_read_models_use_workspace_scoped_rpcs() -> None:
    admin = Admin()
    instance = service(admin, retrieval_response(), Generation())

    runs = await instance.list_runs(workspace_id=WORKSPACE_ID, actor_id=USER_ID, limit=20)
    trace = await instance.get_run_trace(workspace_id=WORKSPACE_ID, actor_id=USER_ID, run_id=RUN_ID)
    usage = await instance.workspace_usage(workspace_id=WORKSPACE_ID, actor_id=USER_ID)

    assert runs.items[0].question == "How is the token rotated?"
    assert trace.run.id == RUN_ID
    assert usage.document_bytes == 2048
    assert [name for name, _ in admin.calls] == [
        "list_rag_runs",
        "get_agent_run_trace",
        "get_workspace_usage",
    ]


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


async def test_service_conversation_run_and_event_snapshots() -> None:
    class SnapshotAdmin(Admin):
        async def rpc(self, name: str, payload: dict[str, Any]) -> Any:  # noqa: PLR0911
            self.calls.append((name, payload))
            conversation = {
                "id": str(CONVERSATION_ID),
                "workspace_id": str(WORKSPACE_ID),
                "owner_id": str(USER_ID),
                "title": "Policy",
                "summary": None,
                "summary_through_message_id": None,
                "summary_message_count": 0,
                "summary_updated_at": None,
                "created_at": NOW.isoformat(),
                "updated_at": NOW.isoformat(),
            }
            run = {
                "id": str(RUN_ID),
                "conversation_id": str(CONVERSATION_ID),
                "status": "running",
                "mode": "simple",
                "current_node": "retrieval",
                "step_count": 1,
                "confidence": None,
                "answer_status": None,
                "output_message_id": None,
                "error": None,
                "created_at": NOW.isoformat(),
                "updated_at": NOW.isoformat(),
                "completed_at": None,
            }
            if name == "create_conversation":
                return conversation
            if name == "list_conversations":
                return {"items": [conversation], "next_cursor": None}
            if name == "get_conversation":
                return {**conversation, "messages": []}
            if name == "start_rag_run":
                return {
                    "run_id": str(RUN_ID),
                    "message_id": str(MESSAGE_ID),
                    "status": "completed",
                    "events_url": f"/v1/runs/{RUN_ID}/events",
                }
            if name in {"get_rag_run", "request_rag_run_cancel"}:
                return run
            if name == "get_rag_run_events":
                return [
                    {
                        "id": str(UUID(int=12)),
                        "sequence": 1,
                        "event_type": "run.status_changed",
                        "payload": {"status": "running"},
                        "occurred_at": NOW.isoformat(),
                    }
                ]
            return True

    admin = SnapshotAdmin()
    instance = service(admin, retrieval_response(), Generation())

    created = await instance.create_conversation(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        title="Policy",
        idempotency_key="0123456789abcdef",
    )
    listed = await instance.list_conversations(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        limit=10,
    )
    detail = await instance.get_conversation(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
    )
    snapshot = await instance.get_run(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        run_id=RUN_ID,
    )
    cancelled = await instance.cancel(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        run_id=RUN_ID,
    )
    events = await instance.events(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        run_id=RUN_ID,
        after_sequence=0,
    )
    simple = await instance.start_run(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        request_id=UUID(int=14),
        idempotency_key="0123456789abcdef",
        body=CreateMessageRequest(content="What is the policy?", force_mode="simple"),
    )
    agentic = await instance.start_run(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        request_id=UUID(int=15),
        idempotency_key="fedcba9876543210",
        body=CreateMessageRequest(content="Compare the policy.", force_mode="agentic"),
    )

    assert created.title == "Policy"
    assert created.summary_message_count == 0
    assert listed.items[0].id == CONVERSATION_ID
    assert detail.messages == []
    assert snapshot.status == "running"
    assert cancelled.id == RUN_ID
    assert events[0]["sequence"] == 1
    assert simple.status == "completed"
    assert agentic.status == "completed"
    modes = [payload["p_mode"] for name, payload in admin.calls if name == "start_rag_run"]
    assert modes == ["simple", "agentic"]


async def test_start_run_dispatches_simple_and_agentic_background_paths() -> None:
    class AcceptedAdmin(Admin):
        async def rpc(self, name: str, payload: dict[str, Any]) -> Any:
            self.calls.append((name, payload))
            if name == "attach_rag_run_correlation":
                return None
            assert name == "start_rag_run"
            return {
                "run_id": str(RUN_ID),
                "message_id": str(MESSAGE_ID),
                "status": "accepted",
                "events_url": f"/v1/runs/{RUN_ID}/events",
            }

    simple = service(AcceptedAdmin(), retrieval_response(), Generation())
    simple._execute = AsyncMock()  # type: ignore[method-assign]
    accepted = await simple.start_run(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        request_id=UUID(int=16),
        idempotency_key="0123456789abcdef",
        body=CreateMessageRequest(content="What is the policy?", force_mode="simple"),
    )
    await asyncio.sleep(0)
    simple._execute.assert_awaited_once()
    assert accepted.status == "accepted"

    agentic = service(AcceptedAdmin(), retrieval_response(), Generation())
    agentic._execute_agentic = AsyncMock()  # type: ignore[method-assign]
    await agentic.start_run(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        request_id=UUID(int=17),
        idempotency_key="fedcba9876543210",
        body=CreateMessageRequest(content="Compare the policy.", force_mode="agentic"),
    )
    await asyncio.sleep(0)
    agentic._execute_agentic.assert_awaited_once()


async def test_memory_lifecycle_is_isolated_from_answer_failures() -> None:
    class Memory:
        def __init__(self, *, fail: bool = False) -> None:
            self.fail = fail
            self.maintained = False

        async def remember_explicit(self, **kwargs: Any) -> bool:
            del kwargs
            return True

        async def prompt_context(self, **kwargs: Any) -> str:
            del kwargs
            if self.fail:
                raise RuntimeError("memory offline")
            return "<untrusted_memory>preference</untrusted_memory>"

        async def maintain_conversation(self, **kwargs: Any) -> None:
            del kwargs
            self.maintained = True

    instance = service(Admin(), retrieval_response(), Generation())
    memory = Memory()
    instance.memory = memory  # type: ignore[assignment]
    context = await instance._prepare_memory(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        source_message_id=MESSAGE_ID,
        message="Remember that I prefer concise answers.",
    )
    await instance._maintain_memory(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
    )
    assert "untrusted_memory" in context
    assert memory.maintained is True

    instance.memory = Memory(fail=True)  # type: ignore[assignment]
    assert (
        await instance._prepare_memory(
            workspace_id=WORKSPACE_ID,
            actor_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            source_message_id=MESSAGE_ID,
            message="Question",
        )
        == ""
    )

    sleeping = asyncio.create_task(asyncio.sleep(60))
    instance._tasks[RUN_ID] = sleeping
    await instance.aclose()
    assert sleeping.cancelled()


async def test_resume_rejects_unconfigured_and_terminal_simple_runs() -> None:
    unconfigured = service(Admin(), retrieval_response(), Generation())
    with pytest.raises(ApplicationError) as unavailable:
        await unconfigured.resume(
            workspace_id=WORKSPACE_ID,
            actor_id=USER_ID,
            run_id=RUN_ID,
        )
    assert unavailable.value.code == "AGENTIC_MODE_NOT_CONFIGURED"

    class RunAdmin(Admin):
        async def rpc(self, name: str, payload: dict[str, Any]) -> Any:
            del payload
            assert name == "get_rag_run"
            return {
                "id": str(RUN_ID),
                "conversation_id": str(CONVERSATION_ID),
                "status": "completed",
                "mode": "simple",
                "current_node": "complete",
                "step_count": 3,
                "confidence": 1,
                "answer_status": "grounded",
                "output_message_id": str(MESSAGE_ID),
                "error": None,
                "created_at": NOW.isoformat(),
                "updated_at": NOW.isoformat(),
                "completed_at": NOW.isoformat(),
            }

    terminal = service(RunAdmin(), retrieval_response(), Generation())
    terminal.orchestrator = object()  # type: ignore[assignment]
    with pytest.raises(ApplicationError) as not_resumable:
        await terminal.resume(
            workspace_id=WORKSPACE_ID,
            actor_id=USER_ID,
            run_id=RUN_ID,
        )
    assert not_resumable.value.code == "AGENT_RUN_NOT_RESUMABLE"
