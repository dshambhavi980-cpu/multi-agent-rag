from typing import Any
from uuid import UUID

from app.core.logging import redact_sensitive_data
from app.models.rag import ReplayRunRequest
from tests.test_rag import (
    CONVERSATION_ID,
    MESSAGE_ID,
    RUN_ID,
    USER_ID,
    WORKSPACE_ID,
    Generation,
    retrieval_response,
    service,
)
from tests.test_rag import Admin as RagAdmin


def test_structured_log_redaction_removes_credentials_and_content() -> None:
    event = redact_sensitive_data(
        None,
        "info",
        {
            "authorization": "Bearer secret",
            "nested": {"api_key": "AQ.secret", "safe": "ok"},
            "items": ["safe", "https://example.test/file?signature=secret"],
            "message": "Bearer abc eyJheader.payload.signature",
            "content": "sensitive document",
        },
    )

    assert event["authorization"] == "[REDACTED]"
    assert event["nested"] == {"api_key": "[REDACTED]", "safe": "ok"}
    assert event["content"] == "[REDACTED]"
    assert event["items"][1].endswith("signature=[REDACTED]")
    assert "secret" not in str(event)
    assert "eyJheader" not in str(event)


async def test_replay_uses_snapshot_and_never_inherits_approval() -> None:
    class Admin(RagAdmin):
        async def rpc(self, name: str, payload: dict[str, Any]) -> Any:
            self.calls.append((name, payload))
            if name == "get_rag_replay_snapshot":
                return {
                    "conversation_id": str(CONVERSATION_ID),
                    "question": "Compare the access policies",
                    "document_ids": None,
                    "mode": "agentic",
                    "model": "gemini-test",
                    "prompt_version": "rag-system-v1+answer-v1+memory-v1",
                }
            if name == "start_rag_run":
                return {
                    "run_id": str(RUN_ID),
                    "message_id": str(MESSAGE_ID),
                    "status": "completed",
                    "events_url": f"/v1/runs/{RUN_ID}/events",
                }
            return None

    admin = Admin()
    instance = service(admin, retrieval_response(), Generation())
    accepted = await instance.replay_run(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        source_run_id=UUID(int=99),
        request_id=UUID(int=16),
        idempotency_key="phase11-replay-key",
        body=ReplayRunRequest(mode="current_configuration", reason="Diagnose regression"),
    )

    assert accepted.run_id == RUN_ID
    names = [name for name, _ in admin.calls]
    assert names == [
        "get_rag_replay_snapshot",
        "start_rag_run",
        "attach_rag_run_correlation",
        "mark_rag_run_replay",
    ]
    replay_metadata = admin.calls[-1][1]
    assert replay_metadata["p_source_run_id"] == str(UUID(int=99))
    assert "approval" not in str(replay_metadata).lower()


async def test_observability_models_and_estimated_telemetry_are_recorded() -> None:
    class Admin(RagAdmin):
        async def rpc(self, name: str, payload: dict[str, Any]) -> Any:
            self.calls.append((name, payload))
            if name == "get_run_observability_trace":
                return {
                    "request_id": str(UUID(int=16)),
                    "trace_id": str(UUID(int=17)),
                    "run_id": str(RUN_ID),
                    "model": "gemini-test",
                    "prompt_version": "prompt-v1",
                    "timings": {"total_ms": 42.5},
                    "input_tokens": 4,
                    "output_tokens": 3,
                    "token_usage_source": "estimated",
                    "replayed_from_run_id": None,
                    "replay_mode": None,
                    "error": None,
                    "evidence": [],
                    "events": [],
                }
            if name == "get_workspace_observability":
                return {
                    "window_hours": 24,
                    "total_runs": 2,
                    "successful_runs": 2,
                    "failed_runs": 0,
                    "success_rate": 1,
                    "p95_latency_ms": 42.5,
                    "input_tokens": 8,
                    "output_tokens": 6,
                    "active_runs": 0,
                    "trace_count": 2,
                    "trace_limit": 50,
                    "retention_days": 30,
                }
            return None

    admin = Admin()
    instance = service(admin, retrieval_response(), Generation())
    trace = await instance.get_observability_trace(
        workspace_id=WORKSPACE_ID, actor_id=USER_ID, run_id=RUN_ID
    )
    summary = await instance.observability_summary(workspace_id=WORKSPACE_ID, actor_id=USER_ID)
    await instance._record_telemetry(
        run_id=RUN_ID,
        workspace_id=WORKSPACE_ID,
        question="four token input",
        answer="short answer",
        timings={"total_ms": 42.5},
    )

    assert trace.trace_id == UUID(int=17)
    assert summary.success_rate == 1
    telemetry = admin.calls[-1][1]
    assert telemetry["p_input_tokens"] == 4
    assert telemetry["p_output_tokens"] == 3
    assert telemetry["p_token_usage_source"] == "estimated"
