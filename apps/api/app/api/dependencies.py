from dataclasses import dataclass
from typing import Annotated, Protocol, cast
from uuid import UUID

import structlog.contextvars
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.infrastructure.supabase.auth import AuthenticationError
from app.models.auth import AuthenticatedUser, WorkspaceAccess

bearer_scheme = HTTPBearer(auto_error=False)


class JwtVerifier(Protocol):
    async def verify(self, token: str) -> AuthenticatedUser: ...


class WorkspaceDataClient(Protocol):
    async def get_workspace_access(
        self,
        *,
        access_token: str,
        workspace_id: UUID,
        user_id: UUID,
    ) -> WorkspaceAccess | None: ...


@dataclass(frozen=True)
class AuthContext:
    user: AuthenticatedUser
    access_token: str


async def get_auth_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> AuthContext:
    resolved_credentials = credentials
    if resolved_credentials is None:
        resolved_credentials = await bearer_scheme(request)
    if resolved_credentials is None or resolved_credentials.scheme.lower() != "bearer":
        raise AuthenticationError(
            "AUTHENTICATION_REQUIRED",
            "A bearer access token is required.",
        )

    verifier = cast(JwtVerifier, request.app.state.auth_verifier)
    user = await verifier.verify(resolved_credentials.credentials)
    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    return AuthContext(user=user, access_token=resolved_credentials.credentials)


async def require_workspace_access(
    workspace_id: UUID,
    request: Request,
    auth: AuthContext,
) -> WorkspaceAccess:
    data_client = cast(WorkspaceDataClient, request.app.state.supabase_data)
    access = await data_client.get_workspace_access(
        access_token=auth.access_token,
        workspace_id=workspace_id,
        user_id=auth.user.id,
    )
    if access is None:
        raise AuthenticationError(
            "WORKSPACE_ACCESS_DENIED",
            "You do not have access to this workspace.",
            status=403,
        )
    rate_limiter = getattr(request.app.state, "rate_limiter", None)
    if rate_limiter is not None:
        expensive = request.method != "GET" and any(
            marker in request.url.path
            for marker in (
                "/messages",
                "/retrieval",
                "/documents",
                "/evaluations",
                "/approvals",
            )
        )
        await rate_limiter.check(
            workspace_id=workspace_id,
            actor_id=auth.user.id,
            bucket="expensive" if expensive else "standard",
            expensive=expensive,
        )
    structlog.contextvars.bind_contextvars(
        workspace_id=str(workspace_id),
        workspace_role=access.role,
    )
    return access
