import argparse
from typing import Any
from uuid import UUID

import pytest
from pydantic import AnyHttpUrl, SecretStr

from app.cli import reindex
from app.core.config import Settings

WORKSPACE_ID = UUID("a0000000-0000-4000-8000-000000000001")
ACTOR_ID = UUID("10000000-0000-4000-8000-000000000001")
DOCUMENT_ID = UUID("40000000-0000-4000-8000-000000000001")


class Admin:
    def __init__(self, **kwargs: Any) -> None:
        del kwargs
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def rpc(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, payload))
        return {"queued": 1}

    async def aclose(self) -> None:
        return None


def settings(*, configured: bool = True) -> Settings:
    return Settings(
        environment="test",
        supabase_url=AnyHttpUrl("https://example.supabase.co") if configured else None,
        supabase_service_role_key=SecretStr("service") if configured else None,
    )


def arguments(*, document_id: UUID | None) -> argparse.Namespace:
    return argparse.Namespace(
        document_id=document_id,
        workspace=document_id is None,
        workspace_id=WORKSPACE_ID,
        actor_id=ACTOR_ID,
        strategy="recursive",
    )


async def test_reindexes_one_document(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[Admin] = []

    def make_admin(**kwargs: Any) -> Admin:
        instance = Admin(**kwargs)
        created.append(instance)
        return instance

    monkeypatch.setattr(reindex, "get_settings", settings)
    monkeypatch.setattr(reindex, "SupabaseAdminClient", make_admin)

    result = await reindex._run(arguments(document_id=DOCUMENT_ID))

    assert result == {"queued": 1}
    name, payload = created[0].calls[0]
    assert name == "enqueue_document_reindex"
    assert payload["p_document_id"] == str(DOCUMENT_ID)
    assert payload["p_strategy"] == "recursive"


async def test_reindexes_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[Admin] = []

    def make_admin(**kwargs: Any) -> Admin:
        instance = Admin(**kwargs)
        created.append(instance)
        return instance

    monkeypatch.setattr(reindex, "get_settings", settings)
    monkeypatch.setattr(reindex, "SupabaseAdminClient", make_admin)

    await reindex._run(arguments(document_id=None))

    assert created[0].calls[0][0] == "enqueue_workspace_reindex"


async def test_reindex_requires_server_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reindex, "get_settings", lambda: settings(configured=False))

    with pytest.raises(SystemExit, match="APP_SUPABASE_URL"):
        await reindex._run(arguments(document_id=DOCUMENT_ID))


def test_parser_requires_exactly_one_target() -> None:
    parser = reindex._parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--workspace-id",
                str(WORKSPACE_ID),
                "--actor-id",
                str(ACTOR_ID),
            ]
        )
