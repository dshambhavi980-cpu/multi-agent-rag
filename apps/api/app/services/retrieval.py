import hashlib
import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol, cast
from uuid import UUID

from app.api.errors import ApplicationError
from app.core.logging import get_logger
from app.infrastructure.supabase.admin import SupabaseAdminClient
from app.models.retrieval import RetrievalRequest, RetrievalResponse


class QueryEmbeddingClient(Protocol):
    model: str
    dimensions: int

    async def embed_queries(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class RetrievalConfig:
    embedding_cache_ttl_seconds: int = 86400
    result_cache_ttl_seconds: int = 900
    rrf_k: int = 60
    dense_weight: float = 1
    sparse_weight: float = 1
    duplicate_threshold: float = 0.92


class HybridRetrievalService:
    def __init__(
        self,
        *,
        admin: SupabaseAdminClient,
        embeddings: QueryEmbeddingClient,
        config: RetrievalConfig,
    ) -> None:
        self.admin = admin
        self.embeddings = embeddings
        self.config = config

    async def search(
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        request_id: UUID,
        request: RetrievalRequest,
    ) -> RetrievalResponse:
        started = perf_counter()
        normalized_query = " ".join(request.query.casefold().split())
        query_hash = hashlib.sha256(normalized_query.encode()).hexdigest()
        filters = request.filters.model_dump(mode="json", exclude_none=True)
        request_fingerprint = {
            "query_hash": query_hash,
            "mode": request.mode,
            "limit": request.limit,
            "candidate_count": request.candidate_count,
            "filters": filters,
            "rrf_k": self.config.rrf_k,
            "dense_weight": self.config.dense_weight,
            "sparse_weight": self.config.sparse_weight,
            "duplicate_threshold": self.config.duplicate_threshold,
            "embedding_model": self.embeddings.model,
            "embedding_dimensions": self.embeddings.dimensions,
        }
        request_hash = hashlib.sha256(
            json.dumps(request_fingerprint, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        embedding_started = perf_counter()
        cached = await self.admin.rpc(
            "get_query_embedding_cache",
            {
                "p_query_hash": query_hash,
                "p_embedding_model": self.embeddings.model,
                "p_embedding_dimensions": self.embeddings.dimensions,
            },
        )
        embedding_cache_hit = cached is not None
        if cached is None:
            vectors = await self.embeddings.embed_queries([request.query])
            if len(vectors) != 1:
                raise ApplicationError(
                    "QUERY_EMBEDDING_ERROR",
                    "Query embedding failed",
                    "The embedding provider returned an invalid query embedding.",
                    status=502,
                    retryable=False,
                )
            query_embedding = vectors[0]
            await self.admin.rpc(
                "put_query_embedding_cache",
                {
                    "p_query_hash": query_hash,
                    "p_embedding_model": self.embeddings.model,
                    "p_embedding_dimensions": self.embeddings.dimensions,
                    "p_embedding": query_embedding,
                    "p_ttl_seconds": self.config.embedding_cache_ttl_seconds,
                },
            )
        else:
            try:
                query_embedding = cast(list[float], json.loads(str(cached)))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ApplicationError(
                    "QUERY_CACHE_INVALID",
                    "Query cache invalid",
                    "The cached query embedding could not be read.",
                    status=503,
                    retryable=True,
                ) from exc
        embedding_ms = (perf_counter() - embedding_started) * 1000

        database_started = perf_counter()
        result = cast(
            dict[str, Any],
            await self.admin.rpc(
                "hybrid_search",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_request_id": str(request_id),
                    "p_query_text": request.query,
                    "p_query_hash": query_hash,
                    "p_request_hash": request_hash,
                    "p_query_embedding": query_embedding,
                    "p_embedding_cache_hit": embedding_cache_hit,
                    "p_mode": request.mode,
                    "p_match_count": request.limit,
                    "p_candidate_count": request.candidate_count,
                    "p_rrf_k": self.config.rrf_k,
                    "p_dense_weight": self.config.dense_weight,
                    "p_sparse_weight": self.config.sparse_weight,
                    "p_duplicate_threshold": self.config.duplicate_threshold,
                    "p_document_ids": (
                        [str(value) for value in request.filters.document_ids]
                        if request.filters.document_ids
                        else None
                    ),
                    "p_created_after": (
                        request.filters.created_after.isoformat()
                        if request.filters.created_after
                        else None
                    ),
                    "p_created_before": (
                        request.filters.created_before.isoformat()
                        if request.filters.created_before
                        else None
                    ),
                    "p_content_types": request.filters.content_types,
                    "p_tags": request.filters.tags,
                    "p_cache_ttl_seconds": self.config.result_cache_ttl_seconds,
                    "p_filters": filters,
                },
            ),
        )
        database_ms = (perf_counter() - database_started) * 1000
        total_ms = (perf_counter() - started) * 1000
        response = RetrievalResponse.model_validate(
            {
                **result,
                "embedding_cache_hit": embedding_cache_hit,
                "embedding_ms": embedding_ms,
                "database_ms": database_ms,
                "total_ms": total_ms,
            }
        )
        try:
            await self.admin.rpc(
                "update_retrieval_trace_timings",
                {
                    "p_trace_id": str(response.trace_id),
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_embedding_ms": embedding_ms,
                    "p_database_ms": database_ms,
                    "p_total_ms": total_ms,
                },
            )
        except ApplicationError:
            get_logger().warning(
                "retrieval_trace_timing_update_failed",
                trace_id=str(response.trace_id),
                workspace_id=str(workspace_id),
            )
        return response
