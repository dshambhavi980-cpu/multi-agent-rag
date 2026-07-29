import asyncio
import json
from collections.abc import AsyncIterator
from time import monotonic
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies import AuthContext, get_auth_context, require_workspace_access
from app.models.rag import (
    Conversation,
    ConversationDetail,
    ConversationPage,
    CreateConversationRequest,
    CreateMessageRequest,
    OperationAccepted,
    Run,
    RunAccepted,
    RunPage,
    RunTrace,
    WorkspaceUsage,
)
from app.services.rag import (
    STREAM_END_STATUSES,
    GroundedRagService,
    heartbeat_event,
    sse_envelope,
)

router = APIRouter(prefix="/v1", tags=["Conversations", "Runs"])

WorkspaceHeader = Annotated[UUID, Header(alias="X-Workspace-ID")]
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)]
AuthDependency = Annotated[AuthContext, Depends(get_auth_context)]


@router.post(
    "/conversations",
    operation_id="createConversation",
    response_model=Conversation,
    status_code=201,
)
async def create_conversation(
    request: Request,
    workspace_id: WorkspaceHeader,
    idempotency_key: IdempotencyHeader,
    auth: AuthDependency,
    body: Annotated[CreateConversationRequest | None, Body()] = None,
) -> Conversation:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(GroundedRagService, request.app.state.rag)
    return await service.create_conversation(
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        title=body.title if body else None,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/conversations",
    operation_id="listConversations",
    response_model=ConversationPage,
)
async def list_conversations(
    request: Request,
    workspace_id: WorkspaceHeader,
    auth: AuthDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> ConversationPage:
    del cursor
    await require_workspace_access(workspace_id, request, auth)
    service = cast(GroundedRagService, request.app.state.rag)
    return await service.list_conversations(
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        limit=limit,
    )


@router.get(
    "/conversations/{conversation_id}",
    operation_id="getConversation",
    response_model=ConversationDetail,
)
async def get_conversation(
    conversation_id: UUID,
    request: Request,
    workspace_id: WorkspaceHeader,
    auth: AuthDependency,
) -> ConversationDetail:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(GroundedRagService, request.app.state.rag)
    return await service.get_conversation(
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        conversation_id=conversation_id,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    operation_id="createMessageRun",
    response_model=RunAccepted,
    status_code=202,
)
async def create_message_run(  # noqa: PLR0913, PLR0917 - FastAPI dependencies
    conversation_id: UUID,
    body: CreateMessageRequest,
    request: Request,
    workspace_id: WorkspaceHeader,
    idempotency_key: IdempotencyHeader,
    auth: AuthDependency,
) -> RunAccepted:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(GroundedRagService, request.app.state.rag)
    return await service.start_run(
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        conversation_id=conversation_id,
        request_id=request.state.request_id,
        idempotency_key=idempotency_key,
        body=body,
    )


@router.get("/runs/{run_id}", operation_id="getRun", response_model=Run)
async def get_run(
    run_id: UUID,
    request: Request,
    workspace_id: WorkspaceHeader,
    auth: AuthDependency,
) -> Run:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(GroundedRagService, request.app.state.rag)
    return await service.get_run(
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        run_id=run_id,
    )


@router.get("/runs", operation_id="listRuns", response_model=RunPage)
async def list_runs(
    request: Request,
    workspace_id: WorkspaceHeader,
    auth: AuthDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RunPage:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(GroundedRagService, request.app.state.rag)
    return await service.list_runs(
        workspace_id=workspace_id, actor_id=auth.user.id, limit=limit
    )


@router.get("/runs/{run_id}/trace", operation_id="getRunTrace", response_model=RunTrace)
async def get_run_trace(
    run_id: UUID,
    request: Request,
    workspace_id: WorkspaceHeader,
    auth: AuthDependency,
) -> RunTrace:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(GroundedRagService, request.app.state.rag)
    return await service.get_run_trace(
        workspace_id=workspace_id, actor_id=auth.user.id, run_id=run_id
    )


@router.get("/workspace/usage", operation_id="getWorkspaceUsage", response_model=WorkspaceUsage)
async def get_workspace_usage(
    request: Request,
    workspace_id: WorkspaceHeader,
    auth: AuthDependency,
) -> WorkspaceUsage:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(GroundedRagService, request.app.state.rag)
    return await service.workspace_usage(
        workspace_id=workspace_id, actor_id=auth.user.id
    )


@router.get("/runs/{run_id}/events", operation_id="streamRunEvents")
async def stream_run_events(
    run_id: UUID,
    request: Request,
    workspace_id: WorkspaceHeader,
    auth: AuthDependency,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    await require_workspace_access(workspace_id, request, auth)
    service = cast(GroundedRagService, request.app.state.rag)
    await service.get_run(workspace_id=workspace_id, actor_id=auth.user.id, run_id=run_id)
    try:
        after_sequence = max(int(last_event_id or "0"), 0)
    except ValueError:
        after_sequence = 0

    async def stream() -> AsyncIterator[str]:
        sequence = after_sequence
        last_emission = monotonic()
        while True:
            if await request.is_disconnected():
                return
            events = await service.events(
                workspace_id=workspace_id,
                actor_id=auth.user.id,
                run_id=run_id,
                after_sequence=sequence,
            )
            for event in events:
                sequence = int(event["sequence"])
                envelope = sse_envelope(event, run_id=run_id, workspace_id=workspace_id)
                yield (
                    f"id: {sequence}\n"
                    f"event: {event['event_type']}\n"
                    f"data: {json.dumps(envelope, separators=(',', ':'))}\n\n"
                )
                last_emission = monotonic()
            run = await service.get_run(
                workspace_id=workspace_id,
                actor_id=auth.user.id,
                run_id=run_id,
            )
            if run.status in STREAM_END_STATUSES and not events:
                return
            if monotonic() - last_emission >= service.config.heartbeat_seconds:
                heartbeat = heartbeat_event(run_id, workspace_id, sequence)
                yield (
                    "event: stream.heartbeat\n"
                    f"data: {json.dumps(heartbeat, separators=(',', ':'))}\n\n"
                )
                last_emission = monotonic()
            await asyncio.sleep(service.config.event_poll_seconds)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/runs/{run_id}/resume",
    operation_id="resumeRun",
    response_model=OperationAccepted,
    status_code=202,
)
async def resume_run(
    run_id: UUID,
    request: Request,
    workspace_id: WorkspaceHeader,
    idempotency_key: IdempotencyHeader,
    auth: AuthDependency,
) -> OperationAccepted:
    del idempotency_key
    await require_workspace_access(workspace_id, request, auth)
    service = cast(GroundedRagService, request.app.state.rag)
    run = await service.resume(
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        run_id=run_id,
    )
    return OperationAccepted(id=run_id, status=run.status)


@router.post(
    "/runs/{run_id}/cancel",
    operation_id="cancelRun",
    response_model=OperationAccepted,
    status_code=202,
)
async def cancel_run(
    run_id: UUID,
    request: Request,
    workspace_id: WorkspaceHeader,
    idempotency_key: IdempotencyHeader,
    auth: AuthDependency,
) -> OperationAccepted:
    del idempotency_key
    await require_workspace_access(workspace_id, request, auth)
    service = cast(GroundedRagService, request.app.state.rag)
    run = await service.cancel(
        workspace_id=workspace_id,
        actor_id=auth.user.id,
        run_id=run_id,
    )
    return OperationAccepted(id=run_id, status=run.status)
