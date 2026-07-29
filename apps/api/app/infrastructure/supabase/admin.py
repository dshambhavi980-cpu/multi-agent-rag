from typing import Any, cast

import httpx

from app.api.errors import ApplicationError


class SupabaseAdminClient:
    def __init__(self, *, supabase_url: str, service_key: str, timeout_seconds: float) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{supabase_url.rstrip('/')}/rest/v1/rpc",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 1.5)),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        try:
            response = await self._client.post(f"/{name}", json=payload)
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

    async def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        del name, payload
        raise ApplicationError(
            "SERVICE_ROLE_NOT_CONFIGURED",
            "Document ingestion unavailable",
            "APP_SUPABASE_SERVICE_ROLE_KEY is required by the backend.",
            status=503,
        )
