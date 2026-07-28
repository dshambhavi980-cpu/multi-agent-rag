from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request

from app.api.dependencies import AuthContext, get_auth_context, require_workspace_access
from app.models.memory import MemoryDeleted, MemoryPage, MemoryVisibility
from app.services.memory import MemoryService

router = APIRouter(prefix="/v1/memories", tags=["Memory"])

WorkspaceHeader = Annotated[UUID, Header(alias="X-Workspace-ID")]
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)]
AuthDependency = Annotated[AuthContext, Depends(get_auth_context)]


@router.get("", operation_id="listMemory", response_model=MemoryPage)
async def list_memory(
    request: Request,
    workspace_id: WorkspaceHeader,
    auth: AuthDependency,
    visibility: Annotated[MemoryVisibility | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MemoryPage:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(MemoryService, request.app.state.memory)
    return await service.list_items(
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        visibility=visibility,
        limit=limit,
    )


@router.delete(
    "/{memory_id}",
    operation_id="deleteMemory",
    response_model=MemoryDeleted,
)
async def delete_memory(
    memory_id: UUID,
    request: Request,
    workspace_id: WorkspaceHeader,
    idempotency_key: IdempotencyHeader,
    auth: AuthDependency,
) -> MemoryDeleted:
    del idempotency_key
    await require_workspace_access(workspace_id, request, auth)
    service = cast(MemoryService, request.app.state.memory)
    return await service.delete_item(
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        memory_id=memory_id,
    )
