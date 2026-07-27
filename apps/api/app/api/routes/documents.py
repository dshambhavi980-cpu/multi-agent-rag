import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, Header, Query, Request
from fastapi.responses import RedirectResponse

from app.api.dependencies import AuthContext, get_auth_context, require_workspace_access
from app.api.errors import ApplicationError
from app.infrastructure.supabase.admin import SupabaseAdminClient
from app.infrastructure.supabase.data import SupabaseDataClient
from app.infrastructure.supabase.storage import SupabaseStorageClient
from app.models.documents import (
    CompleteUploadRequest,
    CreateUploadUrlRequest,
    CreateUploadUrlResponse,
    Document,
    DocumentPage,
    IngestionAccepted,
    IngestionJob,
    ReindexRequest,
)

router = APIRouter(prefix="/v1", tags=["Documents"])

EXTENSIONS = {
    "application/pdf": {".pdf"},
    "text/plain": {".txt"},
    "text/markdown": {".md", ".markdown"},
    "text/html": {".html", ".htm"},
}


def _validate_file(filename: str, content_type: str) -> None:
    if Path(filename).suffix.lower() not in EXTENSIONS[content_type]:
        raise ApplicationError(
            "FILE_TYPE_MISMATCH",
            "File type mismatch",
            "The filename extension does not match the declared MIME type.",
            status=422,
        )
    if "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise ApplicationError(
            "INVALID_FILENAME",
            "Invalid filename",
            "Filename must not contain path separators.",
            status=422,
        )


def _validate_signature(data: bytes, content_type: str) -> None:
    if content_type == "application/pdf" and not data.startswith(b"%PDF-"):
        raise ApplicationError(
            "FILE_SIGNATURE_MISMATCH",
            "File signature mismatch",
            "The uploaded bytes are not a PDF.",
            status=422,
        )
    if content_type != "application/pdf" and b"\x00" in data[:8192]:
        raise ApplicationError(
            "FILE_SIGNATURE_MISMATCH",
            "File signature mismatch",
            "The uploaded bytes do not appear to be text.",
            status=422,
        )


