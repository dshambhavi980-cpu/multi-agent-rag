from __future__ import annotations

import hashlib
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from app.api.errors import ApplicationError
from app.models.retrieval import RetrievalFilters, RetrievalRequest, RetrievalResponse
from app.services.retrieval import HybridRetrievalService

from .models import RetrievalToolInput


@dataclass(frozen=True)
class ToolSpec:
    name: str
    permission: str
    description: str


class ToolRegistry:
    def __init__(self, *, admin: Any, retrieval: HybridRetrievalService) -> None:
        self.admin = admin
        self.retrieval = retrieval
        self._specs = {
            "hybrid_document_search": ToolSpec(
                name="hybrid_document_search",
                permission="documents:read",
                description="Search indexed documents in the current workspace.",
            )
        }

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._specs.values())

    async def hybrid_search(  # noqa: PLR0913
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
        request_id: UUID,
        payload: RetrievalToolInput,
        allowed_permissions: frozenset[str],
        candidate_count: int,
    ) -> RetrievalResponse:
        spec = self._specs["hybrid_document_search"]
        if spec.permission not in allowed_permissions:
            raise ApplicationError(
                "AGENT_TOOL_FORBIDDEN",
                "Agent tool forbidden",
                "The current agent node is not permitted to use this tool.",
                status=403,
            )
        call_id = uuid4()
        started = perf_counter()
        sanitized = {
            "query_sha256": hashlib.sha256(payload.query.encode()).hexdigest(),
            "query_length": len(payload.query),
            "document_count": len(payload.document_ids or []),
            "limit": payload.limit,
        }
        try:
            result = await self.retrieval.search(
                workspace_id=workspace_id,
                actor_id=actor_id,
                request_id=request_id,
                request=RetrievalRequest(
                    query=payload.query,
                    mode="hybrid",
                    limit=payload.limit,
                    candidate_count=candidate_count,
                    filters=RetrievalFilters(
                        document_ids=(
                            [UUID(value) for value in payload.document_ids]
                            if payload.document_ids
                            else None
                        )
                    ),
                ),
            )
        except Exception:
            await self._record(
                call_id=call_id,
                run_id=run_id,
                workspace_id=workspace_id,
                input_data=sanitized,
                status="failed",
                output={"error_code": "TOOL_EXECUTION_FAILED"},
                duration_ms=(perf_counter() - started) * 1000,
            )
            raise
        await self._record(
            call_id=call_id,
            run_id=run_id,
            workspace_id=workspace_id,
            input_data=sanitized,
            status="succeeded",
            output={
                "trace_id": str(result.trace_id),
                "selected_chunks": len(result.items),
                "cache_hit": result.cache_hit,
            },
            duration_ms=(perf_counter() - started) * 1000,
        )
        return result

    async def _record(  # noqa: PLR0913
        self,
        *,
        call_id: UUID,
        run_id: UUID,
        workspace_id: UUID,
        input_data: dict[str, object],
        status: str,
        output: dict[str, object],
        duration_ms: float,
    ) -> None:
        await self.admin.rpc(
            "record_agent_tool_call",
            {
                "p_call_id": str(call_id),
                "p_run_id": str(run_id),
                "p_workspace_id": str(workspace_id),
                "p_tool_name": "hybrid_document_search",
                "p_permission": "documents:read",
                "p_status": status,
                "p_sanitized_input": input_data,
                "p_output_summary": output,
                "p_duration_ms": round(duration_ms, 3),
            },
        )
