import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient

from app.api.errors import ApplicationError
from app.models.auth import AuthenticatedUser, WorkspaceAccess
from app.models.retrieval import RetrievalFilters, RetrievalRequest
from app.services.retrieval import HybridRetrievalService, RetrievalConfig

USER_ID = UUID("10000000-0000-4000-8000-000000000001")
WORKSPACE_ID = UUID("a0000000-0000-4000-8000-000000000001")
DOCUMENT_ID = UUID("40000000-0000-4000-8000-000000000001")
CHUNK_ID = UUID("50000000-0000-4000-8000-000000000001")
TRACE_ID = UUID("60000000-0000-4000-8000-000000000001")


def search_result(*, cache_hit: bool = False) -> dict[str, Any]:
    return {
        "trace_id": str(TRACE_ID),
        "cache_hit": cache_hit,
        "index_fingerprint": "a" * 32,
        "dense_candidate_count": 2,
        "sparse_candidate_count": 1,
        "items": [
            {
                "chunk_id": str(CHUNK_ID),
                "document_id": str(DOCUMENT_ID),
                "chunk_index": 0,
                "content": "Reset the access token from settings.",
                "page_start": 1,
                "page_end": 1,
                "section_heading": "Authentication",
                "char_start": 10,
                "char_end": 47,
                "token_count": 7,
                "filename": "guide.md",
                "title": "Guide",
                "content_type": "text/markdown",
                "tags": ["auth"],
                "document_created_at": "2026-07-28T00:00:00Z",
                "semantic_rank": 2,
                "sparse_rank": 1,
                "semantic_score": 0.8,
                "sparse_score": 0.7,
                "rrf_score": 0.0325,
                "final_rank": 1,
            }
        ],
    }


class Admin:
    def __init__(
        self,
        *,
        cached: str | None = None,
        timing_failure: bool = False,
    ) -> None:
        self.cached = cached
        self.timing_failure = timing_failure
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        self.calls.append((name, payload))
        if name == "get_query_embedding_cache":
            return self.cached
        if name == "hybrid_search":
            return search_result(cache_hit=self.cached is not None)
        if name == "update_retrieval_trace_timings" and self.timing_failure:
            raise ApplicationError("TRACE_ERROR", "Trace failed", "trace", status=503)
        return True


class Embeddings:
    model = "gemini-embedding-001"
    dimensions = 768

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[1.0, *([0.0] * 767)]]


def service(
    admin: Admin,
    embeddings: Embeddings | None = None,
) -> HybridRetrievalService:
    return HybridRetrievalService(
        admin=admin,  # type: ignore[arg-type]
        embeddings=embeddings or Embeddings(),
        config=RetrievalConfig(),
    )


async def test_search_embeds_caches_filters_and_records_timing() -> None:
    admin = Admin()
    embeddings = Embeddings()
    request = RetrievalRequest(
        query="  Reset   ACCESS token ",
        filters=RetrievalFilters(
            document_ids=[DOCUMENT_ID],
            tags=[" auth ", "auth"],
            created_after=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )

    response = await service(admin, embeddings).search(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        request_id=UUID(int=9),
        request=request,
    )

    assert response.items[0].chunk_id == CHUNK_ID
    assert response.embedding_cache_hit is False
    assert embeddings.calls == [["Reset ACCESS token"]]
    names = [name for name, _ in admin.calls]
    assert names == [
        "get_query_embedding_cache",
        "put_query_embedding_cache",
        "hybrid_search",
        "update_retrieval_trace_timings",
    ]
    hybrid_payload = admin.calls[2][1]
    assert hybrid_payload["p_tags"] == ["auth"]
    assert hybrid_payload["p_document_ids"] == [str(DOCUMENT_ID)]
    assert hybrid_payload["p_query_text"] == "Reset ACCESS token"
    assert len(hybrid_payload["p_query_hash"]) == 64
    assert len(hybrid_payload["p_request_hash"]) == 64


async def test_search_uses_cached_embedding_and_timing_failure_is_nonfatal() -> None:
    cached = json.dumps([1.0, *([0.0] * 767)])
    admin = Admin(cached=cached, timing_failure=True)
    embeddings = Embeddings()

    response = await service(admin, embeddings).search(
        workspace_id=WORKSPACE_ID,
        actor_id=USER_ID,
        request_id=UUID(int=9),
        request=RetrievalRequest(query="cached"),
    )

    assert response.embedding_cache_hit is True
    assert response.cache_hit is True
    assert embeddings.calls == []
    assert "put_query_embedding_cache" not in [name for name, _ in admin.calls]


async def test_search_rejects_invalid_cached_embedding() -> None:
    with pytest.raises(ApplicationError) as exc_info:
        await service(Admin(cached="not-json")).search(
            workspace_id=WORKSPACE_ID,
            actor_id=USER_ID,
            request_id=UUID(int=9),
            request=RetrievalRequest(query="cached"),
        )
    assert exc_info.value.code == "QUERY_CACHE_INVALID"


def test_request_validates_range_candidate_count_and_tags() -> None:
    with pytest.raises(ValueError, match="candidate_count"):
        RetrievalRequest(query="hello", limit=10, candidate_count=5)
    with pytest.raises(ValueError, match="created_after"):
        RetrievalFilters(
            created_after=datetime.now(UTC),
            created_before=datetime.now(UTC) - timedelta(days=1),
        )
    with pytest.raises(ValueError, match="Tags"):
        RetrievalFilters(tags=["x" * 51])
    with pytest.raises(ValueError, match="whitespace"):
        RetrievalRequest(query="   ")


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


async def test_retrieval_route_is_authenticated_and_workspace_scoped(
    client: AsyncClient,
) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.state.auth_verifier = Verifier()
    app.state.supabase_data = Data()
    app.state.retrieval = service(Admin())

    response = await client.post(
        "/v1/retrieval/search",
        headers={
            "Authorization": "Bearer token",
            "X-Workspace-ID": str(WORKSPACE_ID),
        },
        json={"query": "reset token", "mode": "hybrid"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["document_id"] == str(DOCUMENT_ID)
