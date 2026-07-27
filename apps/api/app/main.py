from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.errors import install_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.rag import router as rag_router
from app.api.routes.retrieval import router as retrieval_router
from app.api.routes.system import router as system_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.infrastructure.gemini import (
    GeminiEmbeddingClient,
    GeminiEmbeddingConfig,
    UnavailableEmbeddingClient,
)
from app.infrastructure.generation import (
    GeminiGenerationClient,
    GeminiGenerationConfig,
    UnavailableGenerationClient,
)
from app.infrastructure.supabase.admin import SupabaseAdminClient, UnavailableAdminClient
from app.infrastructure.supabase.auth import SupabaseJwtVerifier, UnavailableJwtVerifier
from app.infrastructure.supabase.data import SupabaseDataClient, UnavailableDataClient
from app.infrastructure.supabase.storage import SupabaseStorageClient, UnavailableStorageClient
from app.services.ingestion_worker import IngestionWorker, WorkerConfig
from app.services.rag import GroundedRagService, RagConfig
from app.services.readiness import ReadinessRegistry, static_check
from app.services.retrieval import HybridRetrievalService, RetrievalConfig


def _build_embedding_client(
    settings: Settings,
) -> GeminiEmbeddingClient | UnavailableEmbeddingClient:
    if settings.gemini_api_key is None:
        return UnavailableEmbeddingClient()
    return GeminiEmbeddingClient(
        api_key=settings.gemini_api_key.get_secret_value(),
        config=GeminiEmbeddingConfig(
            model=settings.gemini_embedding_model,
            dimensions=settings.embedding_dimensions,
            timeout_seconds=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
            retry_base_seconds=settings.embedding_retry_base_seconds,
        ),
    )


def _build_retrieval_service(
    settings: Settings,
    admin: Any,
    embeddings: Any,
) -> HybridRetrievalService:
    return HybridRetrievalService(
        admin=admin,
        embeddings=embeddings,
        config=RetrievalConfig(
            embedding_cache_ttl_seconds=settings.query_embedding_cache_ttl_seconds,
            result_cache_ttl_seconds=settings.retrieval_cache_ttl_seconds,
            rrf_k=settings.retrieval_rrf_k,
            dense_weight=settings.retrieval_dense_weight,
            sparse_weight=settings.retrieval_sparse_weight,
            duplicate_threshold=settings.retrieval_duplicate_threshold,
        ),
    )


def _build_generation_client(
    settings: Settings,
) -> GeminiGenerationClient | UnavailableGenerationClient:
    if settings.gemini_api_key is None:
        return UnavailableGenerationClient()
    return GeminiGenerationClient(
        api_key=settings.gemini_api_key.get_secret_value(),
        config=GeminiGenerationConfig(
            model=settings.gemini_chat_model,
            timeout_seconds=settings.generation_timeout_seconds,
            max_retries=settings.generation_max_retries,
            retry_base_seconds=settings.generation_retry_base_seconds,
            max_output_tokens=settings.generation_max_output_tokens,
        ),
    )


def _build_rag_service(
    settings: Settings,
    admin: Any,
    retrieval: HybridRetrievalService,
    generation: Any,
) -> GroundedRagService:
    return GroundedRagService(
        admin=admin,
        retrieval=retrieval,
        generation=generation,
        config=RagConfig(
            evidence_limit=settings.rag_evidence_limit,
            candidate_count=settings.rag_candidate_count,
            timeout_seconds=settings.rag_timeout_seconds,
            insufficient_semantic_threshold=settings.rag_insufficient_semantic_threshold,
            event_poll_seconds=settings.rag_event_poll_seconds,
            heartbeat_seconds=settings.rag_heartbeat_seconds,
        ),
    )


def _install_routes(application: FastAPI) -> None:
    application.include_router(system_router)
    application.include_router(auth_router)
    application.include_router(documents_router)
    application.include_router(retrieval_router)
    application.include_router(rag_router)


