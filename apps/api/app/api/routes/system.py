import hashlib
import json
from datetime import UTC, datetime
from time import monotonic

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.models.system import Health, Readiness, Version

router = APIRouter(tags=["System"])


@router.get("/health", operation_id="getHealth", response_model=Health)
async def get_health(request: Request) -> Health:
    started = request.app.state.started_monotonic
    return Health(
        status="ok",
        time=datetime.now(UTC),
        cold_start=monotonic() - started < request.app.state.settings.cold_start_window_seconds,
    )


@router.get(
    "/ready",
    operation_id="getReadiness",
    response_model=Readiness,
    responses={503: {"model": Readiness}},
)
async def get_readiness(request: Request) -> Readiness | JSONResponse:
    result = await request.app.state.readiness.evaluate()
    response = Readiness(status=result.status, dependencies=result.dependencies)
    if result.status == "unavailable":
        return JSONResponse(status_code=503, content=response.model_dump(mode="json"))
    return response


@router.get("/version", operation_id="getVersion", response_model=Version)
async def get_version(request: Request) -> Version:
    settings = request.app.state.settings
    safe_configuration = {
        "agent_max_steps": settings.agent_max_steps,
        "cors_origins": sorted(str(origin).rstrip("/") for origin in settings.cors_origins),
        "cors_origin_regex": settings.cors_origin_regex,
        "embedding_model": settings.gemini_embedding_model,
        "environment": settings.environment,
        "generation_model": settings.gemini_chat_model,
        "index_strategy": settings.index_strategy,
        "ingestion_batch_size": settings.ingestion_batch_size,
        "provider_max_concurrency": settings.provider_max_concurrency,
        "rag_candidate_count": settings.rag_candidate_count,
        "rag_evidence_limit": settings.rag_evidence_limit,
        "rate_limit_enabled": settings.rate_limit_enabled,
    }
    fingerprint = hashlib.sha256(
        json.dumps(safe_configuration, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return Version(
        version=settings.app_version,
        commit=settings.git_sha,
        environment=settings.environment,
        release_id=settings.release_id,
        configuration_sha256=fingerprint,
    )
