from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import AsyncClient

from app.infrastructure.supabase.auth import AuthenticationError, SupabaseJwtVerifier
from app.infrastructure.supabase.data import SupabaseDataClient
from app.models.auth import AuthenticatedUser, WorkspaceAccess

USER_ID = UUID("10000000-0000-4000-8000-000000000001")
WORKSPACE_ID = UUID("a0000000-0000-4000-8000-000000000001")
ISSUER = "https://project.supabase.co/auth/v1"


class FakeVerifier:
    async def aclose(self) -> None:
        return None

    async def verify(self, token: str) -> AuthenticatedUser:
        assert token == "valid-token"
        return AuthenticatedUser(id=USER_ID, email="user@example.test", role="authenticated")


class FakeDataClient:
    def __init__(self, access: WorkspaceAccess | None) -> None:
        self.access = access

    async def aclose(self) -> None:
        return None

    async def get_workspace_access(
        self,
        *,
        access_token: str,
        workspace_id: UUID,
        user_id: UUID,
    ) -> WorkspaceAccess | None:
        assert access_token == "valid-token"
        assert workspace_id == WORKSPACE_ID
        assert user_id == USER_ID
        return self.access


async def test_authentication_is_required(client: AsyncClient) -> None:
    response = await client.get("/v1/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


async def test_reports_missing_supabase_configuration(client: AsyncClient) -> None:
    response = await client.get(
        "/v1/auth/me",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "AUTH_NOT_CONFIGURED"


async def test_returns_verified_user(client: AsyncClient) -> None:
    client._transport.app.state.auth_verifier = FakeVerifier()  # type: ignore[attr-defined]

    response = await client.get(
        "/v1/auth/me",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": str(USER_ID),
        "email": "user@example.test",
        "role": "authenticated",
    }


async def test_returns_workspace_access(client: AsyncClient) -> None:
    application = client._transport.app  # type: ignore[attr-defined]
    application.state.auth_verifier = FakeVerifier()
    application.state.supabase_data = FakeDataClient(
        WorkspaceAccess(workspace_id=WORKSPACE_ID, user_id=USER_ID, role="owner")
    )

    response = await client.get(
        f"/v1/workspaces/{WORKSPACE_ID}/access",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "owner"


async def test_denies_workspace_without_membership(client: AsyncClient) -> None:
    application = client._transport.app  # type: ignore[attr-defined]
    application.state.auth_verifier = FakeVerifier()
    application.state.supabase_data = FakeDataClient(None)

    response = await client.get(
        f"/v1/workspaces/{WORKSPACE_ID}/access",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "WORKSPACE_ACCESS_DENIED"


def _jwk(private_key: ec.EllipticCurvePrivateKey, key_id: str = "test-key") -> dict[str, Any]:
    value = jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    assert isinstance(value, dict)
    return {**value, "kid": key_id, "alg": "ES256", "use": "sig"}


def _token(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    key_id: str = "test-key",
    role: str = "authenticated",
    expires_in: timedelta = timedelta(minutes=5),
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": "authenticated",
            "sub": str(USER_ID),
            "role": role,
            "email": "user@example.test",
            "iat": now,
            "exp": now + expires_in,
        },
        private_key,
        algorithm="ES256",
        headers={"kid": key_id},
    )


async def test_verifies_with_cached_jwks() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        assert request.headers["apikey"] == "publishable"
        return httpx.Response(200, json={"keys": [_jwk(private_key)]})

    verifier = SupabaseJwtVerifier(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable",
        cache_seconds=600,
        timeout_seconds=3,
    )
    await verifier._client.aclose()
    verifier._client = httpx.AsyncClient(
        headers={"apikey": "publishable"},
        transport=httpx.MockTransport(handler),
    )

    first = await verifier.verify(_token(private_key))
    second = await verifier.verify(_token(private_key))
    await verifier.aclose()

    assert first.id == USER_ID
    assert second.email == "user@example.test"
    assert requests == 1


@pytest.mark.parametrize(
    ("token_factory", "expected_code"),
    [
        (
            lambda key: jwt.encode(
                {"sub": str(USER_ID)},
                key,
                algorithm="ES256",
            ),
            "INVALID_ACCESS_TOKEN",
        ),
        (
            lambda key: _token(key, role="anon"),
            "INVALID_ACCESS_TOKEN",
        ),
        (
            lambda key: _token(key, expires_in=timedelta(seconds=-1)),
            "INVALID_ACCESS_TOKEN",
        ),
    ],
)
async def test_rejects_invalid_tokens(token_factory: Any, expected_code: str) -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"keys": [_jwk(private_key)]})

    verifier = SupabaseJwtVerifier(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable",
        cache_seconds=600,
        timeout_seconds=3,
    )
    await verifier._client.aclose()
    verifier._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(AuthenticationError) as exc_info:
        await verifier.verify(token_factory(private_key))
    await verifier.aclose()

    assert exc_info.value.code == expected_code


async def test_reports_jwks_failure() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503)

    verifier = SupabaseJwtVerifier(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable",
        cache_seconds=600,
        timeout_seconds=3,
    )
    await verifier._client.aclose()
    verifier._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(AuthenticationError) as exc_info:
        await verifier.verify(_token(private_key))
    await verifier.aclose()

    assert exc_info.value.code == "AUTH_PROVIDER_UNAVAILABLE"


async def test_supabase_data_client_handles_membership_and_failures() -> None:
    responses = [
        httpx.Response(
            200,
            json=[
                {
                    "workspace_id": str(WORKSPACE_ID),
                    "user_id": str(USER_ID),
                    "role": "reviewer",
                }
            ],
        ),
        httpx.Response(200, json=[]),
        httpx.Response(503),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer token"
        return responses.pop(0)

    data_client = SupabaseDataClient(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable",
        timeout_seconds=3,
    )
    await data_client._client.aclose()
    data_client._client = httpx.AsyncClient(
        base_url="https://project.supabase.co/rest/v1",
        transport=httpx.MockTransport(handler),
    )

    access = await data_client.get_workspace_access(
        access_token="token",
        workspace_id=WORKSPACE_ID,
        user_id=USER_ID,
    )
    missing = await data_client.get_workspace_access(
        access_token="token",
        workspace_id=WORKSPACE_ID,
        user_id=USER_ID,
    )
    with pytest.raises(AuthenticationError) as exc_info:
        await data_client.get_workspace_access(
            access_token="token",
            workspace_id=WORKSPACE_ID,
            user_id=USER_ID,
        )
    await data_client.aclose()

    assert access is not None
    assert access.role == "reviewer"
    assert missing is None
    assert exc_info.value.code == "DATA_PROVIDER_UNAVAILABLE"
