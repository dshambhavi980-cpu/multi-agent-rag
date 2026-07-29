import re
from dataclasses import dataclass
from typing import Any, Literal, cast
from uuid import UUID

from app.agents.models import AgentResult, AgentState
from app.infrastructure.supabase.admin import SupabaseAdminClient
from app.models.approvals import Approval, ApprovalPage

ApprovalAction = Literal["approve", "reject", "revise"]
SENSITIVE_REQUEST = re.compile(
    r"\b(delete|deploy|payment|credential|secret|send|publish|production|financial|legal)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ApprovalConfig:
    confidence_threshold: float = 0.72
    citation_coverage_threshold: float = 0.5
    expires_hours: int = 24


class ApprovalService:
    def __init__(self, *, admin: SupabaseAdminClient, config: ApprovalConfig) -> None:
        self.admin = admin
        self.config = config

    async def maybe_pause(
        self,
        *,
        state: AgentState,
        result: AgentResult,
        citations: list[dict[str, Any]],
    ) -> Approval | None:
        reasons: list[str] = []
        risk_level: Literal["low", "medium", "high", "critical"] = "low"
        if (
            result.answer_status == "grounded"
            and result.confidence < self.config.confidence_threshold
        ):
            reasons.append(
                f"Confidence {result.confidence:.2f} is below "
                f"{self.config.confidence_threshold:.2f}."
            )
            risk_level = "medium"
        coverage = len(result.citation_ids) / max(len(result.evidence), 1)
        if (
            result.answer_status == "grounded"
            and coverage < self.config.citation_coverage_threshold
        ):
            reasons.append(
                f"Citation coverage {coverage:.2f} is below "
                f"{self.config.citation_coverage_threshold:.2f}."
            )
            risk_level = "medium"
        if SENSITIVE_REQUEST.search(state["question"]):
            reasons.append("The request contains a sensitive or external-action intent.")
            risk_level = "high"
        if not reasons:
            return None
        value = await self.admin.rpc(
            "create_approval_request",
            {
                "p_run_id": state["run_id"],
                "p_workspace_id": state["workspace_id"],
                "p_actor_id": state["actor_id"],
                "p_creation_key": (
                    f"{state['run_id']}:{state['step_count']}:{state['resume_node']}"
                ),
                "p_risk_level": risk_level,
                "p_reasons": reasons,
                "p_proposed_output": result.content,
                "p_answer_status": result.answer_status,
                "p_confidence": result.confidence,
                "p_citations": citations,
                "p_model": "agent",
                "p_prompt_version": "agent-system-v1+memory-v1",
                "p_expires_hours": self.config.expires_hours,
            },
        )
        return Approval.model_validate(value)

    async def list(
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        status: str | None,
        limit: int,
    ) -> ApprovalPage:
        return ApprovalPage.model_validate(
            await self.admin.rpc(
                "list_approval_requests",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_status": status,
                    "p_limit": limit,
                },
            )
        )

    async def get(
        self, *, workspace_id: UUID, actor_id: UUID, approval_id: UUID
    ) -> Approval:
        return Approval.model_validate(
            await self.admin.rpc(
                "get_approval_request",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_approval_id": str(approval_id),
                },
            )
        )

    async def decide(  # noqa: PLR0913
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        approval_id: UUID,
        idempotency_key: str,
        action: ApprovalAction,
        comment: str,
        edited_output: str | None = None,
    ) -> tuple[Approval, UUID, bool]:
        value = cast(
            dict[str, Any],
            await self.admin.rpc(
                "decide_approval_request",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_approval_id": str(approval_id),
                    "p_decision_key": idempotency_key,
                    "p_action": action,
                    "p_comment": comment,
                    "p_edited_output": edited_output,
                },
            ),
        )
        return (
            Approval.model_validate(value["approval"]),
            UUID(value["run_id"]),
            bool(value.get("resume_required")),
        )
