from typing import Any, cast
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.infrastructure.supabase.auth import AuthenticationError
from app.models.problem import Problem


class ApplicationError(Exception):
    def __init__(
        self,
        code: str,
        title: str,
        detail: str,
        *,
        status: int,
        retryable: bool = False,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.title = title
        self.detail = detail
        self.status = status
        self.retryable = retryable


def _request_id(request: Request) -> UUID:
    return cast(UUID, request.state.request_id)


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    fields: dict[str, list[str]] = {}
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        fields.setdefault(location, []).append(str(error["msg"]))

    problem = Problem(
        type="https://errors.docpilot.dev/request-validation",
        title="Request validation failed",
        status=422,
        code="REQUEST_VALIDATION_FAILED",
        detail="One or more request fields are invalid.",
        instance=str(request.url.path),
        request_id=_request_id(request),
        retryable=False,
        fields=fields,
    )
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json"),
        media_type="application/problem+json",
    )


async def authentication_error_handler(
    request: Request,
    exc: AuthenticationError,
) -> JSONResponse:
    problem = Problem(
        type=f"https://errors.docpilot.dev/{exc.code.lower().replace('_', '-')}",
        title="Authentication failed" if exc.status == 401 else "Access unavailable",
        status=exc.status,
        code=exc.code,
        detail=exc.detail,
        instance=str(request.url.path),
        request_id=_request_id(request),
        retryable=exc.retryable,
    )
    headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
    return problem_response(problem, headers=headers)


async def application_error_handler(
    request: Request,
    exc: ApplicationError,
) -> JSONResponse:
    problem = Problem(
        type=f"https://errors.docpilot.dev/{exc.code.lower().replace('_', '-')}",
        title=exc.title,
        status=exc.status,
        code=exc.code,
        detail=exc.detail,
        instance=str(request.url.path),
        request_id=_request_id(request),
        retryable=exc.retryable,
    )
    return problem_response(problem)


def install_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(
        RequestValidationError,
        validation_error_handler,  # type: ignore[arg-type]
    )
    application.add_exception_handler(
        AuthenticationError,
        authentication_error_handler,  # type: ignore[arg-type]
    )
    application.add_exception_handler(
        ApplicationError,
        application_error_handler,  # type: ignore[arg-type]
    )


def problem_response(problem: Problem, headers: dict[str, str] | None = None) -> JSONResponse:
    content: dict[str, Any] = problem.model_dump(mode="json")
    return JSONResponse(
        status_code=problem.status,
        content=content,
        headers=headers,
        media_type="application/problem+json",
    )
