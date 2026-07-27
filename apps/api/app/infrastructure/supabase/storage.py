from urllib.parse import parse_qs, quote, urlparse

import httpx

from app.api.errors import ApplicationError

BUCKET = "workspace-documents"


class SupabaseStorageClient:
    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        service_key: str | None,
        timeout_seconds: float,
    ) -> None:
        self.base_url = supabase_url.rstrip("/")
        self.publishable_key = publishable_key
        self.service_key = service_key
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(max(timeout_seconds, 30), connect=min(timeout_seconds, 2))
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_signed_upload(self, path: str, access_token: str) -> tuple[str, str]:
        encoded = quote(path, safe="/")
        response = await self._client.post(
            f"{self.base_url}/storage/v1/object/upload/sign/{BUCKET}/{encoded}",
            headers={"apikey": self.publishable_key, "Authorization": f"Bearer {access_token}"},
            json={},
        )
        self._raise(response, "Could not create the signed upload URL.")
        url = str(response.json()["url"])
        token = parse_qs(urlparse(url).query).get("token", [""])[0]
        if not token:
            raise ApplicationError(
                "STORAGE_RESPONSE_INVALID",
                "Storage response invalid",
                "Storage did not return an upload token.",
                status=502,
                retryable=True,
            )
        return (url if url.startswith("http") else f"{self.base_url}/storage/v1{url}", token)

    async def create_signed_download(
        self, path: str, access_token: str, *, expires_in: int = 60
    ) -> str:
        encoded = quote(path, safe="/")
        response = await self._client.post(
            f"{self.base_url}/storage/v1/object/sign/{BUCKET}/{encoded}",
            headers={"apikey": self.publishable_key, "Authorization": f"Bearer {access_token}"},
            json={"expiresIn": expires_in},
        )
        self._raise(response, "Could not create the signed document URL.")
        signed_url = str(response.json().get("signedURL", ""))
        if not signed_url:
            raise ApplicationError(
                "STORAGE_RESPONSE_INVALID",
                "Storage response invalid",
                "Storage did not return a signed document URL.",
                status=502,
                retryable=True,
            )
        return (
            signed_url
            if signed_url.startswith("http")
            else f"{self.base_url}/storage/v1{signed_url}"
        )

    async def download(self, path: str, access_token: str | None = None) -> bytes:
        key = access_token or self.service_key
        if key is None:
            raise ApplicationError(
                "SERVICE_ROLE_NOT_CONFIGURED",
                "Document ingestion unavailable",
                "APP_SUPABASE_SERVICE_ROLE_KEY is required by the backend.",
                status=503,
            )
        response = await self._client.get(
            f"{self.base_url}/storage/v1/object/authenticated/{BUCKET}/{quote(path, safe='/')}",
            headers={"apikey": self.publishable_key, "Authorization": f"Bearer {key}"},
        )
        self._raise(response, "The uploaded object could not be downloaded.")
        return response.content

    async def remove(self, path: str) -> None:
        if self.service_key is None:
            return
        response = await self._client.request(
            "DELETE",
            f"{self.base_url}/storage/v1/object/{BUCKET}",
            headers={"apikey": self.service_key, "Authorization": f"Bearer {self.service_key}"},
            json={"prefixes": [path]},
        )
        self._raise(response, "The duplicate object could not be removed.")

    @staticmethod
    def _raise(response: httpx.Response, detail: str) -> None:
        if response.is_success:
            return
        raise ApplicationError(
            "STORAGE_PROVIDER_ERROR",
            "Storage request failed",
            detail,
            status=503 if response.status_code >= 500 else 422,
            retryable=response.status_code >= 500,
        )


class UnavailableStorageClient:
    async def aclose(self) -> None:
        return None

    async def create_signed_upload(self, path: str, access_token: str) -> tuple[str, str]:
        del path, access_token
        raise ApplicationError(
            "STORAGE_NOT_CONFIGURED",
            "Storage unavailable",
            "Supabase Storage is not configured.",
            status=503,
        )

    async def create_signed_download(
        self, path: str, access_token: str, *, expires_in: int = 60
    ) -> str:
        del path, access_token, expires_in
        raise ApplicationError(
            "STORAGE_NOT_CONFIGURED",
            "Storage unavailable",
            "Supabase Storage is not configured.",
            status=503,
        )
