from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from app.api.dependencies import AuthContext, get_auth_context, require_workspace_access
from app.models.retrieval import RetrievalRequest, RetrievalResponse
from app.services.retrieval import HybridRetrievalService

router = APIRouter(prefix="/v1/retrieval", tags=["Retrieval"])


@router.post(
    "/search",
    operation_id="hybridSearch",
    response_model=RetrievalResponse,
)
async def hybrid_search(
    body: RetrievalRequest,
    request: Request,
    workspace_id: Annotated[UUID, Header(alias="X-Workspace-ID")],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> RetrievalResponse:
    await require_workspace_access(workspace_id, request, auth)
    retrieval = cast(HybridRetrievalService, request.app.state.retrieval)
    return await retrieval.search(
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        request_id=request.state.request_id,
        request=body,
    )
