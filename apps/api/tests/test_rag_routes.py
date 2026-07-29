from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from httpx import AsyncClient

from app.models.auth import AuthenticatedUser, WorkspaceAccess
from app.models.rag import (
    AgentStep,
    Conversation,
    ConversationDetail,
    ConversationPage,
    Message,
    OperationAccepted,
    Run,
    RunAccepted,
    RunPage,
    RunSummary,
    RunTrace,
    ToolCall,
    WorkspaceUsage,
)

USER_ID = UUID("10000000-0000-4000-8000-000000000001")
WORKSPACE_ID = UUID("a0000000-0000-4000-8000-000000000001")
CONVERSATION_ID = UUID("90000000-0000-4000-8000-000000000001")
RUN_ID = UUID("70000000-0000-4000-8000-000000000001")
MESSAGE_ID = UUID("80000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 7, 28, tzinfo=UTC)


class Verifier:
    async def aclose(self) -> None:
        return None

    async def verify(self, token: str) -> AuthenticatedUser:
        assert token == "token"
        return AuthenticatedUser(id=USER_ID, email="u@example.test", role="authenticated")


class Data:
    async def aclose(self) -> None:
        return None

    async def get_workspace_access(self, **kwargs: Any) -> WorkspaceAccess:
        del kwargs
        return WorkspaceAccess(workspace_id=WORKSPACE_ID, user_id=USER_ID, role="member")


def conversation() -> Conversation:
    return Conversation(
        id=CONVERSATION_ID,
        workspace_id=WORKSPACE_ID,
        owner_id=USER_ID,
        title="Emergency access",
        created_at=NOW,
        updated_at=NOW,
    )


def run(status: str = "completed") -> Run:
    return Run.model_validate(
        {
            "id": RUN_ID,
            "conversation_id": CONVERSATION_ID,
            "status": status,
            "mode": "simple",
            "current_node": "complete",
            "step_count": 3,
            "confidence": 0.9,
            "answer_status": "grounded",
            "output_message_id": MESSAGE_ID,
            "error": None,
            "created_at": NOW,
            "updated_at": NOW,
            "completed_at": NOW if status == "completed" else None,
        }
    )


class Rag:
    def __init__(self) -> None:
        self.config = type("Config", (), {"event_poll_seconds": 0.001, "heartbeat_seconds": 5})()

    async def aclose(self) -> None:
        return None

    async def create_conversation(self, **kwargs: Any) -> Conversation:
        assert kwargs["idempotency_key"] == "0123456789abcdef"
        return conversation()

    async def list_conversations(self, **kwargs: Any) -> ConversationPage:
        del kwargs
        return ConversationPage(items=[conversation()])

    async def get_conversation(self, **kwargs: Any) -> ConversationDetail:
        del kwargs
        return ConversationDetail(
            **conversation().model_dump(),
            messages=[
                Message(
                    id=MESSAGE_ID,
                    conversation_id=CONVERSATION_ID,
                    role="user",
                    content="Question",
                    created_at=NOW,
                )
            ],
        )

    async def start_run(self, **kwargs: Any) -> RunAccepted:
        del kwargs
        return RunAccepted(
            run_id=RUN_ID,
            message_id=MESSAGE_ID,
            status="accepted",
            events_url=f"/v1/runs/{RUN_ID}/events",
        )

    async def get_run(self, **kwargs: Any) -> Run:
        del kwargs
        return run()

    async def list_runs(self, **kwargs: Any) -> RunPage:
        del kwargs
        return RunPage(items=[RunSummary(**run().model_dump(), question="Question")])

    async def get_run_trace(self, **kwargs: Any) -> RunTrace:
        del kwargs
        return RunTrace(
            run=RunSummary(**run().model_dump(), question="Question"),
            steps=[
                AgentStep(
                    id=UUID(int=21),
                    step_number=1,
                    node="retrieve",
                    status="succeeded",
                    summary="Retrieved workspace evidence.",
                    duration_ms=12,
                    created_at=NOW,
                )
            ],
            tool_calls=[
                ToolCall(
                    id=UUID(int=22),
                    tool_name="workspace_search",
                    permission="read",
                    status="succeeded",
                    output_summary={"results": 3},
                    duration_ms=8,
                    created_at=NOW,
                )
            ],
        )

    async def workspace_usage(self, **kwargs: Any) -> WorkspaceUsage:
        del kwargs
        return WorkspaceUsage(
            documents=2,
            document_bytes=2048,
            ready_documents=1,
            conversations=1,
            runs=1,
            approvals=0,
            memories=3,
        )

    async def cancel(self, **kwargs: Any) -> Run:
        del kwargs
        return run("cancelling")

    async def resume(self, **kwargs: Any) -> Run:
        del kwargs
        return run("running")

    async def events(self, **kwargs: Any) -> list[dict[str, Any]]:
        if kwargs["after_sequence"] > 0:
            return []
        return [
            {
                "id": UUID(int=12),
                "sequence": 1,
                "event_type": "run.completed",
                "occurred_at": NOW,
                "payload": {
                    "message_id": str(MESSAGE_ID),
                    "answer_status": "grounded",
                    "confidence": 0.9,
                    "duration_ms": 100,
                },
            }
        ]


def headers(*, idempotent: bool = False) -> dict[str, str]:
    result = {
        "Authorization": "Bearer token",
        "X-Workspace-ID": str(WORKSPACE_ID),
    }
    if idempotent:
        result["Idempotency-Key"] = "0123456789abcdef"
    return result


async def test_conversation_and_run_routes(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.state.auth_verifier = Verifier()
    app.state.supabase_data = Data()
    app.state.rag = Rag()

    created = await client.post(
        "/v1/conversations",
        headers=headers(idempotent=True),
        json={"title": "Emergency access"},
    )
    assert created.status_code == 201
    assert created.json()["id"] == str(CONVERSATION_ID)

    listed = await client.get("/v1/conversations", headers=headers())
    detail = await client.get(f"/v1/conversations/{CONVERSATION_ID}", headers=headers())
    accepted = await client.post(
        f"/v1/conversations/{CONVERSATION_ID}/messages",
        headers=headers(idempotent=True),
        json={"content": "Question", "force_mode": "simple"},
    )
    snapshot = await client.get(f"/v1/runs/{RUN_ID}", headers=headers())
    run_page = await client.get("/v1/runs?limit=10", headers=headers())
    trace = await client.get(f"/v1/runs/{RUN_ID}/trace", headers=headers())
    usage = await client.get("/v1/workspace/usage", headers=headers())
    cancelled = await client.post(f"/v1/runs/{RUN_ID}/cancel", headers=headers(idempotent=True))
    resumed = await client.post(f"/v1/runs/{RUN_ID}/resume", headers=headers(idempotent=True))

    assert listed.json()["items"][0]["id"] == str(CONVERSATION_ID)
    assert detail.json()["messages"][0]["content"] == "Question"
    assert accepted.status_code == 202
    assert snapshot.json()["status"] == "completed"
    assert run_page.json()["items"][0]["question"] == "Question"
    assert trace.json()["steps"][0]["summary"] == "Retrieved workspace evidence."
    assert trace.json()["tool_calls"][0]["output_summary"] == {"results": 3}
    assert usage.json()["document_bytes"] == 2048
    assert cancelled.json() == OperationAccepted(id=RUN_ID, status="cancelling").model_dump(
        mode="json"
    )
    assert resumed.json() == OperationAccepted(id=RUN_ID, status="running").model_dump(mode="json")


async def test_sse_replays_durable_events_and_requires_idempotency(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.state.auth_verifier = Verifier()
    app.state.supabase_data = Data()
    app.state.rag = Rag()

    response = await client.get(
        f"/v1/runs/{RUN_ID}/events",
        headers={**headers(), "Last-Event-ID": "not-a-sequence"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: run.completed" in response.text
    assert '"sequence":1' in response.text

    missing_key = await client.post("/v1/conversations", headers=headers(), json={})
    assert missing_key.status_code == 422
