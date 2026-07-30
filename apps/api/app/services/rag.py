import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, time
from typing import Any, Literal, Protocol, cast
from uuid import UUID, uuid4

from app.agents.models import AgentState
from app.agents.orchestrator import AgentOrchestrator
from app.agents.router import route_request
from app.api.errors import ApplicationError
from app.core.logging import get_logger
from app.infrastructure.supabase.admin import SupabaseAdminClient
from app.models.rag import (
    Citation,
    Conversation,
    ConversationDetail,
    ConversationPage,
    CreateMessageRequest,
    ObservabilityTrace,
    ReplayRunRequest,
    Run,
    RunAccepted,
    RunPage,
    RunTrace,
    WorkspaceObservability,
    WorkspaceUsage,
)
from app.models.retrieval import RetrievalFilters, RetrievalRequest, RetrievalResponse
from app.services.approvals import ApprovalService
from app.services.content_security import sanitize_untrusted_text
from app.services.memory import MemoryService
from app.services.retrieval import HybridRetrievalService

PROMPT_VERSION = "rag-system-v2+answer-v2+memory-v1+injection-v1"
LEGACY_PROMPT_VERSION = "rag-system-v1+answer-v1+memory-v1+injection-v1"
AGENT_PROMPT_VERSION = "agent-system-v1+memory-v1+injection-v1"
PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
SYSTEM_PROMPT = (PROMPT_DIR / "rag_system_v2.txt").read_text(encoding="utf-8").strip()
ANSWER_PROMPT = (PROMPT_DIR / "rag_answer_v2.txt").read_text(encoding="utf-8").strip()
LEGACY_SYSTEM_PROMPT = (PROMPT_DIR / "rag_system_v1.txt").read_text(encoding="utf-8").strip()
LEGACY_ANSWER_PROMPT = (PROMPT_DIR / "rag_answer_v1.txt").read_text(encoding="utf-8").strip()
CITATION_PATTERN = re.compile(r"\[(C[1-9][0-9]*)\]")
SEGMENT_BOUNDARY = re.compile(r"(?:[.!?](?:\s+|$)|\n+)")
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "timed_out"}
STREAM_END_STATUSES = TERMINAL_STATUSES | {"awaiting_approval"}
INSUFFICIENT_ANSWER = (
    "I do not have enough evidence in the selected workspace documents to answer that question."
)


class StreamingGenerationClient(Protocol):
    model: str

    def stream_answer(self, *, system_prompt: str, prompt: str) -> AsyncIterator[str]: ...


@dataclass(frozen=True)
class RagConfig:
    evidence_limit: int = 4
    candidate_count: int = 30
    timeout_seconds: float = 30
    insufficient_semantic_threshold: float = 0.25
    event_poll_seconds: float = 0.1
    heartbeat_seconds: float = 15


@dataclass(frozen=True)
class PromptBundle:
    version: str
    system_prompt: str
    answer_prompt: str


CURRENT_PROMPT_BUNDLE = PromptBundle(PROMPT_VERSION, SYSTEM_PROMPT, ANSWER_PROMPT)
SUPPORTED_PROMPT_BUNDLES = {
    PROMPT_VERSION: CURRENT_PROMPT_BUNDLE,
    LEGACY_PROMPT_VERSION: PromptBundle(
        LEGACY_PROMPT_VERSION,
        LEGACY_SYSTEM_PROMPT,
        LEGACY_ANSWER_PROMPT,
    ),
}


@dataclass(frozen=True)
class ValidatedAnswer:
    content: str
    citation_ids: set[str]
    answer_status: str
    coverage: float
    review_score: float


def _split_complete_segments(buffer: str, *, final: bool = False) -> tuple[list[str], str]:
    segments: list[str] = []
    consumed = 0
    for match in SEGMENT_BOUNDARY.finditer(buffer):
        segment = buffer[consumed : match.end()].strip()
        consumed = match.end()
        if segment:
            segments.append(segment)
    remainder = buffer[consumed:]
    if final and remainder.strip():
        segments.append(remainder.strip())
        remainder = ""
    return segments, remainder


def _validate_segments(
    segments: list[str],
    *,
    allowed: set[str],
) -> tuple[list[str], set[str], int, int, bool]:
    valid: list[str] = []
    used: set[str] = set()
    reviewed = 0
    accepted = 0
    conflict = False
    for original in segments:
        segment = original.strip()
        if not segment:
            continue
        if segment == "INSUFFICIENT_EVIDENCE":
            return [], set(), 1, 0, False
        if segment.startswith("CONFLICTING_EVIDENCE"):
            conflict = True
            segment = segment.removeprefix("CONFLICTING_EVIDENCE").lstrip(": \n")
            if not segment:
                continue
        reviewed += 1
        citations = set(CITATION_PATTERN.findall(segment))
        if citations and citations <= allowed:
            valid.append(segment)
            used.update(citations)
            accepted += 1
    return valid, used, reviewed, accepted, conflict


