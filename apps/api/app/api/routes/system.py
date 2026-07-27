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
    return Version(
        version=settings.app_version,
        commit=settings.git_sha,
        environment=settings.environment,
    )
