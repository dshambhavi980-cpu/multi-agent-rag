from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import structlog.contextvars
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger

RequestHandler = Callable[[Request], Awaitable[Response]]


def _parse_request_id(raw_request_id: str | None) -> UUID:
    if raw_request_id is None:
        return uuid4()
    try:
        return UUID(raw_request_id)
    except ValueError:
        return uuid4()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        request_id = _parse_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=str(request_id),
            method=request.method,
            path=request.url.path,
        )
        logger = get_logger()
        logger.info("request_started")
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(request_id)
        logger.info("request_completed", status_code=response.status_code)
        structlog.contextvars.clear_contextvars()
        return response
