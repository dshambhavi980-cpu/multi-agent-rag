from typing import Any, cast
from uuid import UUID

import httpx

from app.infrastructure.supabase.auth import AuthenticationError
from app.models.auth import WorkspaceAccess
from app.models.documents import Document, IngestionJob


class SupabaseDataClient:
    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        timeout_seconds: float,
    ) -> None:
        timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 1.5))
        self._client = httpx.AsyncClient(
            base_url=f"{supabase_url.rstrip('/')}/rest/v1",
            headers={"apikey": publishable_key},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_workspace_access(
        self,
        *,
        access_token: str,
        workspace_id: UUID,
        user_id: UUID,
    ) -> WorkspaceAccess | None:
        try:
            response = await self._client.get(
                "/workspace_members",
                params={
                    "select": "workspace_id,user_id,role",
                    "workspace_id": f"eq.{workspace_id}",
                    "user_id": f"eq.{user_id}",
                    "limit": "1",
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            records = cast(list[dict[str, Any]], response.json())
            return WorkspaceAccess.model_validate(records[0]) if records else None
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise AuthenticationError(
                "DATA_PROVIDER_UNAVAILABLE",
                "Workspace authorization is temporarily unavailable.",
                status=503,
                retryable=True,
            ) from exc

    async def create_upload_session(
        self, *, access_token: str, record: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request_one("POST", "/document_uploads", access_token, json=record)

    async def get_upload_session(
        self, *, access_token: str, upload_id: UUID
    ) -> dict[str, Any] | None:
        records = await self._request_many(
            "GET",
            "/document_uploads",
            access_token,
            params={"select": "*", "id": f"eq.{upload_id}", "limit": "1"},
        )
        return records[0] if records else None

    async def list_documents(
        self, *, access_token: str, workspace_id: UUID, limit: int
    ) -> list[Document]:
        records = await self._request_many(
            "GET",
            "/documents",
            access_token,
            params={
                "select": "*",
                "workspace_id": f"eq.{workspace_id}",
                "order": "created_at.desc",
                "limit": str(limit),
            },
        )
        return [Document.model_validate(record) for record in records]

    async def get_document(self, *, access_token: str, document_id: UUID) -> Document | None:
        records = await self._request_many(
            "GET",
            "/documents",
            access_token,
            params={"select": "*", "id": f"eq.{document_id}", "limit": "1"},
        )
        return Document.model_validate(records[0]) if records else None

    async def get_ingestion_job(self, *, access_token: str, job_id: UUID) -> IngestionJob | None:
        records = await self._request_many(
            "GET",
            "/ingestion_jobs",
            access_token,
            params={"select": "*", "id": f"eq.{job_id}", "limit": "1"},
        )
        return IngestionJob.model_validate(records[0]) if records else None

    async def _request_many(
        self,
        method: str,
        path: str,
        access_token: str,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        try:
            headers = {"Authorization": f"Bearer {access_token}", **kwargs.pop("headers", {})}
            response = await self._client.request(
                method,
                path,
                headers=headers,
                **kwargs,
            )
            response.raise_for_status()
            return cast(list[dict[str, Any]], response.json())
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise AuthenticationError(
                "DATA_PROVIDER_UNAVAILABLE",
                "Document data is temporarily unavailable.",
                status=503,
                retryable=True,
            ) from exc

    async def _request_one(
        self,
        method: str,
        path: str,
        access_token: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Prefer": "return=representation",
        }
        records = await self._request_many(method, path, access_token, headers=headers, **kwargs)
        if not records:
            raise AuthenticationError(
                "DATA_PROVIDER_UNAVAILABLE",
                "The database did not return the created record.",
                status=503,
                retryable=True,
            )
        return records[0]


class UnavailableDataClient:
    async def aclose(self) -> None:
        return None

    async def get_workspace_access(
        self,
        *,
        access_token: str,
        workspace_id: UUID,
        user_id: UUID,
    ) -> WorkspaceAccess | None:
        del access_token, workspace_id, user_id
        raise AuthenticationError(
            "DATA_PROVIDER_NOT_CONFIGURED",
            "Supabase data access is not configured.",
            status=503,
        )

    def __getattr__(self, name: str) -> Any:
        if name.startswith(("create_", "get_", "list_")):

            async def unavailable(**kwargs: Any) -> Any:
                del kwargs
                raise AuthenticationError(
                    "DATA_PROVIDER_NOT_CONFIGURED",
                    "Supabase data access is not configured.",
                    status=503,
                )

            return unavailable
        raise AttributeError(name)