def confidence_score(
    retrieval: RetrievalResponse,
    *,
    coverage: float,
    review_score: float,
    conflicting: bool,
) -> float:
    if not retrieval.items:
        return 0
    top = retrieval.items[0]
    semantic = max(0.0, min(float(top.semantic_score or 0), 1.0))
    sparse = 0.8 if top.sparse_rank == 1 else 0.6 if top.sparse_rank is not None else 0.0
    retrieval_quality = max(semantic, sparse)
    score = 0.45 * retrieval_quality + 0.35 * coverage + 0.20 * review_score
    if conflicting:
        score = min(score, 0.35)
    return round(max(0.0, min(score, 1.0)), 4)


class GroundedRagService:
    def __init__(  # noqa: PLR0913
        self,
        *,
        admin: SupabaseAdminClient,
        retrieval: HybridRetrievalService,
        generation: StreamingGenerationClient,
        config: RagConfig,
        orchestrator: AgentOrchestrator | None = None,
        memory: MemoryService | None = None,
        approvals: ApprovalService | None = None,
    ) -> None:
        self.admin = admin
        self.retrieval = retrieval
        self.generation = generation
        self.config = config
        self.orchestrator = orchestrator
        self.memory = memory
        self.approvals = approvals
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    async def aclose(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def create_conversation(
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        title: str | None,
        idempotency_key: str,
    ) -> Conversation:
        result = await self.admin.rpc(
            "create_conversation",
            {
                "p_workspace_id": str(workspace_id),
                "p_actor_id": str(actor_id),
                "p_title": title,
                "p_create_key": idempotency_key,
            },
        )
        return Conversation.model_validate(result)

    async def list_conversations(
        self, *, workspace_id: UUID, actor_id: UUID, limit: int
    ) -> ConversationPage:
        return ConversationPage.model_validate(
            await self.admin.rpc(
                "list_conversations",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_limit": limit,
                },
            )
        )

    async def get_conversation(
        self, *, workspace_id: UUID, actor_id: UUID, conversation_id: UUID
    ) -> ConversationDetail:
        return ConversationDetail.model_validate(
            await self.admin.rpc(
                "get_conversation",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_conversation_id": str(conversation_id),
                },
            )
        )

    async def start_run(  # noqa: PLR0913
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        conversation_id: UUID,
        request_id: UUID,
        idempotency_key: str,
        body: CreateMessageRequest,
    ) -> RunAccepted:
        decision = route_request(body)
        accepted = RunAccepted.model_validate(
            await self.admin.rpc(
                "start_rag_run",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_conversation_id": str(conversation_id),
                    "p_content": body.content,
                    "p_document_ids": (
                        [str(document_id) for document_id in body.document_ids]
                        if body.document_ids
                        else None
                    ),
                    "p_request_key": idempotency_key,
                    "p_prompt_version": (
                        AGENT_PROMPT_VERSION if decision.mode == "agentic" else PROMPT_VERSION
                    ),
                    "p_model": self.generation.model,
                    "p_mode": decision.mode,
                },
            )
        )
        await self.admin.rpc(
            "attach_rag_run_correlation",
            {
                "p_run_id": str(accepted.run_id),
                "p_workspace_id": str(workspace_id),
                "p_request_id": str(request_id),
            },
        )
        if accepted.status == "accepted" and accepted.run_id not in self._tasks:
            operation = (
                self._execute_agentic(
                    run_id=accepted.run_id,
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    body=body,
                    route_reason=decision.reason,
                    conversation_id=conversation_id,
                    source_message_id=accepted.message_id,
                )
                if decision.mode == "agentic"
                else self._execute(
                    run_id=accepted.run_id,
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    body=body,
                    conversation_id=conversation_id,
                    source_message_id=accepted.message_id,
                )
            )
            task = asyncio.create_task(operation, name=f"rag-run-{accepted.run_id}")
            self._tasks[accepted.run_id] = task
            task.add_done_callback(lambda _: self._tasks.pop(accepted.run_id, None))
        return accepted

    async def replay_run(  # noqa: PLR0913
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        source_run_id: UUID,
        request_id: UUID,
        idempotency_key: str,
        body: ReplayRunRequest,
    ) -> RunAccepted:
        snapshot = cast(
            dict[str, Any],
            await self.admin.rpc(
                "get_rag_replay_snapshot",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_run_id": str(source_run_id),
                },
            ),
        )
        replay_body = CreateMessageRequest(
            content=str(snapshot["question"]),
            document_ids=snapshot.get("document_ids"),
            force_mode=(
                cast(Literal["simple", "agentic"], snapshot["mode"])
                if body.mode == "exact_snapshot"
                else "auto"
            ),
        )
        decision = route_request(replay_body)
        stored_prompt_version = str(snapshot["prompt_version"])
        prompt_version = (
            AGENT_PROMPT_VERSION
            if decision.mode == "agentic"
            else stored_prompt_version
            if body.mode == "exact_snapshot"
            else PROMPT_VERSION
        )
        model = str(snapshot["model"]) if body.mode == "exact_snapshot" else self.generation.model
        exact_prompt_bundle: PromptBundle | None = None
        exact_prompt_supported = (
            stored_prompt_version in {AGENT_PROMPT_VERSION, LEGACY_PROMPT_VERSION, PROMPT_VERSION}
            if snapshot["mode"] == "agentic"
            else prompt_version in SUPPORTED_PROMPT_BUNDLES
        )
        if body.mode == "exact_snapshot" and (
            model != self.generation.model or not exact_prompt_supported
        ):
            raise ApplicationError(
                "REPLAY_SNAPSHOT_UNAVAILABLE",
                "Exact replay is unavailable",
                (
                    "The stored model or prompt version is no longer available. "
                    "Use current configuration."
                ),
                status=409,
            )
        if body.mode == "exact_snapshot" and snapshot["mode"] == "simple":
            exact_prompt_bundle = SUPPORTED_PROMPT_BUNDLES[prompt_version]
        accepted = RunAccepted.model_validate(
            await self.admin.rpc(
                "start_rag_run",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_conversation_id": str(snapshot["conversation_id"]),
                    "p_content": replay_body.content,
                    "p_document_ids": (
                        [str(document_id) for document_id in replay_body.document_ids]
                        if replay_body.document_ids
                        else None
                    ),
                    "p_request_key": idempotency_key,
                    "p_prompt_version": prompt_version,
                    "p_model": model,
                    "p_mode": decision.mode,
                },
            )
        )
        await self.admin.rpc(
            "attach_rag_run_correlation",
            {
                "p_run_id": str(accepted.run_id),
                "p_workspace_id": str(workspace_id),
                "p_request_id": str(request_id),
            },
        )
        await self.admin.rpc(
            "mark_rag_run_replay",
            {
                "p_run_id": str(accepted.run_id),
                "p_workspace_id": str(workspace_id),
                "p_source_run_id": str(source_run_id),
                "p_replay_mode": body.mode,
                "p_reason": body.reason,
            },
        )
        if accepted.status == "accepted" and accepted.run_id not in self._tasks:
            operation = (
                self._execute_agentic(
                    run_id=accepted.run_id,
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    body=replay_body,
                    route_reason=f"Replay ({body.mode}): {decision.reason}",
                    conversation_id=UUID(str(snapshot["conversation_id"])),
                    source_message_id=accepted.message_id,
                )
                if decision.mode == "agentic"
                else self._execute(
                    run_id=accepted.run_id,
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    body=replay_body,
                    conversation_id=UUID(str(snapshot["conversation_id"])),
                    source_message_id=accepted.message_id,
                    prompt_bundle=exact_prompt_bundle,
                )
            )
            task = asyncio.create_task(operation, name=f"rag-replay-{accepted.run_id}")
            self._tasks[accepted.run_id] = task
            task.add_done_callback(lambda _: self._tasks.pop(accepted.run_id, None))
        return accepted

    async def get_run(self, *, workspace_id: UUID, actor_id: UUID, run_id: UUID) -> Run:
        return Run.model_validate(
            await self.admin.rpc(
                "get_rag_run",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_run_id": str(run_id),
                },
            )
        )

    async def list_runs(self, *, workspace_id: UUID, actor_id: UUID, limit: int) -> RunPage:
        return RunPage.model_validate(
            await self.admin.rpc(
                "list_rag_runs",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_limit": limit,
                },
            )
        )

    async def get_run_trace(self, *, workspace_id: UUID, actor_id: UUID, run_id: UUID) -> RunTrace:
        return RunTrace.model_validate(
            await self.admin.rpc(
                "get_agent_run_trace",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_run_id": str(run_id),
                },
            )
        )

    async def get_observability_trace(
        self, *, workspace_id: UUID, actor_id: UUID, run_id: UUID
    ) -> ObservabilityTrace:
        return ObservabilityTrace.model_validate(
            await self.admin.rpc(
                "get_run_observability_trace",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_run_id": str(run_id),
                },
            )
        )

    async def observability_summary(
        self, *, workspace_id: UUID, actor_id: UUID
    ) -> WorkspaceObservability:
        return WorkspaceObservability.model_validate(
            await self.admin.rpc(
                "get_workspace_observability",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                },
            )
        )

    async def _record_telemetry(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        question: str,
        answer: str,
        timings: dict[str, float],
    ) -> None:
        await self.admin.rpc(
            "record_rag_run_telemetry",
            {
                "p_run_id": str(run_id),
                "p_workspace_id": str(workspace_id),
                "p_input_tokens": max(1, (len(question) + 3) // 4),
                "p_output_tokens": max(1, (len(answer) + 3) // 4),
                "p_token_usage_source": "estimated",
                "p_timings": timings,
            },
        )

    async def workspace_usage(self, *, workspace_id: UUID, actor_id: UUID) -> WorkspaceUsage:
        return WorkspaceUsage.model_validate(
            await self.admin.rpc(
                "get_workspace_usage",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                },
            )
        )

    async def cancel(self, *, workspace_id: UUID, actor_id: UUID, run_id: UUID) -> Run:
        result = Run.model_validate(
            await self.admin.rpc(
                "request_rag_run_cancel",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_run_id": str(run_id),
                },
            )
        )
        task = self._tasks.get(run_id)
        if task is not None:
            task.cancel()
        return result

    async def events(
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        run_id: UUID,
        after_sequence: int,
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            await self.admin.rpc(
                "get_rag_run_events",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_run_id": str(run_id),
                    "p_after_sequence": after_sequence,
                },
            ),
        )

    async def resume(self, *, workspace_id: UUID, actor_id: UUID, run_id: UUID) -> Run:
        if self.orchestrator is None:
            raise ApplicationError(
                "AGENTIC_MODE_NOT_CONFIGURED",
                "Agentic mode unavailable",
                "The agent orchestrator is not configured.",
                status=503,
            )
        run = await self.get_run(workspace_id=workspace_id, actor_id=actor_id, run_id=run_id)
        if run.mode != "agentic" or run.status not in {
            "accepted",
            "running",
            "failed",
            "timed_out",
        }:
            raise ApplicationError(
                "AGENT_RUN_NOT_RESUMABLE",
                "Agent run is not resumable",
                "Only incomplete agentic runs with a durable checkpoint can resume.",
                status=409,
            )
        checkpoint = await self.orchestrator.load_checkpoint(run_id, workspace_id)
        if checkpoint is None:
            raise ApplicationError(
                "AGENT_CHECKPOINT_NOT_FOUND",
                "Agent checkpoint not found",
                "No durable workflow checkpoint exists for this run.",
                status=404,
            )
        checkpoint["started_at"] = time()
        await self.admin.rpc(
            "resume_agent_run",
            {
                "p_workspace_id": str(workspace_id),
                "p_actor_id": str(actor_id),
                "p_run_id": str(run_id),
            },
        )
        if run_id not in self._tasks:
            task = asyncio.create_task(
                self._execute_agentic_state(checkpoint),
                name=f"agent-resume-{run_id}",
            )
            self._tasks[run_id] = task
            task.add_done_callback(lambda _: self._tasks.pop(run_id, None))
        return await self.get_run(workspace_id=workspace_id, actor_id=actor_id, run_id=run_id)

    async def resume_from_review(self, *, run_id: UUID, workspace_id: UUID) -> None:
        if self.orchestrator is None or run_id in self._tasks:
            return
        checkpoint = await self.orchestrator.load_checkpoint(run_id, workspace_id)
        if checkpoint is None:
            return
        checkpoint["started_at"] = time()
        task = asyncio.create_task(
            self._execute_agentic_state(checkpoint),
            name=f"agent-review-resume-{run_id}",
        )
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))

    async def _execute_agentic(  # noqa: PLR0913
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
        request_id: UUID,
        body: CreateMessageRequest,
        route_reason: str,
        conversation_id: UUID,
        source_message_id: UUID,
    ) -> None:
        memory_context = await self._prepare_memory(
            workspace_id=workspace_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            message=body.content,
        )
        state: AgentState = {
            "run_id": str(run_id),
            "workspace_id": str(workspace_id),
            "actor_id": str(actor_id),
            "request_id": str(request_id),
            "question": body.content,
            "document_ids": (
                [str(document_id) for document_id in body.document_ids]
                if body.document_ids
                else None
            ),
            "step_count": 0,
            "started_at": time(),
            "resume_node": "supervisor",
            "route_reason": route_reason,
            "conversation_id": str(conversation_id),
            "source_message_id": str(source_message_id),
            "memory_context": memory_context,
        }
        await self._execute_agentic_state(state)

    async def _execute_agentic_state(self, state: AgentState) -> None:
        run_id = UUID(state["run_id"])
        workspace_id = UUID(state["workspace_id"])
        started = perf_counter()
        try:
            if self.orchestrator is None:
                raise ApplicationError(
                    "AGENTIC_MODE_NOT_CONFIGURED",
                    "Agentic mode unavailable",
                    "The agent orchestrator is not configured.",
                    status=503,
                )
            await self._transition(run_id, workspace_id, "running", state["resume_node"])
            await self._event(
                run_id,
                workspace_id,
                "run.status_changed",
                {"previous_status": "accepted", "status": "running"},
            )
            result = await self.orchestrator.run(state)
            if result.retrieval_trace_ids:
                await self.admin.rpc(
                    "store_rag_evidence",
                    {
                        "p_run_id": str(run_id),
                        "p_workspace_id": str(workspace_id),
                        "p_retrieval_trace_id": result.retrieval_trace_ids[0],
                        "p_evidence": result.evidence,
                    },
                )
            citations = [
                Citation.model_validate(item).model_dump(mode="json")
                for item in result.evidence
                if item["citation_id"] in result.citation_ids
            ]
            if citations:
                await self._event(
                    run_id, workspace_id, "citations.available", {"citations": citations}
                )
            if self.approvals is not None:
                approval = await self.approvals.maybe_pause(
                    state=state,
                    result=result,
                    citations=citations,
                )
                if approval is not None:
                    await self._event(
                        run_id,
                        workspace_id,
                        "run.awaiting_approval",
                        {
                            "approval_id": str(approval.id),
                            "risk_level": approval.risk_level,
                            "reasons": approval.reasons,
                        },
                    )
                    return
            await self._event(run_id, workspace_id, "answer.delta", {"delta": result.content})
            timings = {"total_ms": round((perf_counter() - started) * 1000, 3)}
            completed = cast(
                dict[str, Any],
                await self.admin.rpc(
                    "complete_rag_run",
                    {
                        "p_run_id": str(run_id),
                        "p_workspace_id": str(workspace_id),
                        "p_content": result.content,
                        "p_answer_status": result.answer_status,
                        "p_confidence": result.confidence,
                        "p_citations": citations,
                        "p_model": self.generation.model,
                        "p_prompt_version": AGENT_PROMPT_VERSION,
                        "p_timings": timings,
                    },
                ),
            )
            if completed.get("cancelled"):
                return
            await self._record_telemetry(
                run_id=run_id,
                workspace_id=workspace_id,
                question=state["question"],
                answer=result.content,
                timings=timings,
            )
            await self._event(
                run_id,
                workspace_id,
                "run.completed",
                {
                    "message_id": completed["message_id"],
                    "answer_status": result.answer_status,
                    "confidence": result.confidence,
                    "duration_ms": round(timings["total_ms"]),
                },
            )
            if state.get("conversation_id"):
                await self._maintain_memory(
                    workspace_id=workspace_id,
                    actor_id=UUID(state["actor_id"]),
                    conversation_id=UUID(state["conversation_id"]),
                )
        except asyncio.CancelledError:
            await self._transition(run_id, workspace_id, "cancelled", "cancelled")
            await self._event(
                run_id,
                workspace_id,
                "run.status_changed",
                {"previous_status": "cancelling", "status": "cancelled"},
            )
            raise
        except ApplicationError as exc:
            if (
                exc.code
                in {
                    "AGENTIC_MODE_NOT_CONFIGURED",
                    "PROVIDER_BACKPRESSURE",
                    "PROVIDER_CIRCUIT_OPEN",
                }
                and state.get("conversation_id")
                and state.get("source_message_id")
            ):
                await self._event(
                    run_id,
                    workspace_id,
                    "run.degraded",
                    {"from": "agentic", "to": "simple", "reason": exc.code},
                )
                await self._execute(
                    run_id=run_id,
                    workspace_id=workspace_id,
                    actor_id=UUID(state["actor_id"]),
                    request_id=UUID(state["request_id"]),
                    body=CreateMessageRequest(
                        content=state["question"],
                        document_ids=(
                            [UUID(value) for value in cast(list[str], state["document_ids"])]
                            if state.get("document_ids")
                            else None
                        ),
                        force_mode="simple",
                    ),
                    conversation_id=UUID(state["conversation_id"]),
                    source_message_id=UUID(state["source_message_id"]),
                )
                return
            status = "timed_out" if exc.code == "AGENT_BUDGET_TIMEOUT" else "failed"
            await self._fail(
                run_id,
                workspace_id,
                code=exc.code,
                detail=exc.detail,
                retryable=exc.retryable,
                status=status,
                accumulated="",
                started=started,
            )
        except Exception:
            get_logger().exception("agent_run_failed", run_id=str(run_id))
            await self._fail(
                run_id,
                workspace_id,
                code="AGENT_RUN_FAILED",
                detail="The bounded agent workflow failed unexpectedly.",
                retryable=True,
                status="failed",
                accumulated="",
                started=started,
            )

    async def _execute(  # noqa: PLR0913
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
        request_id: UUID,
        body: CreateMessageRequest,
        conversation_id: UUID,
        source_message_id: UUID,
        prompt_bundle: PromptBundle | None = None,
    ) -> None:
        prompts = prompt_bundle or CURRENT_PROMPT_BUNDLE
        started = perf_counter()
        accumulated = ""
        timings: dict[str, float] = {}
        try:
            async with asyncio.timeout(self.config.timeout_seconds):
                await self._transition(run_id, workspace_id, "running", "retrieval")
                await self._event(
                    run_id,
                    workspace_id,
                    "run.status_changed",
                    {"previous_status": "accepted", "status": "running"},
                )
                retrieval_started = perf_counter()
                retrieval, memory_context = await asyncio.gather(
                    self.retrieval.search(
                        workspace_id=workspace_id,
                        actor_id=actor_id,
                        request_id=request_id,
                        request=RetrievalRequest(
                            query=body.content,
                            mode="hybrid",
                            limit=self.config.evidence_limit,
                            candidate_count=self.config.candidate_count,
                            filters=RetrievalFilters(document_ids=body.document_ids),
                        ),
                    ),
                    self._prepare_memory(
                        workspace_id=workspace_id,
                        actor_id=actor_id,
                        conversation_id=conversation_id,
                        source_message_id=source_message_id,
                        message=body.content,
                    ),
                )
                timings["retrieval_ms"] = round((perf_counter() - retrieval_started) * 1000, 3)
                evidence = self._evidence(retrieval)
                await self.admin.rpc(
                    "store_rag_evidence",
                    {
                        "p_run_id": str(run_id),
                        "p_workspace_id": str(workspace_id),
                        "p_retrieval_trace_id": str(retrieval.trace_id),
                        "p_evidence": evidence,
                    },
                )
                await self._event(
                    run_id,
                    workspace_id,
                    "retrieval.completed",
                    {
                        "query_id": str(retrieval.trace_id),
                        "dense_candidates": retrieval.dense_candidate_count,
                        "sparse_candidates": retrieval.sparse_candidate_count,
                        "selected_chunks": len(evidence),
                        "duration_ms": round(retrieval.total_ms),
                        "cache_hit": retrieval.cache_hit,
                        "evidence": [
                            {
                                "document_id": item["document_id"],
                                "chunk_id": item["chunk_id"],
                                "dense_rank": item["semantic_rank"],
                                "sparse_rank": item["sparse_rank"],
                                "fused_score": item["rrf_score"],
                            }
                            for item in evidence
                        ],
                    },
                )
                if self._insufficient(retrieval):
                    await self._complete_insufficient(
                        run_id,
                        workspace_id,
                        body.content,
                        retrieval,
                        timings,
                        started,
                        prompt_version=prompts.version,
                    )
                    await self._maintain_memory(
                        workspace_id=workspace_id,
                        actor_id=actor_id,
                        conversation_id=conversation_id,
                    )
                    return

                await self._transition(run_id, workspace_id, "running", "generation")
                generation_started = perf_counter()
                answer = await self._generate_validated(
                    run_id=run_id,
                    workspace_id=workspace_id,
                    question=body.content,
                    evidence=evidence,
                    memory_context=memory_context,
                    prompt_bundle=prompts,
                )
                timings["generation_ms"] = round((perf_counter() - generation_started) * 1000, 3)
                timings["total_ms"] = round((perf_counter() - started) * 1000, 3)
                retrieval_quality_confidence = confidence_score(
                    retrieval,
                    coverage=answer.coverage,
                    review_score=answer.review_score,
                    conflicting=answer.answer_status == "insufficient_evidence",
                )
                citations = [
                    Citation.model_validate(item).model_dump(mode="json")
                    for item in evidence
                    if item["citation_id"] in answer.citation_ids
                ]
                if citations:
                    await self._event(
                        run_id,
                        workspace_id,
                        "citations.available",
                        {"citations": citations},
                    )
                completed = cast(
                    dict[str, Any],
                    await self.admin.rpc(
                        "complete_rag_run",
                        {
                            "p_run_id": str(run_id),
                            "p_workspace_id": str(workspace_id),
                            "p_content": answer.content,
                            "p_answer_status": answer.answer_status,
                            "p_confidence": retrieval_quality_confidence,
                            "p_citations": citations,
                            "p_model": self.generation.model,
                            "p_prompt_version": prompts.version,
                            "p_timings": timings,
                        },
                    ),
                )
                if completed.get("cancelled"):
                    await self._event(
                        run_id,
                        workspace_id,
                        "run.status_changed",
                        {"previous_status": "cancelling", "status": "cancelled"},
                    )
                    return
                await self._record_telemetry(
                    run_id=run_id,
                    workspace_id=workspace_id,
                    question=body.content,
                    answer=answer.content,
                    timings=timings,
                )
                await self._event(
                    run_id,
                    workspace_id,
                    "run.completed",
                    {
                        "message_id": completed["message_id"],
                        "answer_status": answer.answer_status,
                        "confidence": retrieval_quality_confidence,
                        "duration_ms": round(timings["total_ms"]),
                    },
                )
                await self._maintain_memory(
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    conversation_id=conversation_id,
                )
        except asyncio.CancelledError:
            timings["total_ms"] = round((perf_counter() - started) * 1000, 3)
            await self._transition(
                run_id,
                workspace_id,
                "cancelled",
                "cancelled",
                accumulated_text=accumulated or None,
                timings=timings,
            )
            await self._event(
                run_id,
                workspace_id,
                "run.status_changed",
                {"previous_status": "cancelling", "status": "cancelled"},
            )
            raise
        except TimeoutError:
            await self._fail(
                run_id,
                workspace_id,
                code="RAG_RUN_TIMEOUT",
                detail="The grounded answer exceeded its execution deadline.",
                retryable=True,
                status="timed_out",
                accumulated=accumulated,
                started=started,
            )
        except ApplicationError as exc:
            await self._fail(
                run_id,
                workspace_id,
                code=exc.code,
                detail=exc.detail,
                retryable=exc.retryable,
                status="failed",
                accumulated=accumulated,
                started=started,
            )
        except Exception:
            get_logger().exception("rag_run_failed", run_id=str(run_id))
            await self._fail(
                run_id,
                workspace_id,
                code="RAG_RUN_FAILED",
                detail="The grounded answer run failed unexpectedly.",
                retryable=True,
                status="failed",
                accumulated=accumulated,
                started=started,
            )

    async def _generate_validated(  # noqa: PLR0913
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        question: str,
        evidence: list[dict[str, Any]],
        memory_context: str = "",
        prompt_bundle: PromptBundle | None = None,
    ) -> ValidatedAnswer:
        prompts = prompt_bundle or CURRENT_PROMPT_BUNDLE
        allowed = {str(item["citation_id"]) for item in evidence}
        context = "\n\n".join(
            f"[{item['citation_id']}] {item['label']}\n"
            f"<untrusted_evidence>{sanitize_untrusted_text(str(item['quote']))}</untrusted_evidence>"
            for item in evidence
        )
        prompt = prompts.answer_prompt.format(question=question, context=context)
        if memory_context:
            prompt = f"{prompt}\n\nConversation memory:\n{memory_context}"
        buffer = ""
        accepted_segments: list[str] = []
        used: set[str] = set()
        reviewed = 0
        accepted = 0
        conflict = False
        first_delta_at: float | None = None
        generation_started = perf_counter()
        async for delta in self.generation.stream_answer(
            system_prompt=prompts.system_prompt,
            prompt=prompt,
        ):
            buffer += delta
            segments, buffer = _split_complete_segments(buffer)
            valid, cited, count, accepted_count, has_conflict = _validate_segments(
                segments, allowed=allowed
            )
            reviewed += count
            accepted += accepted_count
            conflict = conflict or has_conflict
            for segment in valid:
                if first_delta_at is None:
                    first_delta_at = perf_counter()
                accepted_segments.append(segment)
                used.update(CITATION_PATTERN.findall(segment))
                await self._event(
                    run_id,
                    workspace_id,
                    "answer.delta",
                    {"delta": segment + "\n"},
                )
                await self._transition(
                    run_id,
                    workspace_id,
                    "running",
                    "generation",
                    accumulated_text="\n".join(accepted_segments),
                )
            used.update(cited)
        trailing, _ = _split_complete_segments(buffer, final=True)
        valid, cited, count, accepted_count, has_conflict = _validate_segments(
            trailing, allowed=allowed
        )
        reviewed += count
        accepted += accepted_count
        conflict = conflict or has_conflict
        for segment in valid:
            if first_delta_at is None:
                first_delta_at = perf_counter()
            accepted_segments.append(segment)
            await self._event(
                run_id,
                workspace_id,
                "answer.delta",
                {"delta": segment + "\n"},
            )
        used.update(cited)
        coverage = accepted / reviewed if reviewed else 0
        review_score = 1.0 if coverage == 1 else 0.5 if coverage > 0 else 0.0
        if not accepted_segments:
            await self._event(
                run_id,
                workspace_id,
                "answer.delta",
                {"delta": INSUFFICIENT_ANSWER},
            )
            return ValidatedAnswer(
                content=INSUFFICIENT_ANSWER,
                citation_ids=set(),
                answer_status="insufficient_evidence",
                coverage=coverage,
                review_score=review_score,
            )
        content = "\n".join(accepted_segments)
        if first_delta_at is not None:
            get_logger().info(
                "rag_first_validated_token",
                run_id=str(run_id),
                time_to_first_token_ms=round((first_delta_at - generation_started) * 1000, 3),
            )
        return ValidatedAnswer(
            content=content,
            citation_ids=used,
            answer_status="insufficient_evidence" if conflict else "grounded",
            coverage=coverage,
            review_score=review_score,
        )

    async def _complete_insufficient(  # noqa: PLR0913, PLR0917
        self,
        run_id: UUID,
        workspace_id: UUID,
        question: str,
        retrieval: RetrievalResponse,
        timings: dict[str, float],
        started: float,
        *,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        await self._event(run_id, workspace_id, "answer.delta", {"delta": INSUFFICIENT_ANSWER})
        timings["total_ms"] = round((perf_counter() - started) * 1000, 3)
        completed = cast(
            dict[str, Any],
            await self.admin.rpc(
                "complete_rag_run",
                {
                    "p_run_id": str(run_id),
                    "p_workspace_id": str(workspace_id),
                    "p_content": INSUFFICIENT_ANSWER,
                    "p_answer_status": "insufficient_evidence",
                    "p_confidence": confidence_score(
                        retrieval, coverage=0, review_score=1, conflicting=False
                    ),
                    "p_citations": [],
                    "p_model": self.generation.model,
                    "p_prompt_version": prompt_version,
                    "p_timings": timings,
                },
            ),
        )
        await self._record_telemetry(
            run_id=run_id,
            workspace_id=workspace_id,
            question=question,
            answer=INSUFFICIENT_ANSWER,
            timings=timings,
        )
        await self._event(
            run_id,
            workspace_id,
            "run.completed",
            {
                "message_id": completed["message_id"],
                "answer_status": "insufficient_evidence",
                "confidence": 0,
                "duration_ms": round(timings["total_ms"]),
            },
        )

    async def _prepare_memory(
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        conversation_id: UUID,
        source_message_id: UUID,
        message: str,
    ) -> str:
        if self.memory is None:
            return ""
        try:
            await self.memory.remember_explicit(
                workspace_id=workspace_id,
                actor_id=actor_id,
                conversation_id=conversation_id,
                source_message_id=source_message_id,
                message=message,
            )
            return await self.memory.prompt_context(
                workspace_id=workspace_id,
                actor_id=actor_id,
                conversation_id=conversation_id,
            )
        except Exception:
            get_logger().exception(
                "memory_context_unavailable",
                conversation_id=str(conversation_id),
            )
            return ""

    async def _maintain_memory(
        self, *, workspace_id: UUID, actor_id: UUID, conversation_id: UUID
    ) -> None:
        if self.memory is not None:
            await self.memory.maintain_conversation(
                workspace_id=workspace_id,
                actor_id=actor_id,
                conversation_id=conversation_id,
            )

    def _evidence(self, retrieval: RetrievalResponse) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for ordinal, item in enumerate(retrieval.items, start=1):
            page = item.page_start
            label = f"{item.filename}, page {page}"
            evidence.append(
                {
                    "citation_id": f"C{ordinal}",
                    "ordinal": ordinal,
                    "document_id": str(item.document_id),
                    "chunk_id": str(item.chunk_id),
                    "label": label,
                    "page": page,
                    "section": item.section_heading,
                    "quote": item.content[:1000],
                    "source_url": (f"/v1/documents/{item.document_id}/source?page={page}"),
                    "semantic_rank": item.semantic_rank,
                    "sparse_rank": item.sparse_rank,
                    "semantic_score": item.semantic_score,
                    "sparse_score": item.sparse_score,
                    "rrf_score": item.rrf_score,
                }
            )
        return evidence

    def _insufficient(self, retrieval: RetrievalResponse) -> bool:
        if not retrieval.items:
            return True
        top = retrieval.items[0]
        semantic = float(top.semantic_score or 0)
        return semantic < self.config.insufficient_semantic_threshold and top.sparse_rank is None

    async def _transition(  # noqa: PLR0913
        self,
        run_id: UUID,
        workspace_id: UUID,
        status: str,
        node: str,
        *,
        accumulated_text: str | None = None,
        timings: dict[str, float] | None = None,
        error: dict[str, object] | None = None,
    ) -> None:
        await self.admin.rpc(
            "transition_rag_run",
            {
                "p_run_id": str(run_id),
                "p_workspace_id": str(workspace_id),
                "p_status": status,
                "p_current_node": node,
                "p_accumulated_text": accumulated_text,
                "p_answer_status": "failed" if status == "failed" else None,
                "p_confidence": None,
                "p_output_message_id": None,
                "p_timings": timings,
                "p_error": error,
            },
        )

    async def _event(
        self,
        run_id: UUID,
        workspace_id: UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        await self.admin.rpc(
            "append_rag_run_event",
            {
                "p_run_id": str(run_id),
                "p_workspace_id": str(workspace_id),
                "p_event_type": event_type,
                "p_payload": payload,
            },
        )

    async def _fail(  # noqa: PLR0913
        self,
        run_id: UUID,
        workspace_id: UUID,
        *,
        code: str,
        detail: str,
        retryable: bool,
        status: str,
        accumulated: str,
        started: float,
    ) -> None:
        error = {"code": code, "detail": detail, "retryable": retryable}
        await self._transition(
            run_id,
            workspace_id,
            status,
            status,
            accumulated_text=accumulated or None,
            timings={"total_ms": round((perf_counter() - started) * 1000, 3)},
            error=error,
        )
        await self._event(
            run_id,
            workspace_id,
            "run.failed",
            error,
        )


def sse_envelope(event: dict[str, Any], *, run_id: UUID, workspace_id: UUID) -> dict[str, Any]:
    return {
        "event_id": str(event["id"]),
        "event_type": event["event_type"],
        "occurred_at": str(event["occurred_at"]),
        "run_id": str(run_id),
        "workspace_id": str(workspace_id),
        "sequence": event["sequence"],
        "schema_version": "0.1.0",
        **cast(dict[str, Any], event["payload"]),
    }


def heartbeat_event(run_id: UUID, workspace_id: UUID, sequence: int) -> dict[str, Any]:
    return {
        "event_id": str(uuid4()),
        "event_type": "stream.heartbeat",
        "occurred_at": datetime.now(UTC).isoformat(),
        "run_id": str(run_id),
        "workspace_id": str(workspace_id),
        "sequence": sequence,
        "schema_version": "0.1.0",
        "comment": "keep-alive",
    }
