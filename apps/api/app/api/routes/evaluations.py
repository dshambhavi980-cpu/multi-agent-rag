from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request

from app.api.dependencies import AuthContext, get_auth_context, require_workspace_access
from app.models.evaluations import (
    CreateEvaluationRequest,
    EvaluationPage,
    EvaluationRun,
    EvaluationSuiteSummary,
)
from app.services.evaluations import EvaluationService

router = APIRouter(prefix="/v1/evaluations", tags=["Evaluations"])

WorkspaceHeader = Annotated[UUID, Header(alias="X-Workspace-ID")]
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)]
AuthDependency = Annotated[AuthContext, Depends(get_auth_context)]


@router.get(
    "/suite",
    operation_id="getEvaluationSuite",
    response_model=EvaluationSuiteSummary,
)
async def get_evaluation_suite(
    request: Request,
    workspace_id: WorkspaceHeader,
    auth: AuthDependency,
) -> EvaluationSuiteSummary:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(EvaluationService, request.app.state.evaluations)
    return service.suite_summary()


@router.get("", operation_id="listEvaluationRuns", response_model=EvaluationPage)
async def list_evaluation_runs(
    request: Request,
    workspace_id: WorkspaceHeader,
    auth: AuthDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> EvaluationPage:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(EvaluationService, request.app.state.evaluations)
    return await service.list_runs(workspace_id=workspace_id, actor_id=auth.user.id, limit=limit)


@router.get(
    "/{evaluation_id}",
    operation_id="getEvaluationRun",
    response_model=EvaluationRun,
)
async def get_evaluation_run(
    evaluation_id: UUID,
    request: Request,
    workspace_id: WorkspaceHeader,
    auth: AuthDependency,
) -> EvaluationRun:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(EvaluationService, request.app.state.evaluations)
    return await service.get(
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        evaluation_id=evaluation_id,
    )


@router.post(
    "",
    operation_id="createEvaluationRun",
    response_model=EvaluationRun,
    status_code=202,
)
async def create_evaluation_run(
    body: CreateEvaluationRequest,
    request: Request,
    workspace_id: WorkspaceHeader,
    idempotency_key: IdempotencyHeader,
    auth: AuthDependency,
) -> EvaluationRun:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(EvaluationService, request.app.state.evaluations)
    return await service.create(
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        request_id=request.state.request_id,
        idempotency_key=idempotency_key,
        body=body,
    )
