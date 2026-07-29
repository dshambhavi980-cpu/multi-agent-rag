from collections.abc import Awaitable, Callable
from time import perf_counter
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
            correlation_id=str(request_id),
            method=request.method,
            path=request.url.path,
        )
        logger = get_logger()
        logger.info("request_started")
        started = perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = str(request_id)
            response.headers["X-Correlation-ID"] = str(request_id)
            logger.info(
                "request_completed",
                status_code=response.status_code,
                latency_ms=round((perf_counter() - started) * 1000, 3),
            )
            return response
        except Exception:
            logger.exception(
                "request_failed",
                latency_ms=round((perf_counter() - started) * 1000, 3),
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
