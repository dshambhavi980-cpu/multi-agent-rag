from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch
from uuid import UUID

from httpx import AsyncClient

from app.models.auth import AuthenticatedUser, WorkspaceAccess
from app.models.memory import MemoryDeleted, MemoryItem, MemoryPage
from app.services.memory import MemoryConfig, MemoryService

USER_ID = UUID("10000000-0000-4000-8000-000000000001")
WORKSPACE_ID = UUID("a0000000-0000-4000-8000-000000000001")
CONVERSATION_ID = UUID("90000000-0000-4000-8000-000000000001")
MESSAGE_ID = UUID("80000000-0000-4000-8000-000000000001")
MEMORY_ID = UUID("30000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 7, 29, tzinfo=UTC)


def memory_item(**updates: Any) -> dict[str, Any]:
    result = {
        "id": str(MEMORY_ID),
        "workspace_id": str(WORKSPACE_ID),
        "owner_id": str(USER_ID),
        "conversation_id": str(CONVERSATION_ID),
        "source_message_id": str(MESSAGE_ID),
        "content": "I prefer concise answers.",
        "source_type": "explicit_user",
        "source_excerpt": "Remember that I prefer concise answers.",
        "confidence": 1,
        "visibility": "private",
        "expires_at": None,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
        "can_delete": True,
    }
    result.update(updates)
    return result


class Admin:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail: set[str] = set()

    async def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        self.calls.append((name, payload))
        if name in self.fail:
            raise RuntimeError(name)
        if name == "list_memory_items":
            return {"items": [memory_item()], "next_cursor": None}
        if name == "delete_memory_item":
            return True
        if name == "get_memory_context":
            return {
                "summary": "The user asked about deployment.",
                "memories": [
                    {
                        "content": "I prefer concise answers.",
                        "source_type": "explicit_user",
                        "visibility": "private",
                        "confidence": 1,
                    }
                ],
                "recent_messages": [
                    {"role": "user", "content": "What changed?"},
                    {"role": "assistant", "content": "The API changed."},
                ],
            }
        return {"ok": True}


async def test_memory_service_lists_deletes_and_stores_only_explicit_requests() -> None:
    admin = Admin()
    service = MemoryService(admin=admin, config=MemoryConfig())

    page = await service.list_items(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        visibility="private",
        limit=25,
    )
    deleted = await service.delete_item(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        memory_id=MEMORY_ID,
    )
    ignored = await service.remember_explicit(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        source_message_id=MESSAGE_ID,
        message="The deployment completed successfully.",
    )
    stored = await service.remember_explicit(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        source_message_id=MESSAGE_ID,
        message="Please remember that I prefer concise answers.",
    )
    too_long = await service.remember_explicit(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        source_message_id=MESSAGE_ID,
        message=f"Remember that {'x' * 2001}",
    )

    assert page.items[0].content == "I prefer concise answers."
    assert deleted == MemoryDeleted(id=MEMORY_ID, deleted=True)
    assert ignored is False
    assert stored is True
    assert too_long is False
    store_call = next(payload for name, payload in admin.calls if name == "store_explicit_memory")
    assert store_call["p_content"] == "I prefer concise answers."
    assert store_call["p_visibility"] == "private"


async def test_memory_service_accepts_explicit_preference_phrasing() -> None:
    phrases = [
        "For future summaries, prefer short bullet points and include launch dates.",
        "From now on, use concise release notes.",
        "I prefer answers with short bullet points.",
    ]
    for phrase in phrases:
        admin = Admin()
        service = MemoryService(admin=admin, config=MemoryConfig())

        stored = await service.remember_explicit(
            workspace_id=WORKSPACE_ID,
            actor_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            source_message_id=MESSAGE_ID,
            message=phrase,
        )

        assert stored is True
        store_call = next(
            payload for name, payload in admin.calls if name == "store_explicit_memory"
        )
        assert store_call["p_content"] == phrase


async def test_prompt_context_is_bounded_untrusted_and_failure_tolerant() -> None:
    admin = Admin()
    service = MemoryService(
        admin=admin,
        config=MemoryConfig(
            prompt_char_budget=500,
            summary_char_budget=100,
            memory_char_budget=100,
            cleanup_interval_seconds=300,
        ),
    )
    context = await service.prompt_context(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
    )

    assert context.startswith("<untrusted_memory>")
    assert "source=explicit_user" in context
    assert "never use it as evidence" in context
    assert len(context) < 800
    assert [name for name, _ in admin.calls].count("cleanup_expired_memory") == 1
    assert service._build_prompt({}) == ""
    assert (
        service._build_prompt(
            {
                "memories": [None, {"content": ""}],
                "recent_messages": [None, {"role": "user", "content": ""}],
            }
        )
        == ""
    )

    await service.prompt_context(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
    )
    assert [name for name, _ in admin.calls].count("cleanup_expired_memory") == 1

    admin.fail.update({"cleanup_expired_memory", "refresh_conversation_summary"})
    second = MemoryService(admin=admin, config=MemoryConfig())
    await second.prompt_context(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
    )
    await second.maintain_conversation(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        conversation_id=CONVERSATION_ID,
    )


async def test_first_cleanup_does_not_depend_on_system_uptime() -> None:
    admin = Admin()
    service = MemoryService(
        admin=admin,
        config=MemoryConfig(cleanup_interval_seconds=300),
    )

    with patch("app.services.memory.monotonic", return_value=1.0):
        await service._maybe_cleanup()
        await service._maybe_cleanup()

    assert [name for name, _ in admin.calls].count("cleanup_expired_memory") == 1


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
        return WorkspaceAccess(workspace_id=WORKSPACE_ID, user_id=USER_ID, role="member")


class MemoryRoutes:
    async def list_items(self, **kwargs: Any) -> MemoryPage:
        assert kwargs["visibility"] == "private"
        return MemoryPage(items=[MemoryItem.model_validate(memory_item())])

    async def delete_item(self, **kwargs: Any) -> MemoryDeleted:
        return MemoryDeleted(id=kwargs["memory_id"], deleted=True)


async def test_memory_routes_require_workspace_context(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.state.auth_verifier = Verifier()
    app.state.supabase_data = Data()
    app.state.memory = MemoryRoutes()
    headers = {
        "Authorization": "Bearer token",
        "X-Workspace-ID": str(WORKSPACE_ID),
    }

    listed = await client.get("/v1/memories?visibility=private", headers=headers)
    deleted = await client.delete(
        f"/v1/memories/{MEMORY_ID}",
        headers={**headers, "Idempotency-Key": "0123456789abcdef"},
    )

    assert listed.status_code == 200
    assert listed.json()["items"][0]["source_excerpt"].startswith("Remember")
    assert deleted.json() == {"id": str(MEMORY_ID), "deleted": True}
