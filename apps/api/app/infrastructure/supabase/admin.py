from typing import Any, cast

import httpx

from app.api.errors import ApplicationError
from app.core.logging import get_logger


class SupabaseAdminClient:
    def __init__(self, *, supabase_url: str, service_key: str, timeout_seconds: float) -> None:
        self._supabase_url = supabase_url.rstrip("/")
        self._service_key = service_key
        self._client = httpx.AsyncClient(
            base_url=f"{self._supabase_url}/rest/v1/rpc",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 1.5)),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def table_delete(
        self,
        table: str,
        params: dict[str, str],
        *,
        request_timeout: float | httpx.Timeout | None = None,
    ) -> None:
        try:
            kwargs: dict[str, Any] = {}
            if request_timeout is not None:
                kwargs["timeout"] = request_timeout
            url = f"{self._supabase_url}/rest/v1/{table}"
            response = await self._client.delete(url, params=params, **kwargs)
            if not response.is_success:
                body = response.json() if response.content else {}
                get_logger().warning(
                    "supabase_admin_table_delete_failed",
                    table=table,
                    status=response.status_code,
                    body=body,
                )
        except Exception as exc:
            get_logger().warning(
                "supabase_admin_table_delete_exception",
                table=table,
                error=str(exc),
            )

    async def rpc(
        self,
        name: str,
        payload: dict[str, Any],
        *,
        request_timeout: float | httpx.Timeout | None = None,
    ) -> Any:
        try:
            kwargs: dict[str, Any] = {}
            if request_timeout is not None:
                kwargs["timeout"] = request_timeout
            response = await self._client.post(f"/{name}", json=payload, **kwargs)
            if not response.is_success:
                body = response.json()
                code = str(body.get("code", ""))
                status = {
                    "22023": 400,
                    "42501": 403,
                    "P0002": 404,
                    "54000": 413,
                    "55000": 409,
                }.get(code, 503)
                is_retrieval = "search" in name or "retrieval" in name
                raise ApplicationError(
                    (
                        "RETRIEVAL_REQUEST_REJECTED"
                        if is_retrieval
                        else "REINDEX_CONFLICT"
                        if status == 409
                        else "INGESTION_PROVIDER_ERROR"
                    ),
                    "Retrieval request rejected" if is_retrieval else "Indexing request rejected",
                    str(body.get("message", "The database rejected the request.")),
                    status=status,
                    retryable=status == 503,
                )
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        except ApplicationError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            get_logger().warning(
                "supabase_admin_rpc_failed",
                function=name,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise ApplicationError(
                "INGESTION_PROVIDER_UNAVAILABLE",
                "Ingestion provider unavailable",
                "The durable ingestion service is temporarily unavailable.",
                status=503,
                retryable=True,
            ) from exc

    async def claim(self, visibility: int, batch_size: int) -> list[dict[str, Any]]:
        value = await self.rpc(
            "claim_document_ingestion",
            {"p_visibility_seconds": visibility, "p_batch_size": batch_size},
        )
        return cast(list[dict[str, Any]], value)


class UnavailableAdminClient:
    async def aclose(self) -> None:
        return None

    async def rpc(
        self,
        name: str,
        payload: dict[str, Any],
        *,
        request_timeout: float | httpx.Timeout | None = None,
    ) -> Any:
        del name, payload, request_timeout
        raise ApplicationError(
            "SERVICE_ROLE_NOT_CONFIGURED",
            "Document ingestion unavailable",
            "APP_SUPABASE_SERVICE_ROLE_KEY is required by the backend.",
            status=503,
        )

    async def table_delete(
        self,
        table: str,
        params: dict[str, str],
        *,
        request_timeout: float | httpx.Timeout | None = None,
    ) -> None:
        del table, params, request_timeout
        raise ApplicationError(
            "SERVICE_ROLE_NOT_CONFIGURED",
            "Database operation unavailable",
            "APP_SUPABASE_SERVICE_ROLE_KEY is required by the backend.",
            status=503,
        )