@router.post(
    "/documents/upload-url",
    operation_id="createDocumentUploadUrl",
    response_model=CreateUploadUrlResponse,
    status_code=201,
)
async def create_upload_url(
    body: CreateUploadUrlRequest,
    request: Request,
    workspace_id: Annotated[UUID, Header(alias="X-Workspace-ID")],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> CreateUploadUrlResponse:
    await require_workspace_access(workspace_id, request, auth)
    _validate_file(body.filename, body.content_type)
    upload_id = uuid4()
    expires_at = datetime.now(UTC) + timedelta(hours=2)
    object_path = f"{workspace_id}/{auth.user.id}/{upload_id}/{body.filename}"
    data = cast(SupabaseDataClient, request.app.state.supabase_data)
    await data.create_upload_session(
        access_token=auth.access_token,
        record={
            "id": str(upload_id),
            "workspace_id": str(workspace_id),
            "uploaded_by": str(auth.user.id),
            "object_path": object_path,
            "filename": body.filename,
            "expected_content_type": body.content_type,
            "expected_size_bytes": body.size_bytes,
            "expected_sha256": body.sha256,
            "expires_at": expires_at.isoformat(),
        },
    )
    storage = cast(SupabaseStorageClient, request.app.state.supabase_storage)
    signed_url, token = await storage.create_signed_upload(object_path, auth.access_token)
    return CreateUploadUrlResponse(
        upload_id=upload_id,
        object_path=object_path,
        signed_url=signed_url,
        upload_token=token,
        expires_at=expires_at,
    )


@router.post(
    "/documents/complete-upload",
    operation_id="completeDocumentUpload",
    response_model=IngestionAccepted,
    status_code=202,
)
async def complete_upload(
    body: CompleteUploadRequest,
    request: Request,
    workspace_id: Annotated[UUID, Header(alias="X-Workspace-ID")],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> IngestionAccepted:
    await require_workspace_access(workspace_id, request, auth)
    data_client = cast(SupabaseDataClient, request.app.state.supabase_data)
    session = await data_client.get_upload_session(
        access_token=auth.access_token, upload_id=body.upload_id
    )
    if session is None or session["object_path"] != body.object_path:
        raise ApplicationError(
            "UPLOAD_SESSION_NOT_FOUND",
            "Upload session not found",
            "The upload session does not exist or does not own this object.",
            status=404,
        )
    if session["workspace_id"] != str(workspace_id) or session["uploaded_by"] != str(auth.user.id):
        raise ApplicationError(
            "UPLOAD_OWNERSHIP_MISMATCH",
            "Upload ownership mismatch",
            "The upload does not belong to this user and workspace.",
            status=403,
        )
    storage = cast(SupabaseStorageClient, request.app.state.supabase_storage)
    content = await storage.download(body.object_path, auth.access_token)
    actual_hash = hashlib.sha256(content).hexdigest()
    if (
        actual_hash != body.sha256
        or actual_hash != session["expected_sha256"]
        or len(content) != session["expected_size_bytes"]
    ):
        raise ApplicationError(
            "UPLOAD_INTEGRITY_FAILED",
            "Upload integrity check failed",
            "The uploaded object does not match its declared checksum or size.",
            status=422,
        )
    _validate_signature(content, str(session["expected_content_type"]))
    admin = cast(SupabaseAdminClient, request.app.state.supabase_admin)
    result = cast(
        dict[str, Any],
        await admin.rpc(
            "finalize_document_upload",
            {
                "p_upload_id": str(body.upload_id),
                "p_actor_id": str(auth.user.id),
                "p_actual_sha256": actual_hash,
                "p_actual_size_bytes": len(content),
                "p_actual_content_type": session["expected_content_type"],
                "p_request_id": str(request.state.request_id),
                "p_title": body.title,
                "p_tags": body.tags,
            },
        ),
    )
    duplicate_path = result.pop("duplicate_object_path", None)
    if duplicate_path:
        await storage.remove(str(duplicate_path))
    return IngestionAccepted.model_validate(result)


@router.get("/documents", operation_id="listDocuments", response_model=DocumentPage)
async def list_documents(
    request: Request,
    workspace_id: Annotated[UUID, Header(alias="X-Workspace-ID")],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DocumentPage:
    await require_workspace_access(workspace_id, request, auth)
    data = cast(SupabaseDataClient, request.app.state.supabase_data)
    return DocumentPage(
        items=await data.list_documents(
            access_token=auth.access_token, workspace_id=workspace_id, limit=limit
        )
    )


async def _get_workspace_document(
    *,
    document_id: UUID,
    workspace_id: UUID,
    access_token: str,
    data: SupabaseDataClient,
) -> Document:
    document = await data.get_document(
        access_token=access_token,
        document_id=document_id,
    )
    if document is None or document.workspace_id != workspace_id:
        raise ApplicationError(
            "DOCUMENT_NOT_FOUND",
            "Document not found",
            "The document was not found in this workspace.",
            status=404,
        )
    return document


@router.get(
    "/documents/{document_id}",
    operation_id="getDocument",
    response_model=Document,
)
async def get_document(
    document_id: UUID,
    request: Request,
    workspace_id: Annotated[UUID, Header(alias="X-Workspace-ID")],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> Document:
    await require_workspace_access(workspace_id, request, auth)
    data = cast(SupabaseDataClient, request.app.state.supabase_data)
    return await _get_workspace_document(
        document_id=document_id,
        workspace_id=workspace_id,
        access_token=auth.access_token,
        data=data,
    )


@router.get(
    "/documents/{document_id}/source",
    operation_id="openDocumentSource",
    response_class=RedirectResponse,
)
async def open_document_source(
    document_id: UUID,
    request: Request,
    workspace_id: Annotated[UUID, Header(alias="X-Workspace-ID")],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    page: Annotated[int | None, Query(ge=1)] = None,
) -> RedirectResponse:
    await require_workspace_access(workspace_id, request, auth)
    data = cast(SupabaseDataClient, request.app.state.supabase_data)
    document = await _get_workspace_document(
        document_id=document_id,
        workspace_id=workspace_id,
        access_token=auth.access_token,
        data=data,
    )
    storage = cast(SupabaseStorageClient, request.app.state.supabase_storage)
    signed_url = await storage.create_signed_download(
        document.object_path,
        auth.access_token,
    )
    if page is not None and document.content_type == "application/pdf":
        signed_url = f"{signed_url}#page={page}"
    return RedirectResponse(signed_url, status_code=307)


@router.get(
    "/ingestion-jobs/{job_id}",
    operation_id="getIngestionJob",
    response_model=IngestionJob,
)
async def get_ingestion_job(
    job_id: UUID,
    request: Request,
    workspace_id: Annotated[UUID, Header(alias="X-Workspace-ID")],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> IngestionJob:
    await require_workspace_access(workspace_id, request, auth)
    data = cast(SupabaseDataClient, request.app.state.supabase_data)
    job = await data.get_ingestion_job(access_token=auth.access_token, job_id=job_id)
    if job is None or job.workspace_id != workspace_id:
        raise ApplicationError(
            "INGESTION_JOB_NOT_FOUND",
            "Ingestion job not found",
            "The ingestion job was not found in this workspace.",
            status=404,
        )
    return job


@router.post(
    "/documents/{document_id}/reindex",
    operation_id="reindexDocument",
    response_model=IngestionJob,
    status_code=202,
)
async def reindex_document(
    document_id: UUID,
    request: Request,
    workspace_id: Annotated[UUID, Header(alias="X-Workspace-ID")],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    body: Annotated[ReindexRequest | None, Body()] = None,
) -> IngestionJob:
    access = await require_workspace_access(workspace_id, request, auth)
    if access.role != "owner":
        raise ApplicationError(
            "WORKSPACE_OWNER_REQUIRED",
            "Workspace owner required",
            "Only workspace owners can start re-indexing.",
            status=403,
        )
    admin = cast(SupabaseAdminClient, request.app.state.supabase_admin)
    result = await admin.rpc(
        "enqueue_document_reindex",
        {
            "p_document_id": str(document_id),
            "p_workspace_id": str(workspace_id),
            "p_actor_id": str(auth.user.id),
            "p_request_id": str(request.state.request_id),
            "p_strategy": body.strategy if body else None,
        },
    )
    return IngestionJob.model_validate(result)
