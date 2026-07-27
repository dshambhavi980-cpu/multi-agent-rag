import asyncio
from collections.abc import Mapping
from time import monotonic
from typing import Any, cast
from uuid import UUID

import httpx
import jwt
from jwt import InvalidTokenError, PyJWK

from app.models.auth import AuthenticatedUser


class AuthenticationError(Exception):
    def __init__(
        self,
        code: str,
        detail: str,
        *,
        status: int = 401,
        retryable: bool = False,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status
        self.retryable = retryable


class SupabaseJwtVerifier:
    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        cache_seconds: int,
        timeout_seconds: float,
    ) -> None:
        base_url = supabase_url.rstrip("/")
        self._issuer = f"{base_url}/auth/v1"
        self._jwks_url = f"{self._issuer}/.well-known/jwks.json"
        self._cache_seconds = cache_seconds
        self._keys: dict[str, PyJWK] = {}
        self._expires_at = 0.0
        self._lock = asyncio.Lock()
        timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 1.5))
        self._client = httpx.AsyncClient(
            headers={"apikey": publishable_key},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def verify(self, token: str) -> AuthenticatedUser:
        try:
            header = jwt.get_unverified_header(token)
            key_id = header.get("kid")
            algorithm = header.get("alg")
            if not isinstance(key_id, str) or algorithm not in {"ES256", "RS256"}:
                raise AuthenticationError(
                    "INVALID_ACCESS_TOKEN",
                    "The access token uses an unsupported signing key.",
                )

            signing_key = await self._get_key(key_id)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience="authenticated",
                issuer=self._issuer,
                options={"require": ["aud", "exp", "iss", "sub"]},
            )
            if claims.get("role") != "authenticated":
                raise AuthenticationError(
                    "INVALID_ACCESS_TOKEN",
                    "The access token is not an authenticated user token.",
                )
            return AuthenticatedUser(
                id=UUID(str(claims["sub"])),
                email=_optional_string(claims.get("email")),
                role="authenticated",
            )
        except AuthenticationError:
            raise
        except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError(
                "INVALID_ACCESS_TOKEN",
                "The access token is invalid or expired.",
            ) from exc

    async def _get_key(self, key_id: str) -> PyJWK:
        now = monotonic()
        cached = self._keys.get(key_id)
        if cached is not None and now < self._expires_at:
            return cached

        async with self._lock:
            now = monotonic()
            cached = self._keys.get(key_id)
            if cached is not None and now < self._expires_at:
                return cached
            await self._refresh_keys()
            resolved = self._keys.get(key_id)
            if resolved is None:
                raise AuthenticationError(
                    "INVALID_ACCESS_TOKEN",
                    "The access token signing key is unknown.",
                )
            return resolved

    async def _refresh_keys(self) -> None:
        try:
            response = await self._client.get(self._jwks_url)
            response.raise_for_status()
            payload = cast(Mapping[str, Any], response.json())
            raw_keys = payload.get("keys")
            if not isinstance(raw_keys, list) or not raw_keys:
                raise ValueError("JWKS did not contain signing keys.")
            parsed = {
                str(raw_key["kid"]): PyJWK.from_dict(raw_key)
                for raw_key in raw_keys
                if isinstance(raw_key, dict) and isinstance(raw_key.get("kid"), str)
            }
            if not parsed:
                raise ValueError("JWKS did not contain usable signing keys.")
            self._keys = parsed
            self._expires_at = monotonic() + self._cache_seconds
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise AuthenticationError(
                "AUTH_PROVIDER_UNAVAILABLE",
                "Authentication verification is temporarily unavailable.",
                status=503,
                retryable=True,
            ) from exc


class UnavailableJwtVerifier:
    async def aclose(self) -> None:
        return None

    async def verify(self, token: str) -> AuthenticatedUser:
        del token
        raise AuthenticationError(
            "AUTH_NOT_CONFIGURED",
            "Supabase authentication is not configured.",
            status=503,
        )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
