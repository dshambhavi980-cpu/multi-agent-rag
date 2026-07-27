from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import AuthContext, get_auth_context, require_workspace_access
from app.models.auth import AuthenticatedUser, WorkspaceAccess

router = APIRouter(prefix="/v1", tags=["Authentication"])


@router.get("/auth/me", operation_id="getCurrentUser", response_model=AuthenticatedUser)
async def get_current_user(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AuthenticatedUser:
    return auth.user


@router.get(
    "/workspaces/{workspace_id}/access",
    operation_id="getWorkspaceAccess",
    response_model=WorkspaceAccess,
)
async def get_workspace_access(
    workspace_id: UUID,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> WorkspaceAccess:
    return await require_workspace_access(workspace_id, request, auth)
