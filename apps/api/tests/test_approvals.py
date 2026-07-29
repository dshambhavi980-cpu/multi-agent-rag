from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from httpx import AsyncClient

from app.agents.models import AgentResult, AgentState
from app.models.approvals import Approval, ApprovalPage
from app.models.auth import AuthenticatedUser, WorkspaceAccess
from app.services.approvals import ApprovalConfig, ApprovalService

USER_ID = UUID("10000000-0000-4000-8000-000000000001")
WORKSPACE_ID = UUID("a0000000-0000-4000-8000-000000000001")
RUN_ID = UUID("70000000-0000-4000-8000-000000000001")
APPROVAL_ID = UUID("60000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 7, 29, tzinfo=UTC)


def approval_item(**updates: Any) -> dict[str, Any]:
    item = {
        "id": str(APPROVAL_ID),
        "run_id": str(RUN_ID),
        "status": "pending",
        "risk_level": "medium",
        "reasons": ["Confidence is below threshold."],
        "proposed_output": "A proposed cited answer. [C1]",
        "reviewer_id": None,
        "reviewer_comment": None,
        "decided_at": None,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    item.update(updates)
    return item


class Admin:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        self.calls.append((name, payload))
        if name == "list_approval_requests":
            return {"items": [approval_item()], "next_cursor": None}
        if name == "decide_approval_request":
            return {
                "approval": approval_item(
                    status="revision_requested",
                    reviewer_id=str(USER_ID),
                    reviewer_comment="Add the exception.",
                    decided_at=NOW.isoformat(),
                ),
                "run_id": str(RUN_ID),
                "resume_required": True,
            }
        return approval_item()


def state(question: str = "Compare the production deployment policies.") -> AgentState:
    return {
        "run_id": str(RUN_ID),
        "workspace_id": str(WORKSPACE_ID),
        "actor_id": str(USER_ID),
        "request_id": str(UUID(int=2)),
        "question": question,
        "document_ids": None,
        "step_count": 6,
        "started_at": 0,
        "resume_node": "complete",
        "route_reason": "complex",
    }


async def test_policy_pauses_sensitive_or_low_confidence_runs() -> None:
    admin = Admin()
    service = ApprovalService(
        admin=admin,  # type: ignore[arg-type]
        config=ApprovalConfig(confidence_threshold=0.8, citation_coverage_threshold=0.75),
    )
    result = AgentResult(
        content="A proposed cited answer. [C1]",
        answer_status="grounded",
        confidence=0.6,
        evidence=[{"citation_id": "C1"}, {"citation_id": "C2"}],
        citation_ids=["C1"],
        retrieval_trace_ids=[],
        step_count=6,
    )

    approval = await service.maybe_pause(state=state(), result=result, citations=[])

    assert approval is not None
    payload = admin.calls[0][1]
    assert payload["p_risk_level"] == "high"
    assert len(payload["p_reasons"]) == 3
    assert payload["p_creation_key"].endswith(":6:complete")


async def test_policy_allows_grounded_low_risk_output_and_decisions_resume() -> None:
    admin = Admin()
    service = ApprovalService(
        admin=admin,  # type: ignore[arg-type]
        config=ApprovalConfig(confidence_threshold=0.5, citation_coverage_threshold=0.5),
    )
    result = AgentResult(
        content="Answer [C1]",
        answer_status="grounded",
        confidence=0.9,
        evidence=[{"citation_id": "C1"}],
        citation_ids=["C1"],
        retrieval_trace_ids=[],
        step_count=6,
    )

    assert (
        await service.maybe_pause(
            state=state("Compare two internal policies."),
            result=result,
            citations=[],
        )
        is None
    )
    page = await service.list(
        workspace_id=WORKSPACE_ID, actor_id=USER_ID, status="pending", limit=25
    )
    item = await service.get(workspace_id=WORKSPACE_ID, actor_id=USER_ID, approval_id=APPROVAL_ID)
    decided, run_id, resume = await service.decide(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        approval_id=APPROVAL_ID,
        idempotency_key="0123456789abcdef",
        action="revise",
        comment="Add the exception.",
    )

    assert page.items[0].id == APPROVAL_ID
    assert item.status == "pending"
    assert decided.status == "revision_requested"
    assert run_id == RUN_ID
    assert resume is True


class Verifier:
    async def aclose(self) -> None:
        return None

    async def verify(self, token: str) -> AuthenticatedUser:
        assert token == "token"
        return AuthenticatedUser(id=USER_ID, email=None, role="authenticated")


class Data:
    async def aclose(self) -> None:
        return None

    async def get_workspace_access(self, **kwargs: Any) -> WorkspaceAccess:
        del kwargs
        return WorkspaceAccess(workspace_id=WORKSPACE_ID, user_id=USER_ID, role="owner")


class ApprovalRoutes:
    async def list(self, **kwargs: Any) -> ApprovalPage:
        assert kwargs["status"] == "pending"
        return ApprovalPage(items=[Approval.model_validate(approval_item())])

    async def get(self, **kwargs: Any) -> Approval:
        del kwargs
        return Approval.model_validate(approval_item())

    async def decide(self, **kwargs: Any) -> tuple[Approval, UUID, bool]:
        assert len(kwargs["idempotency_key"]) >= 16
        return (
            Approval.model_validate(
                approval_item(
                    status="revision_requested",
                    reviewer_id=str(USER_ID),
                    reviewer_comment=kwargs["comment"],
                    decided_at=NOW.isoformat(),
                )
            ),
            RUN_ID,
            kwargs["action"] == "revise",
        )


class Rag:
    def __init__(self) -> None:
        self.resumed = False

    async def resume_from_review(self, **kwargs: Any) -> None:
        assert kwargs == {"run_id": RUN_ID, "workspace_id": WORKSPACE_ID}
        self.resumed = True

    async def aclose(self) -> None:
        return None


async def test_approval_routes_list_get_and_resume_revision(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.state.auth_verifier = Verifier()
    app.state.supabase_data = Data()
    app.state.approvals = ApprovalRoutes()
    rag = Rag()
    app.state.rag = rag
    headers = {
        "Authorization": "Bearer token",
        "X-Workspace-ID": str(WORKSPACE_ID),
    }

    listed = await client.get("/v1/approvals?status=pending", headers=headers)
    detail = await client.get(f"/v1/approvals/{APPROVAL_ID}", headers=headers)
    revised = await client.post(
        f"/v1/approvals/{APPROVAL_ID}/revise",
        headers={**headers, "Idempotency-Key": "0123456789abcdef"},
        json={"comment": "Add the exception."},
    )
    approved = await client.post(
        f"/v1/approvals/{APPROVAL_ID}/approve",
        headers={**headers, "Idempotency-Key": "fedcba9876543210"},
        json={"comment": "Verified.", "edited_output": "Reviewed output."},
    )
    rejected = await client.post(
        f"/v1/approvals/{APPROVAL_ID}/reject",
        headers={**headers, "Idempotency-Key": "aaaabbbbccccdddd"},
        json={"comment": "Unsafe."},
    )

    assert listed.status_code == 200
    assert detail.json()["id"] == str(APPROVAL_ID)
    assert revised.json()["status"] == "revision_requested"
    assert approved.status_code == 200
    assert rejected.status_code == 200
    assert rag.resumed is True