def create_app(settings: Settings | None = None) -> FastAPI:  # noqa: PLR0915
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level, resolved_settings.environment)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.started_monotonic = monotonic()
        application.state.readiness = ReadinessRegistry(
            checks={"application": static_check("ready")}
        )
        supabase_setting = resolved_settings.supabase_url
        publishable_key_setting = resolved_settings.supabase_publishable_key
        if supabase_setting is not None and publishable_key_setting is not None:
            supabase_url = str(supabase_setting)
            publishable_key = publishable_key_setting.get_secret_value()
            application.state.auth_verifier = SupabaseJwtVerifier(
                supabase_url=supabase_url,
                publishable_key=publishable_key,
                cache_seconds=resolved_settings.supabase_jwks_cache_seconds,
                timeout_seconds=resolved_settings.supabase_http_timeout_seconds,
            )
            application.state.supabase_data = SupabaseDataClient(
                supabase_url=supabase_url,
                publishable_key=publishable_key,
                timeout_seconds=resolved_settings.supabase_http_timeout_seconds,
            )
            service_setting = resolved_settings.supabase_service_role_key
            service_key = service_setting.get_secret_value() if service_setting else None
            application.state.supabase_storage = SupabaseStorageClient(
                supabase_url=supabase_url,
                publishable_key=publishable_key,
                service_key=service_key,
                timeout_seconds=resolved_settings.supabase_http_timeout_seconds,
            )
            if service_key:
                application.state.supabase_admin = SupabaseAdminClient(
                    supabase_url=supabase_url,
                    service_key=service_key,
                    timeout_seconds=resolved_settings.supabase_http_timeout_seconds,
                )
            else:
                application.state.supabase_admin = UnavailableAdminClient()
            application.state.embeddings = _build_embedding_client(resolved_settings)
            application.state.generation = _build_generation_client(resolved_settings)
        else:
            application.state.auth_verifier = UnavailableJwtVerifier()
            application.state.supabase_data = UnavailableDataClient()
            application.state.supabase_storage = UnavailableStorageClient()
            application.state.supabase_admin = UnavailableAdminClient()
            application.state.embeddings = UnavailableEmbeddingClient()
            application.state.generation = UnavailableGenerationClient()
        worker = None
        application.state.retrieval = _build_retrieval_service(
            resolved_settings,
            application.state.supabase_admin,
            application.state.embeddings,
        )
        application.state.rag = _build_rag_service(
            resolved_settings,
            application.state.supabase_admin,
            application.state.retrieval,
            application.state.generation,
        )
        if (
            resolved_settings.ingestion_worker_enabled
            and isinstance(application.state.supabase_admin, SupabaseAdminClient)
            and isinstance(application.state.supabase_storage, SupabaseStorageClient)
            and isinstance(application.state.embeddings, GeminiEmbeddingClient)
        ):
            worker = IngestionWorker(
                admin=application.state.supabase_admin,
                storage=application.state.supabase_storage,
                embeddings=application.state.embeddings,
                config=WorkerConfig(
                    poll_seconds=resolved_settings.ingestion_poll_seconds,
                    visibility_seconds=resolved_settings.ingestion_visibility_seconds,
                    batch_size=resolved_settings.ingestion_batch_size,
                    parse_timeout_seconds=resolved_settings.ingestion_parse_timeout_seconds,
                    index_version=resolved_settings.index_version,
                    chunk_strategy=resolved_settings.index_strategy,
                    chunk_target_chars=resolved_settings.index_target_chars,
                    chunk_overlap_chars=resolved_settings.index_overlap_chars,
                    embedding_batch_size=resolved_settings.embedding_batch_size,
                ),
            )
            worker.start()
        application.state.ingestion_worker = worker
        get_logger().info(
            "application_started",
            environment=resolved_settings.environment,
            version=resolved_settings.app_version,
        )
        yield
        if worker:
            await worker.stop()
        await application.state.rag.aclose()
        await application.state.auth_verifier.aclose()
        await application.state.supabase_data.aclose()
        await application.state.supabase_storage.aclose()
        await application.state.supabase_admin.aclose()
        await application.state.generation.aclose()
        await application.state.embeddings.aclose()
        get_logger().info("application_stopped")

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        docs_url="/docs" if resolved_settings.docs_enabled else None,
        redoc_url="/redoc" if resolved_settings.docs_enabled else None,
        openapi_url="/openapi.json" if resolved_settings.docs_enabled else None,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.package_version = __version__

    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in resolved_settings.cors_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Workspace-ID"],
        expose_headers=["X-Request-ID"],
    )
    install_error_handlers(application)
    _install_routes(application)
    return application


app = create_app()
