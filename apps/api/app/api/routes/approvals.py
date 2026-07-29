from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request

from app.api.dependencies import AuthContext, get_auth_context, require_workspace_access
from app.models.approvals import (
    Approval,
    ApprovalDecisionRequest,
    ApprovalPage,
    ApprovalStatus,
    RevisionRequest,
)
from app.services.approvals import ApprovalService
from app.services.rag import GroundedRagService

router = APIRouter(prefix="/v1/approvals", tags=["Approvals"])
WorkspaceHeader = Annotated[UUID, Header(alias="X-Workspace-ID")]
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)]
AuthDependency = Annotated[AuthContext, Depends(get_auth_context)]


@router.get("", operation_id="listApprovals", response_model=ApprovalPage)
async def list_approvals(
    request: Request,
    workspace_id: WorkspaceHeader,
    auth: AuthDependency,
    status: Annotated[ApprovalStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ApprovalPage:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(ApprovalService, request.app.state.approvals)
    return await service.list(
        workspace_id=workspace_id, actor_id=auth.user.id, status=status, limit=limit
    )


@router.get("/{approval_id}", operation_id="getApproval", response_model=Approval)
async def get_approval(
    approval_id: UUID,
    request: Request,
    workspace_id: WorkspaceHeader,
    auth: AuthDependency,
) -> Approval:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(ApprovalService, request.app.state.approvals)
    return await service.get(
        workspace_id=workspace_id, actor_id=auth.user.id, approval_id=approval_id
    )


async def _decide(  # noqa: PLR0913
    *,
    action: Literal["approve", "reject", "revise"],
    approval_id: UUID,
    request: Request,
    workspace_id: UUID,
    actor_id: UUID,
    idempotency_key: str,
    comment: str,
    edited_output: str | None = None,
) -> Approval:
    service = cast(ApprovalService, request.app.state.approvals)
    approval, run_id, resume_required = await service.decide(
        workspace_id=workspace_id,
        actor_id=actor_id,
        approval_id=approval_id,
        idempotency_key=idempotency_key,
        action=action,
        comment=comment,
        edited_output=edited_output,
    )
    if resume_required:
        rag = cast(GroundedRagService, request.app.state.rag)
        await rag.resume_from_review(run_id=run_id, workspace_id=workspace_id)
    return approval


@router.post("/{approval_id}/approve", operation_id="approveRun", response_model=Approval)
async def approve(  # noqa: PLR0913, PLR0917 - FastAPI dependencies
    approval_id: UUID,
    body: ApprovalDecisionRequest,
    request: Request,
    workspace_id: WorkspaceHeader,
    idempotency_key: IdempotencyHeader,
    auth: AuthDependency,
) -> Approval:
    await require_workspace_access(workspace_id, request, auth)
    return await _decide(
        action="approve",
        approval_id=approval_id,
        request=request,
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        idempotency_key=idempotency_key,
        comment=body.comment,
        edited_output=body.edited_output,
    )


@router.post("/{approval_id}/reject", operation_id="rejectRun", response_model=Approval)
async def reject(  # noqa: PLR0913, PLR0917 - FastAPI dependencies
    approval_id: UUID,
    body: ApprovalDecisionRequest,
    request: Request,
    workspace_id: WorkspaceHeader,
    idempotency_key: IdempotencyHeader,
    auth: AuthDependency,
) -> Approval:
    await require_workspace_access(workspace_id, request, auth)
    return await _decide(
        action="reject",
        approval_id=approval_id,
        request=request,
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        idempotency_key=idempotency_key,
        comment=body.comment,
    )


@router.post("/{approval_id}/revise", operation_id="requestRunRevision", response_model=Approval)
async def revise(  # noqa: PLR0913, PLR0917 - FastAPI dependencies
    approval_id: UUID,
    body: RevisionRequest,
    request: Request,
    workspace_id: WorkspaceHeader,
    idempotency_key: IdempotencyHeader,
    auth: AuthDependency,
) -> Approval:
    await require_workspace_access(workspace_id, request, auth)
    return await _decide(
        action="revise",
        approval_id=approval_id,
        request=request,
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        idempotency_key=idempotency_key,
        comment=body.comment,
    )
