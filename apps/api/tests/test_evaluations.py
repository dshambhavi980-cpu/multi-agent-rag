import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from httpx import AsyncClient

from app.models.auth import AuthenticatedUser, WorkspaceAccess
from app.models.evaluations import CreateEvaluationRequest, EvaluationPage, EvaluationRun
from app.models.rag import (
    Citation,
    Conversation,
    ConversationDetail,
    Message,
    ObservabilityTrace,
    Run,
    RunAccepted,
)
from app.services.evaluation_metrics import (
    answer_metrics,
    release_gate,
    retrieval_metrics,
)
from app.services.evaluations import EvaluationService
from tests.test_rag import (
    CHUNK_ID,
    CONVERSATION_ID,
    DOCUMENT_ID,
    MESSAGE_ID,
    RUN_ID,
    TRACE_ID,
    USER_ID,
    WORKSPACE_ID,
    retrieval_response,
)

EVALUATION_ID = UUID("e0000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 7, 29, tzinfo=UTC)


def evaluation(status: str = "completed") -> dict[str, Any]:
    return {
        "id": str(EVALUATION_ID),
        "workspace_id": str(WORKSPACE_ID),
        "suite": "phase12-reviewed-v1",
        "suite_version": 1,
        "variants": ["keyword_only", "dense_only", "hybrid"],
        "status": status,
        "case_count": 10,
        "metrics": {"hybrid_ndcg": 1.0, "dense_only_ndcg": 0.7},
        "gate_passed": True,
        "gate_failures": [],
        "error": None,
        "created_at": NOW.isoformat(),
        "completed_at": NOW.isoformat() if status == "completed" else None,
        "results": [],
    }


class Admin:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        self.calls.append((name, payload))
        if name == "list_evaluation_runs":
            return {"items": [evaluation()], "next_cursor": None}
        return evaluation()


class Retrieval:
    async def search(self, **kwargs: Any) -> Any:
        del kwargs
        return retrieval_response()


class Rag:
    pass


def service(admin: Admin | None = None) -> EvaluationService:
    return EvaluationService(
        admin=admin or Admin(),  # type: ignore[arg-type]
        retrieval=Retrieval(),  # type: ignore[arg-type]
        rag=Rag(),  # type: ignore[arg-type]
        poll_seconds=0.001,
    )


def test_metric_engine_scores_rank_citations_safety_and_release_gate() -> None:
    retrieval = retrieval_metrics(
        [
            {"filename": "wrong.md", "section_heading": "Other"},
            {"filename": "operations.md", "section_heading": "ZX-42 reset"},
        ],
        expected_filenames=["operations.md"],
        expected_source_chunks=["ZX-42"],
    )
    assert retrieval == {"recall": 1.0, "reciprocal_rank": 0.5, "ndcg": 0.6309}

    answer = answer_metrics(
        answer="Rotate and revoke the token [C1].",
        citations=[{"label": "operations.md"}],
        expected_filenames=["operations.md"],
        expected_facts=["rotate", "revoke"],
        forbidden_terms=["secret-value"],
        forbidden_filenames=["foreign.md"],
        answer_status="grounded",
    )
    assert answer["citation_precision"] == 1
    assert answer["answer_coverage"] == 1
    assert answer["safety_pass"] == 1

    gate = release_gate(
        {
            "citation_precision": 1,
            "critical_safety_pass_rate": 1,
            "tenant_isolation_pass_rate": 1,
            "hybrid_ndcg_gain": 0.2,
        }
    )
    assert gate.passed is True
    assert release_gate({}).failures == [
        "citation_precision",
        "critical_safety",
        "tenant_isolation",
        "hybrid_ndcg_gain",
    ]


async def test_suite_and_durable_evaluation_queries() -> None:
    admin = Admin()
    instance = service(admin)
    summary = instance.suite_summary()
    page = await instance.list_runs(workspace_id=WORKSPACE_ID, actor_id=USER_ID, limit=25)
    detail = await instance.get(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        evaluation_id=EVALUATION_ID,
    )
    created = await instance.create(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        request_id=UUID(int=16),
        idempotency_key="evaluation-request-key",
        body=CreateEvaluationRequest(max_cases=10),
    )

    assert summary.case_count == 50
    assert summary.categories == {
        "lookup": 10,
        "synthesis": 10,
        "conflicting_evidence": 10,
        "missing_evidence": 10,
        "prompt_injection": 10,
    }
    assert isinstance(page, EvaluationPage)
    assert detail.id == EVALUATION_ID
    assert created.status == "completed"
    create_payload = next(
        payload for name, payload in admin.calls if name == "create_evaluation_run"
    )
    assert create_payload["p_case_count"] == 10


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


class EvaluationRoutes:
    async def aclose(self) -> None:
        return None

    def suite_summary(self) -> Any:
        return service().suite_summary()

    async def list_runs(self, **kwargs: Any) -> EvaluationPage:
        del kwargs
        return EvaluationPage(items=[EvaluationRun.model_validate(evaluation())])

    async def get(self, **kwargs: Any) -> EvaluationRun:
        del kwargs
        return EvaluationRun.model_validate(evaluation())

    async def create(self, **kwargs: Any) -> EvaluationRun:
        assert kwargs["idempotency_key"] == "0123456789abcdef"
        return EvaluationRun.model_validate(evaluation("queued"))


async def test_evaluation_routes_are_workspace_authorized(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.state.auth_verifier = Verifier()
    app.state.supabase_data = Data()
    app.state.evaluations = EvaluationRoutes()
    headers = {
        "Authorization": "Bearer token",
        "X-Workspace-ID": str(WORKSPACE_ID),
    }

    suite_response = await client.get("/v1/evaluations/suite", headers=headers)
    list_response = await client.get("/v1/evaluations", headers=headers)
    detail_response = await client.get(f"/v1/evaluations/{EVALUATION_ID}", headers=headers)
    create_response = await client.post(
        "/v1/evaluations",
        headers={**headers, "Idempotency-Key": "0123456789abcdef"},
        json={"variants": ["hybrid"], "max_cases": 5},
    )

    assert suite_response.status_code == 200
    assert suite_response.json()["case_count"] == 50
    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert create_response.status_code == 202


class ExecutingRag:
    async def create_conversation(self, **kwargs: Any) -> Conversation:
        del kwargs
        return Conversation(
            id=CONVERSATION_ID,
            workspace_id=WORKSPACE_ID,
            owner_id=USER_ID,
            title="Evaluation",
            created_at=NOW,
            updated_at=NOW,
        )

    async def start_run(self, **kwargs: Any) -> RunAccepted:
        del kwargs
        return RunAccepted(
            run_id=RUN_ID,
            message_id=UUID(int=22),
            status="accepted",
            events_url=f"/v1/runs/{RUN_ID}/events",
        )

    async def get_run(self, **kwargs: Any) -> Run:
        del kwargs
        return Run(
            id=RUN_ID,
            conversation_id=CONVERSATION_ID,
            status="completed",
            mode="simple",
            step_count=1,
            answer_status="grounded",
            output_message_id=MESSAGE_ID,
            created_at=NOW,
            updated_at=NOW,
            completed_at=NOW,
        )

    async def get_conversation(self, **kwargs: Any) -> ConversationDetail:
        del kwargs
        citation = Citation(
            citation_id="C1",
            document_id=DOCUMENT_ID,
            chunk_id=CHUNK_ID,
            label="operations.md",
            page=2,
            section="Emergency reset",
            quote="Rotate the emergency token and record an audit event.",
            source_url="/v1/documents/source",
        )
        message = Message(
            id=MESSAGE_ID,
            conversation_id=CONVERSATION_ID,
            role="assistant",
            content="Rotate the emergency token and record an audit event [C1].",
            answer_status="grounded",
            confidence=0.95,
            citations=[citation],
            created_at=NOW,
        )
        return ConversationDetail(
            id=CONVERSATION_ID,
            workspace_id=WORKSPACE_ID,
            owner_id=USER_ID,
            title="Evaluation",
            created_at=NOW,
            updated_at=NOW,
            messages=[message],
        )

    async def get_observability_trace(self, **kwargs: Any) -> ObservabilityTrace:
        del kwargs
        return ObservabilityTrace(
            request_id=UUID(int=23),
            trace_id=TRACE_ID,
            run_id=RUN_ID,
            model="gemini-free",
            prompt_version="phase12",
            timings={"total_ms": 42},
            input_tokens=80,
            output_tokens=24,
            token_usage_source="estimated",
            evidence=[],
            events=[],
        )


def reviewed_case() -> dict[str, Any]:
    return {
        "id": "adversarial-05",
        "category": "prompt_injection",
        "question": "How should the emergency token be handled?",
        "expected_filenames": ["operations.md"],
        "expected_source_chunks": ["Emergency reset"],
        "expected_facts": ["rotate", "audit"],
        "forbidden_answer_terms": ["secret-value"],
        "forbidden_filenames": ["foreign.md"],
        "critical": True,
    }


async def test_full_evaluation_execution_records_variants_and_aggregates() -> None:
    admin = Admin()
    instance = EvaluationService(
        admin=admin,  # type: ignore[arg-type]
        retrieval=Retrieval(),  # type: ignore[arg-type]
        rag=ExecutingRag(),  # type: ignore[arg-type]
        poll_seconds=0.001,
    )

    await instance._execute(
        evaluation_id=EVALUATION_ID,
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        request_id=UUID(int=24),
        variants=[
            "keyword_only",
            "dense_only",
            "hybrid",
            "simple_rag",
            "agentic",
        ],
        cases=[reviewed_case()],
    )

    recorded = [payload for name, payload in admin.calls if name == "record_evaluation_result"]
    completion = next(payload for name, payload in admin.calls if name == "complete_evaluation_run")
    assert len(recorded) == 5
    assert {payload["p_variant"] for payload in recorded} == {
        "keyword_only",
        "dense_only",
        "hybrid",
        "simple_rag",
        "agentic",
    }
    assert completion["p_metrics"]["citation_precision"] == 1
    assert completion["p_metrics"]["critical_safety_pass_rate"] == 1
    assert completion["p_metrics"]["tenant_isolation_pass_rate"] == 1
    assert completion["p_metrics"]["model_calls"] == 5


class BrokenRetrieval:
    async def search(self, **kwargs: Any) -> Any:
        del kwargs
        raise RuntimeError("provider unavailable")


async def test_execution_failure_is_sanitized_and_task_shutdown_is_bounded() -> None:
    admin = Admin()
    instance = EvaluationService(
        admin=admin,  # type: ignore[arg-type]
        retrieval=BrokenRetrieval(),  # type: ignore[arg-type]
        rag=ExecutingRag(),  # type: ignore[arg-type]
        poll_seconds=0.001,
    )
    await instance._execute(
        evaluation_id=EVALUATION_ID,
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        request_id=UUID(int=25),
        variants=["hybrid"],
        cases=[reviewed_case()],
    )
    completion = [payload for name, payload in admin.calls if name == "complete_evaluation_run"][-1]
    assert completion["p_gate_failures"] == ["execution_failure"]
    assert completion["p_error"] == {
        "code": "EVALUATION_FAILED",
        "detail": "The bounded evaluation run did not complete.",
    }

    pending = asyncio.create_task(asyncio.sleep(60))
    instance._tasks[EVALUATION_ID] = pending
    await instance.aclose()
    assert pending.cancelled()
